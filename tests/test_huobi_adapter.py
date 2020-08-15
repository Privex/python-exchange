from decimal import Decimal
from privex.exchange import Huobi
import pytest
import nest_asyncio

from tests.base_rates import *

nest_asyncio.apply()


@pytest.fixture()
async def adapter():
    adapter = Huobi()
    yield adapter
    del adapter


@pytest.mark.asyncio
async def test_get_pair_btcusd(adapter: Huobi):
    pair_data = await adapter.get_pair('BTC', 'USDT')
    
    assert pair_data.from_coin == 'BTC'
    assert pair_data.to_coin == 'USDT'
    
    assert isinstance(pair_data.last, Decimal)
    
    assert pair_data.last > BTC_USD


@pytest.mark.asyncio
async def test_get_pair_ltcbtc(adapter: Huobi):
    pair_data = await adapter.get_pair('LTC', 'BTC')
    
    assert pair_data.from_coin == 'LTC'
    assert pair_data.to_coin == 'BTC'
    
    assert isinstance(pair_data.last, Decimal)
    
    assert pair_data.last > LTC_BTC


@pytest.mark.asyncio
async def test_get_pair_hivebtc(adapter: Huobi):
    pair_data = await adapter.get_pair('HIVE', 'BTC')
    
    assert pair_data.from_coin == 'HIVE'
    assert pair_data.to_coin == 'BTC'
    
    assert isinstance(pair_data.last, Decimal)
    
    assert pair_data.last > HIVE_BTC


@pytest.mark.asyncio
async def test_get_pair_hiveusd(adapter: Huobi):
    pair_data = await adapter.get_pair('HIVE', 'USD')
    
    assert pair_data.from_coin == 'HIVE'
    assert pair_data.to_coin == 'USD'
    
    assert isinstance(pair_data.last, Decimal)
    
    assert pair_data.last > HIVE_USD
