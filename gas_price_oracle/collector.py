import asyncio
import logging
import time
from typing import List, Optional

from gas_price_oracle.config import AppConfig
from gas_price_oracle.rpc import FailoverRPCClient
from gas_price_oracle.storage import FeeStorage
from gas_price_oracle.types import BlockFeeSample

log = logging.getLogger(__name__)


class HistoryCollector:
    def __init__(self, cfg: AppConfig, rpc: FailoverRPCClient, storage: FeeStorage):
        self.cfg = cfg
        self.rpc = rpc
        self.storage = storage
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.last_saved_block = 0
        self._consecutive_dupes = 0

    async def start(self):
        self._running = True
        self.last_saved_block = await self.storage.get_latest_block_number()
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        while self._running:
            sleep_duration = self.cfg.poll_interval
            try:
                new_saved = await self.poll_once()
                if new_saved == 0:
                    self._consecutive_dupes += 1
                    # no new block yet, slow down slightly if we're hammering the node
                    if self._consecutive_dupes > 4:
                        sleep_duration = min(self.cfg.poll_interval * 1.5, 6.0)
                else:
                    self._consecutive_dupes = 0
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("poll cycle failed: %s", e)
                # back off on network or RPC errors
                sleep_duration = max(self.cfg.poll_interval * 2, 4.0)

            await asyncio.sleep(sleep_duration)

    async def poll_once(self) -> int:
        # TODO: switch to websocket eth_subscribe("newHeads") once ws failover is implemented
        req_blocks = self.cfg.history_blocks
        if self.last_saved_block > 0:
            # if we lagged behind or started fresh, grab a slightly wider window
            req_blocks = min(req_blocks * 2, 64)

        hist = await self.rpc.get_fee_history(
            block_count=req_blocks,
            newest_block="latest",
            reward_percentiles=self.cfg.percentiles,
        )

        samples: List[BlockFeeSample] = []
        n_blocks = len(hist.gas_used_ratios)
        now_ts = int(time.time())

        # baseFeePerGas has n_blocks + 1 entries according to spec
        for i in range(n_blocks):
            blk_num = hist.oldest_block + i
            if blk_num <= self.last_saved_block:
                continue

            base_fee = hist.base_fees[i]
            ratio = hist.gas_used_ratios[i]
            rewards = hist.reward[i] if i < len(hist.reward) else []

            # eth_feeHistory omits timestamps; approx 12s slot time on post-merge mainnet
            offset_sec = (n_blocks - 1 - i) * 12
            sample_ts = now_ts - offset_sec

            # basic trend: difference against previous block base fee
            prev_base = hist.base_fees[i - 1] if i > 0 else base_fee
            trend = ((base_fee - prev_base) / prev_base) if prev_base > 0 else 0.0

            samples.append(
                BlockFeeSample(
                    number=blk_num,
                    timestamp=sample_ts,
                    base_fee=base_fee,
                    gas_used_ratio=ratio,
                    rewards=rewards,
                    base_fee_trend=trend,
                )
            )

        if samples:
            await self.storage.save_samples(samples)
            self.last_saved_block = samples[-1].number
            log.info("ingested %d blocks up to %d", len(samples), self.last_saved_block)
            return len(samples)
        return 0
