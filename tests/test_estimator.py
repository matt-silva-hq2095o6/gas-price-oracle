import pytest
from gas_price_oracle.estimator import (
    calculate_percentiles,
    recommend_priority_fee,
    smooth_base_fee,
    trim_outliers,
)
from gas_price_oracle.types import BlockSample


def test_calculate_percentiles_simple():
    vals = [10.0, 20.0, 30.0, 40.0, 50.0]
    p25 = calculate_percentiles(vals, 25.0)
    p50 = calculate_percentiles(vals, 50.0)
    p75 = calculate_percentiles(vals, 75.0)
    assert p25 == 20.0
    assert p50 == 30.0
    assert p75 == 40.0


def test_empty_samples():
    assert calculate_percentiles([], 50.0) == 0.0


def test_single_element():
    assert calculate_percentiles([42.5], 10.0) == 42.5
    assert calculate_percentiles([42.5], 90.0) == 42.5


def test_trim_outliers():
    # 1 gwei baseline with a 100 gwei MEV spike
    raw = [1.0, 1.1, 1.2, 0.9, 1.05, 1.15, 100.0, 0.95]
    cleaned = trim_outliers(raw, upper_percentile=90.0)
    assert 100.0 not in cleaned
    assert len(cleaned) == 7


def test_smooth_base_fee():
    base_fees = [10_000_000_000, 11_250_000_000, 12_656_250_000]
    est = smooth_base_fee(base_fees, next_block_base_fee=14_000_000_000)
    assert est >= 12_656_250_000
    assert est <= 14_000_000_000


def test_smooth_base_fee_empty_history():
    assert smooth_base_fee([], next_block_base_fee=25_000_000_000) == 25_000_000_000


def test_recommend_priority_fee_levels():
    samples = [
        BlockSample(number=100, base_fee=20_000_000_000, gas_used_ratio=0.5, rewards=[1_000_000_000, 2_000_000_000, 5_000_000_000]),
        BlockSample(number=101, base_fee=20_000_000_000, gas_used_ratio=0.6, rewards=[1_500_000_000, 2_500_000_000, 6_000_000_000]),
    ]
    rec = recommend_priority_fee(samples, min_priority_fee=1_000_000_000)
    assert rec.slow >= 1_000_000_000
    assert rec.standard >= rec.slow
    assert rec.fast >= rec.standard


def test_zero_reward_empty_blocks():
    # empty blocks where miner got 0 priority fees
    samples = [
        BlockSample(number=200, base_fee=15_000_000_000, gas_used_ratio=0.0, rewards=[0, 0, 0]),
        BlockSample(number=201, base_fee=13_125_000_000, gas_used_ratio=0.0, rewards=[0, 0, 0]),
    ]
    # should bump up to min_priority_fee
    rec = recommend_priority_fee(samples, min_priority_fee=1_000_000_000)
    assert rec.slow == 1_000_000_000
    assert rec.standard == 1_000_000_000
    assert rec.fast == 1_000_000_000
