from decimal import Decimal
from privex.exchange import ExchangeManager
import pytest
import nest_asyncio

from tests.base import assert_almost
from tests.base_rates import *
import logging

nest_asyncio.apply()

log = logging.getLogger(__name__)


@pytest.fixture()
async def adapter():
    adapter = ExchangeManager()
    yield adapter
    # del adapter


@pytest.mark.asyncio
async def test_get_pair_btcusd(adapter: ExchangeManager):
    price = await adapter.get_pair('BTC', 'USDT')
    log.debug(f'BTC/USDT: {price}')
    
    assert isinstance(price, Decimal)
    
    assert price > BTC_USD


@pytest.mark.asyncio
async def test_get_pair_ltcbtc(adapter: ExchangeManager):
    price = await adapter.get_pair('LTC', 'BTC')
    log.debug(f'LTC/BTC: {price}')

    assert isinstance(price, Decimal)
    assert price > LTC_BTC


@pytest.mark.asyncio
async def test_get_pair_hiveusd(adapter: ExchangeManager):
    ex_hivebtc = await adapter.get_pair('HIVE', 'BTC')
    ex_btcusd = await adapter.get_pair('BTC', 'USD')
    ex_hiveusd = await adapter.get_pair('HIVE', 'USD')

    calc_hiveusd = ex_hivebtc * ex_btcusd
    log.debug(f'HIVE/BTC: {ex_hivebtc} BTC/USD: {ex_btcusd} HIVE/USD: {ex_hiveusd} Calc HIVE/USD: {calc_hiveusd}')

    assert isinstance(ex_hiveusd, Decimal)
    assert ex_hiveusd > HIVE_USD
    
    assert_almost(ex_hiveusd, calc_hiveusd, Decimal('0.01'))


@pytest.mark.asyncio
async def test_get_pair_eoshive(adapter: ExchangeManager):
    ex_eosbtc = await adapter.get_pair('EOS', 'BTC')
    ex_hivebtc = await adapter.get_pair('HIVE', 'BTC')
    ex_hiveeos = await adapter.get_pair('HIVE', 'EOS')
    
    calc_hiveeos = ex_hivebtc / ex_eosbtc
    log.debug(f'HIVE/BTC: {ex_hivebtc} EOS/BTC: {ex_eosbtc} HIVE/EOS: {ex_hiveeos} Calc HIVE/EOS: {calc_hiveeos}')

    assert isinstance(ex_hiveeos, Decimal)
    
    assert_almost(ex_hiveeos, calc_hiveeos, Decimal('0.001'))


@pytest.mark.asyncio
async def test_get_pair_hiveltc(adapter: ExchangeManager):
    ex_ltcbtc = await adapter.get_pair('LTC', 'BTC')
    ex_hivebtc = await adapter.get_pair('HIVE', 'BTC')
    ex_hiveltc = await adapter.get_pair('HIVE', 'LTC')
    
    calc_hiveltc = ex_hivebtc / ex_ltcbtc

    log.debug(f'HIVE/BTC: {ex_hivebtc} LTC/BTC: {ex_ltcbtc} HIVE/LTC: {ex_hiveltc} Calc HIVE/LTC: {calc_hiveltc}')

    assert isinstance(ex_hivebtc, Decimal)
    
    assert_almost(ex_hiveltc, calc_hiveltc, Decimal('0.001'))


@pytest.mark.asyncio
async def test_get_pair_dogeltc(adapter: ExchangeManager):
    ex_dogebtc = await adapter.get_pair('DOGE', 'BTC')
    ex_ltcbtc = await adapter.get_pair('LTC', 'BTC')
    ex_dogeltc = await adapter.get_pair('DOGE', 'LTC')
    log.debug(f'DOGE/BTC: {ex_dogebtc:.8f}  LTC/BTC: {ex_ltcbtc:.8f}')

    calc_dogeltc = ex_dogebtc / ex_ltcbtc
    log.debug(f'DOGE/LTC: {ex_dogeltc:.8f}  Calc DOGE/LTC: {calc_dogeltc:.8f}')
    assert isinstance(ex_dogeltc, Decimal)
    
    assert_almost(ex_dogeltc, calc_dogeltc, Decimal('0.001'))

# ----


@pytest.mark.asyncio
async def test_get_avg_btcusd(adapter: ExchangeManager):
    price = await adapter.get_avg('BTC', 'USDT')
    log.debug(f'BTC/USDT: {price}')
    
    assert isinstance(price, Decimal)
    
    assert price > BTC_USD


@pytest.mark.asyncio
async def test_get_avg_ltcbtc(adapter: ExchangeManager):
    price = await adapter.get_avg('LTC', 'BTC')
    log.debug(f'LTC/BTC: {price}')
    
    assert isinstance(price, Decimal)
    assert price > LTC_BTC


@pytest.mark.asyncio
async def test_get_avg_hiveusd(adapter: ExchangeManager):
    ex_hivebtc = await adapter.get_avg('HIVE', 'BTC')
    ex_btcusd = await adapter.get_avg('BTC', 'USD')
    ex_hiveusd = await adapter.get_avg('HIVE', 'USD')
    
    calc_hiveusd = ex_hivebtc * ex_btcusd
    log.debug(f'HIVE/BTC: {ex_hivebtc} BTC/USD: {ex_btcusd} HIVE/USD: {ex_hiveusd} Calc HIVE/USD: {calc_hiveusd}')
    
    assert isinstance(ex_hiveusd, Decimal)
    assert ex_hiveusd > HIVE_USD
    
    assert_almost(ex_hiveusd, calc_hiveusd, Decimal('0.01'))
