import json
import sqlite3
from pathlib import Path
from gas_price_oracle.types import BlockFeeData


class Storage:
    """Local SQLite store for block fee history."""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        # WAL mode keeps reads non-blocking while polling worker writes
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fee_history (
                    block_number INTEGER PRIMARY KEY,
                    base_fee INTEGER NOT NULL,
                    gas_used_ratio REAL NOT NULL,
                    timestamp INTEGER NOT NULL,
                    rewards_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_timestamp ON fee_history(timestamp)"
            )

    def save_block(self, block: BlockFeeData) -> None:
        self.save_blocks([block])

    def save_blocks(self, blocks: list[BlockFeeData]) -> None:
        if not blocks:
            return
        with self._get_conn() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO fee_history (
                    block_number, base_fee, gas_used_ratio, timestamp, rewards_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        b.number,
                        b.base_fee,
                        b.gas_used_ratio,
                        b.timestamp,
                        json.dumps(b.rewards),
                    )
                    for b in blocks
                ],
            )

    def get_latest_block_number(self) -> int | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT MAX(block_number) as max_num FROM fee_history"
            ).fetchone()
            if row and row["max_num"] is not None:
                return int(row["max_num"])
            return None

    def get_recent_blocks(self, limit: int = 20) -> list[BlockFeeData]:
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT block_number, base_fee, gas_used_ratio, timestamp, rewards_json
                FROM fee_history
                ORDER BY block_number DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        # reverse so returned list is ascending by block number
        result = []
        for r in reversed(rows):
            result.append(
                BlockFeeData(
                    number=r["block_number"],
                    base_fee=r["base_fee"],
                    gas_used_ratio=r["gas_used_ratio"],
                    timestamp=r["timestamp"],
                    rewards=json.loads(r["rewards_json"]),
                )
            )
        return result

    def get_block_count(self) -> int:
        with self._get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM fee_history").fetchone()
            return int(row["cnt"]) if row else 0

    def prune(self, keep_blocks: int = 2000) -> int:
        # FIXME: vacuum periodically when pruning large batches on long-running instances
        latest = self.get_latest_block_number()
        if latest is None:
            return 0

        cutoff = latest - keep_blocks
        if cutoff <= 0:
            return 0

        with self._get_conn() as conn:
            cur = conn.execute(
                "DELETE FROM fee_history WHERE block_number < ?",
                (cutoff,),
            )
            # print(f"storage prune removed {cur.rowcount} rows")
            return cur.rowcount
