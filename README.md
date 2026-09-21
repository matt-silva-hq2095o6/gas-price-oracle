# gas-price-oracle

Small background daemon that polls `eth_feeHistory` from one or more EVM endpoints, saves block fee percentiles to a local SQLite database, and serves fast estimates over HTTP or a unix domain socket.

I built this because querying public RPCs on every transaction build is slow, rate-limited, and annoying when you run several local scripts or trading bots.

## Quick start

Install editable package:

```bash
pip install -e .
```

Run the daemon against your node:

```bash
gas-oracle run --rpc https://eth.llamarpc.com --db gas.db
```

Query current estimate from another terminal:

```bash
gas-oracle get
```

Or fetch JSON directly:

```bash
curl http://127.0.0.1:8545/estimate
```

## Unix socket support

If you prefer lower overhead or don't want to expose an open TCP port on the host, tell the daemon to listen on a unix socket:

```bash
gas-oracle run --rpc https://eth.llamarpc.com --socket /tmp/gas-oracle.sock
```

Query it via CLI:

```bash
gas-oracle get --socket /tmp/gas-oracle.sock --json
```

## Environment variables

- `GAS_ORACLE_RPC_URLS`: comma-separated list of HTTP RPC URLs
- `GAS_ORACLE_DB_PATH`: path to sqlite file (default: `~/.gas-oracle.db`)
- `GAS_ORACLE_POLL_INTERVAL`: seconds between polling runs (default: `4.0`)
- `GAS_ORACLE_HTTP_PORT`: daemon listen port (default: `8545`)
- `GAS_ORACLE_SOCKET_PATH`: unix socket path (if set, takes precedence over TCP)
- `GAS_ORACLE_HISTORY_BLOCKS`: how many blocks of history to fetch per poll (default: `20`)
- `GAS_ORACLE_RETENTION_HOURS`: prune records older than this (default: `24`)

## Output format

Estimates return slow, standard, fast, and instant tiers with base fee, priority fee, and recommended max fee in Gwei.

```json
{
  "timestamp": 1709900120,
  "latest_block": 19390214,
  "base_fee": 22.41,
  "estimated_next_base_fee": 23.10,
  "slow": {"max_priority_fee": 0.15, "max_fee": 23.25},
  "standard": {"max_priority_fee": 1.05, "max_fee": 24.15},
  "fast": {"max_priority_fee": 2.20, "max_fee": 25.30},
  "instant": {"max_priority_fee": 4.50, "max_fee": 27.60}
}
```

<!-- generated: 2026-09-21 -->
