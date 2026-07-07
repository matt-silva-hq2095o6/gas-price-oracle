import asyncio
import json
import os
from aiohttp import web
from gas_price_oracle.storage import Storage
from gas_price_oracle.estimator import FeeEstimator


class OracleServer:
    """Serves cached fee estimates and health status over HTTP or Unix socket."""

    def __init__(self, storage: Storage, estimator: FeeEstimator, host: str = "127.0.0.1", port: int = 8545, socket_path: str | None = None, socket_mode: int = 0o660):
        self.storage = storage
        self.estimator = estimator
        self.host = host
        self.port = port
        self.socket_path = socket_path
        self.socket_mode = socket_mode
        self.app = web.Application()
        self._setup_routes()
        self._runner = None

    def _setup_routes(self):
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/estimate", self.handle_estimate)
        self.app.router.add_get("/v1/estimate", self.handle_estimate)
        self.app.router.add_get("/stats", self.handle_stats)

    async def handle_health(self, request: web.Request) -> web.Response:
        latest_block = await self.storage.get_latest_block_number()
        if latest_block is None:
            return web.json_response({"status": "degraded", "reason": "no block data yet"}, status=503)
        return web.json_response({"status": "ok", "latest_block": latest_block})

    async def handle_estimate(self, request: web.Request) -> web.Response:
        # FIXME: cache this in-memory if query rate exceeds ~200 rps
        priority = request.query.get("priority", "normal")
        chain_id_raw = request.query.get("chain_id")
        chain_id = int(chain_id_raw) if chain_id_raw else None

        # print(f"estimate request: priority={priority} chain_id={chain_id}")
        estimate = await self.estimator.get_estimate(priority=priority, chain_id=chain_id)
        
        if not estimate:
            return web.json_response({"error": "insufficient history for estimate"}, status=503)

        return web.json_response({
            "base_fee": estimate.base_fee,
            "next_base_fee": estimate.next_base_fee,
            "priority_fee": estimate.priority_fee,
            "max_fee": estimate.max_fee,
            "confidence": estimate.confidence,
            "latest_block": estimate.block_number,
            "timestamp": estimate.timestamp,
        })

    async def handle_stats(self, request: web.Request) -> web.Response:
        limit = int(request.query.get("limit", 50))
        chain_id_raw = request.query.get("chain_id")
        chain_id = int(chain_id_raw) if chain_id_raw else None
        
        rows = await self.storage.get_recent_history(limit=min(limit, 500), chain_id=chain_id)
        return web.json_response({"count": len(rows), "history": rows})

    async def start(self):
        self._runner = web.AppRunner(self.app)
        await self._runner.setup()

        if self.socket_path:
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)
            site = web.UnixSite(self._runner, path=self.socket_path)
            await site.start()
            try:
                os.chmod(self.socket_path, self.socket_mode)
            except OSError:
                pass
        else:
            site = web.TCPSite(self._runner, self.host, self.port)
            await site.start()

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
        if self.socket_path and os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except OSError:
                pass
