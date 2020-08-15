from decimal import Decimal
from privex.exchange.SteemEngine import SteemEngine
import pytest
import nest_asyncio

from tests.base_rates import *

nest_asyncio.apply()


@pytest.fixture()
async def adapter():
    adapter = SteemEngine()
    yield adapter
    del adapter


@pytest.mark.asyncio
async def test_get_pair_btcsteem(adapter: SteemEngine):
    pair_data = await adapter.get_pair('BTC', 'STEEM')
    
    assert pair_data.from_coin == 'BTCP'
    assert pair_data.to_coin == 'STEEMP'
    
    assert isinstance(pair_data.last, Decimal)
    
    assert pair_data.last >= BTC_STEEM


@pytest.mark.asyncio
async def test_get_pair_ltcsteem(adapter: SteemEngine):
    pair_data = await adapter.get_pair('LTC', 'STEEMP')
    
    assert pair_data.from_coin == 'LTCP'
    assert pair_data.to_coin == 'STEEMP'
    
    assert isinstance(pair_data.last, Decimal)
    
    assert pair_data.last >= LTC_STEEM


@pytest.mark.asyncio
async def test_get_pair_eossteem(adapter: SteemEngine):
    pair_data = await adapter.get_pair('EOSP', 'STEEM')
    
    assert pair_data.from_coin == 'EOSP'
    assert pair_data.to_coin == 'STEEMP'
    
    assert isinstance(pair_data.last, Decimal)
    
    assert pair_data.last >= EOS_STEEM

