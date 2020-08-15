from decimal import Decimal
from privex.exchange.SteemEngine import HiveEngine
import pytest
import nest_asyncio

from tests.base_rates import *

nest_asyncio.apply()


@pytest.fixture()
async def adapter():
    adapter = HiveEngine()
    yield adapter
    del adapter


@pytest.mark.asyncio
async def test_get_pair_btchive(adapter: HiveEngine):
    pair_data = await adapter.get_pair('BTC', 'HIVE')
    
    assert pair_data.from_coin == 'SWAP.BTC'
    assert pair_data.to_coin == 'SWAP.HIVE'
    
    assert isinstance(pair_data.last, Decimal)
    
    assert pair_data.last >= BTC_HIVE


@pytest.mark.asyncio
async def test_get_pair_ltchive(adapter: HiveEngine):
    pair_data = await adapter.get_pair('LTC', 'SWAP.HIVE')
    
    assert pair_data.from_coin == 'SWAP.LTC'
    assert pair_data.to_coin == 'SWAP.HIVE'
    
    assert isinstance(pair_data.last, Decimal)
    
    assert pair_data.last >= LTC_HIVE


@pytest.mark.asyncio
async def test_get_pair_eoshive(adapter: HiveEngine):
    pair_data = await adapter.get_pair('SWAP.EOS', 'HIVE')
    
    assert pair_data.from_coin == 'SWAP.EOS'
    assert pair_data.to_coin == 'SWAP.HIVE'
    
    assert isinstance(pair_data.last, Decimal)
    
    assert pair_data.last >= EOS_HIVE

