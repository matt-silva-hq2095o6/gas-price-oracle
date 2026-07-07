import pytest
import os
import tempfile
from gas_price_oracle.storage import BlockStorage
from gas_price_oracle.types import BlockSample


@pytest.fixture
def storage():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    st = BlockStorage(path)
    yield st
    st.close()
    if os.path.exists(path):
        os.unlink(path)


def test_insert_and_get_latest(storage):
    sample1 = BlockSample(number=1000, base_fee=30_000_000_000, gas_used_ratio=0.5, rewards=[1_000_000_000])
    sample2 = BlockSample(number=1001, base_fee=32_000_000_000, gas_used_ratio=0.7, rewards=[2_000_000_000])
    
    storage.save_block(sample1)
    storage.save_block(sample2)

    latest = storage.get_latest_block_number()
    assert latest == 1001


def test_deduplication(storage):
    s1 = BlockSample(number=500, base_fee=10, gas_used_ratio=0.1, rewards=[1])
    s2 = BlockSample(number=500, base_fee=15, gas_used_ratio=0.2, rewards=[2])

    storage.save_block(s1)
    storage.save_block(s2)

    rows = storage.get_recent_blocks(limit=10)
    assert len(rows) == 1
    assert rows[0].base_fee == 15


def test_bulk_save_and_window_trim(storage):
    # populate 200 blocks
    blocks = []
    for i in range(1, 201):
        blocks.append(BlockSample(
            number=i,
            base_fee=10_000_000_000 + i * 10_000,
            gas_used_ratio=0.5,
            rewards=[1_000_000, 2_000_000]
        ))
    
    storage.save_blocks_batch(blocks)
    assert storage.count() == 200

    # trim keeping only the 50 newest
    deleted = storage.trim_history(keep_count=50)
    assert deleted == 150
    assert storage.count() == 50

    recent = storage.get_recent_blocks(limit=100)
    assert len(recent) == 50
    # oldest block in db should now be 151
    assert min(b.number for b in recent) == 151
    assert max(b.number for b in recent) == 200
