from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(slots=True)
class BlockFeeSample:
    number: int
    timestamp: int
    base_fee: int
    gas_used_ratio: float
    rewards: List[int] = field(default_factory=list)
    base_fee_trend: float = 0.0


@dataclass(slots=True)
class FeeHistory:
    oldest_block: int
    base_fees: List[int]
    gas_used_ratios: List[float]
    reward: List[List[int]]


@dataclass(slots=True)
class FeeEstimate:
    base_fee: int
    next_base_fee: int
    slow_priority: int
    normal_priority: int
    fast_priority: int
    instant_priority: int
    sample_count: int
    latest_block: int
    confidence: float = 0.95
