import math
from gas_price_oracle.types import BlockFeeData, FeeEstimate, TierEstimate


def calculate_next_base_fee(base_fee: int, gas_used_ratio: float) -> int:
    """EIP-1559 next base fee formula based on target gas usage ratio of 0.5."""
    target = 0.5
    if abs(gas_used_ratio - target) < 1e-6:
        return base_fee
    if gas_used_ratio > target:
        # max 12.5% increase per block when ratio is 1.0
        delta = int(base_fee * ((gas_used_ratio - target) / target) / 8)
        return base_fee + max(1, delta)
    
    delta = int(base_fee * ((target - gas_used_ratio) / target) / 8)
    return max(0, base_fee - delta)


def _weighted_percentile(values: list[int], weights: list[float], percentile: float) -> int:
    if not values:
        return 0
    if len(values) == 1:
        return values[0]

    # sort together by value
    combined = sorted(zip(values, weights), key=lambda x: x[0])
    total_weight = sum(weights)
    if total_weight <= 0:
        return combined[len(combined) // 2][0]

    threshold = total_weight * percentile
    running = 0.0
    for val, weight in combined:
        running += weight
        if running >= threshold:
            return val
    return combined[-1][0]


def estimate_fees(
    blocks: list[BlockFeeData],
    min_priority_fee: int = 1_000_000_000,  # 1 gwei floor
) -> FeeEstimate:
    if not blocks:
        return FeeEstimate(
            base_fee=0,
            next_base_fee=0,
            base_fee_trend=0.0,
            slow=TierEstimate(max_priority_fee=min_priority_fee, max_fee=min_priority_fee),
            normal=TierEstimate(max_priority_fee=min_priority_fee, max_fee=min_priority_fee),
            fast=TierEstimate(max_priority_fee=min_priority_fee, max_fee=min_priority_fee),
            urgent=TierEstimate(max_priority_fee=min_priority_fee, max_fee=min_priority_fee),
            sample_size=0,
        )

    last_block = blocks[-1]
    next_base = calculate_next_base_fee(last_block.base_fee, last_block.gas_used_ratio)

    # calculate base fee trend using simple linear slope over the window
    n = len(blocks)
    if n >= 2:
        first_base = blocks[0].base_fee
        if first_base > 0:
            trend = round((last_block.base_fee - first_base) / first_base, 4)
        else:
            trend = 0.0
    else:
        trend = 0.0

    # Weight recent blocks higher with exponential decay factor 0.9
    # Also weight blocks by gas used ratio to downweight empty blocks
    tip_pool: list[int] = []
    weight_pool: list[float] = []

    for idx, b in enumerate(blocks):
        # recency multiplier: latest block idx == n-1 gets 1.0
        recency = math.pow(0.92, n - 1 - idx)
        # block activity weight - empty blocks shouldn't distort priority fee
        activity = max(0.1, b.gas_used_ratio)
        block_weight = recency * activity

        for tip in b.rewards:
            if tip <= 0:
                continue
            tip_pool.append(tip)
            weight_pool.append(block_weight)

    # print(f"DEBUG: tip_pool={len(tip_pool)} weights={len(weight_pool)}")

    # fallback defaults if all sampled blocks had zero tips (e.g. fresh devnet)
    if not tip_pool:
        slow_tip = min_priority_fee
        norm_tip = int(min_priority_fee * 1.2)
        fast_tip = int(min_priority_fee * 1.5)
        urg_tip = int(min_priority_fee * 2.0)
    else:
        slow_tip = max(min_priority_fee, _weighted_percentile(tip_pool, weight_pool, 0.15))
        norm_tip = max(slow_tip, _weighted_percentile(tip_pool, weight_pool, 0.45))
        fast_tip = max(norm_tip, _weighted_percentile(tip_pool, weight_pool, 0.75))
        urg_tip = max(fast_tip, _weighted_percentile(tip_pool, weight_pool, 0.95))

    # Add safety buffers for max fee depending on speed tier
    # Urgent tier allows for 2 consecutive 12.5% base fee spikes
    def calc_max_fee(tip: int, base_multiplier: float) -> int:
        return int(next_base * base_multiplier) + tip

    return FeeEstimate(
        base_fee=last_block.base_fee,
        next_base_fee=next_base,
        base_fee_trend=trend,
        slow=TierEstimate(
            max_priority_fee=slow_tip,
            max_fee=calc_max_fee(slow_tip, 1.10),
        ),
        normal=TierEstimate(
            max_priority_fee=norm_tip,
            max_fee=calc_max_fee(norm_tip, 1.20),
        ),
        fast=TierEstimate(
            max_priority_fee=fast_tip,
            max_fee=calc_max_fee(fast_tip, 1.30),
        ),
        urgent=TierEstimate(
            max_priority_fee=urg_tip,
            max_fee=calc_max_fee(urg_tip, 1.45),
        ),
        sample_size=n,
    )
