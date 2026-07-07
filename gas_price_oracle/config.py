import os
from dataclasses import dataclass, field
from typing import List, Optional


def _split_urls(val: str) -> List[str]:
    return [u.strip() for u in val.split(",") if u.strip()]


@dataclass(slots=True)
class AppConfig:
    rpc_urls: List[str] = field(default_factory=lambda: ["http://127.0.0.1:8545"])
    poll_interval: float = 2.0
    history_blocks: int = 10
    percentiles: List[float] = field(default_factory=lambda: [10.0, 30.0, 60.0, 90.0])
    db_path: str = "fees.db"
    http_host: str = "127.0.0.1"
    http_port: int = 8080
    socket_path: Optional[str] = None
    rpc_timeout: float = 5.0
    max_retries: int = 3

    @classmethod
    def from_env(cls) -> "AppConfig":
        raw_urls = os.getenv("RPC_URLS") or os.getenv("RPC_URL")
        urls = _split_urls(raw_urls) if raw_urls else ["http://127.0.0.1:8545"]

        raw_pcts = os.getenv("PERCENTILES")
        if raw_pcts:
            pcts = [float(p.strip()) for p in raw_pcts.split(",") if p.strip()]
        else:
            pcts = [10.0, 30.0, 60.0, 90.0]

        return cls(
            rpc_urls=urls,
            poll_interval=float(os.getenv("POLL_INTERVAL", "2.0")),
            history_blocks=int(os.getenv("HISTORY_BLOCKS", "10")),
            percentiles=pcts,
            db_path=os.getenv("DB_PATH", "fees.db"),
            http_host=os.getenv("HTTP_HOST", "127.0.0.1"),
            http_port=int(os.getenv("HTTP_PORT", "8080")),
            socket_path=os.getenv("SOCKET_PATH"),
            rpc_timeout=float(os.getenv("RPC_TIMEOUT", "5.0")),
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
        )
