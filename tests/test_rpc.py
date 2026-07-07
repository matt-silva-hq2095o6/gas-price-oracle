import pytest
import httpx
from gas_price_oracle.rpc import (
    hex_to_int,
    parse_fee_history_response,
    RpcClientPool,
    RpcError,
)


def test_hex_to_int():
    assert hex_to_int("0x0") == 0
    assert hex_to_int("0x10") == 16
    assert hex_to_int("0x1f4") == 500
    assert hex_to_int("100") == 256
    assert hex_to_int(0) == 0


def test_parse_fee_history_payload():
    payload = {
        "oldestBlock": "0xa",
        "baseFeePerGas": ["0x7", "0x8", "0x9"],
        "gasUsedRatio": [0.5, 0.8],
        "reward": [
            ["0x1", "0x2", "0x3"],
            ["0x2", "0x4", "0x6"],
        ]
    }
    parsed = parse_fee_history_response(payload)
    assert parsed.oldest_block == 10
    assert len(parsed.base_fees) == 3
    assert parsed.base_fees == [7, 8, 9]
    assert parsed.gas_used_ratios == [0.5, 0.8]
    assert parsed.rewards[0] == [1, 2, 3]
    assert parsed.rewards[1] == [2, 4, 6]


def test_parse_fee_history_missing_rewards():
    # Some l2 nodes don't return reward arrays if no priority txs
    payload = {
        "oldestBlock": "0x1",
        "baseFeePerGas": ["0x10", "0x10"],
        "gasUsedRatio": [0.0],
    }
    parsed = parse_fee_history_response(payload)
    assert parsed.rewards == [[]]


@pytest.mark.asyncio
async def test_rpc_pool_failover():
    call_counts = {"primary": 0, "backup": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "primary.local" in url:
            call_counts["primary"] += 1
            # simulate rate limit on primary
            return httpx.Response(429, json={"error": "rate limited"})
        elif "backup.local" in url:
            call_counts["backup"] += 1
            return httpx.Response(200, json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "oldestBlock": "0x5",
                    "baseFeePerGas": ["0x10", "0x12"],
                    "gasUsedRatio": [0.4],
                    "reward": [["0x1", "0x2"]]
                }
            })
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    pool = RpcClientPool(
        endpoints=["http://primary.local", "http://backup.local"],
        transport=transport,
        max_retries_per_node=1,
    )

    res = await pool.fetch_fee_history(block_count=1, newest_block="latest", reward_percentiles=[10, 50])
    assert res.oldest_block == 5
    assert call_counts["primary"] >= 1
    assert call_counts["backup"] == 1
    await pool.close()
