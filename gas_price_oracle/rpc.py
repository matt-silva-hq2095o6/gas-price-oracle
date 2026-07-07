import asyncio
import logging
from typing import Any, Dict, List, Optional
import httpx

from gas_price_oracle.types import FeeHistory

log = logging.getLogger(__name__)


def _hex_to_int(val: Any) -> int:
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        return int(val, 16)
    return 0


class RPCError(Exception):
    pass


class FailoverRPCClient:
    """Rotates across endpoints when one lags, throws 429 or drops connections."""

    def __init__(self, urls: List[str], timeout: float = 5.0):
        if not urls:
            raise ValueError("need at least one RPC URL")
        self.urls = urls
        self.timeout = timeout
        self._idx = 0
        self._client: Optional[httpx.AsyncClient] = None
        self._req_id = 0

    async def start(self):
        self._client = httpx.AsyncClient(timeout=self.timeout)

    async def close(self):
        if self._client:
            await self._client.aclose()

    async def _post(self, payload: Dict[str, Any]) -> Any:
        if not self._client:
            self._client = httpx.AsyncClient(timeout=self.timeout)

        attempts = len(self.urls)
        last_err = None

        for attempt_no in range(attempts):
            url = self.urls[self._idx]
            try:
                res = await self._client.post(url, json=payload)
                # print(f"DEBUG rpc status: {res.status_code}")
                if res.status_code in (429, 502, 503, 504):
                    log.warning("rpc node %s returned status %d, rotating", url, res.status_code)
                    self._idx = (self._idx + 1) % len(self.urls)
                    continue
                res.raise_for_status()
                data = res.json()
                if "error" in data:
                    err_msg = data["error"].get("message", "") if isinstance(data["error"], dict) else str(data["error"])
                    # alchemy and geth occasionally throw dirty block errors during reorgs
                    if "header not found" in err_msg.lower() or "unknown block" in err_msg.lower():
                        log.debug("node %s missing target block header, trying next", url)
                        self._idx = (self._idx + 1) % len(self.urls)
                        last_err = RPCError(err_msg)
                        continue
                    raise RPCError(err_msg)
                return data["result"]
            except (httpx.RequestError, RPCError) as e:
                last_err = e
                log.debug("rpc request failed on %s: %s", url, e)
                self._idx = (self._idx + 1) % len(self.urls)

        raise RPCError(f"all {attempts} RPC endpoints failed: {last_err}")

    async def get_block_number(self) -> int:
        self._req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": "eth_blockNumber",
            "params": [],
        }
        res = await self._post(payload)
        return _hex_to_int(res)

    async def get_fee_history(
        self, block_count: int, newest_block: str, reward_percentiles: List[float]
    ) -> FeeHistory:
        self._req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": "eth_feeHistory",
            "params": [hex(block_count), newest_block, reward_percentiles],
        }
        res = await self._post(payload)
        if not res:
            raise RPCError("empty fee history returned")

        oldest = _hex_to_int(res["oldestBlock"])
        base_fees = [_hex_to_int(x) for x in res.get("baseFeePerGas", [])]
        gas_ratios = [float(x) for x in res.get("gasUsedRatio", [])]

        # Erigon and early Nethermind nodes emit empty reward rows for zero tx blocks
        raw_rewards = res.get("reward", [])
        parsed_rewards: List[List[int]] = []
        for row in raw_rewards:
            if not row:
                parsed_rewards.append([0] * len(reward_percentiles))
            else:
                parsed_rewards.append([_hex_to_int(x) for x in row])

        return FeeHistory(
            oldest_block=oldest,
            base_fees=base_fees,
            gas_used_ratios=gas_ratios,
            reward=parsed_rewards,
        )
