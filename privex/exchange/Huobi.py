from json import JSONDecodeError
from typing import Set, Tuple, Optional, AsyncGenerator, Dict, List
from async_property import async_property
from httpx import HTTPError
from privex.helpers import filter_form
from privex.exchange.base import AsyncProvidesAdapter, PriceData
from privex.exchange.exceptions import PairNotFound, ExchangeDown
import httpx

import logging

log = logging.getLogger(__name__)


class Huobi(AsyncProvidesAdapter):
    TICKER_API = 'https://api.huobi.pro/market/detail/merged?symbol='
    PROVIDES_API = 'https://api.huobi.pro/v1/common/symbols'
    
    name = "Huobi"
    code = "huobi"
    
    _provides = set()
    _extra_provides = set()
    
    async def has_pair(self, from_coin: str, to_coin: str) -> bool:
        prov = await self.provides
        pairs = []
        for f, t in prov:
            pairs += [f"{f.upper()}_{t.upper()}"]
        
        from_coin, to_coin, = from_coin.upper(), to_coin.upper()
        
        if f"{from_coin}_{to_coin}" in pairs:
            return True
        
        if from_coin == 'USD' and (f"USDT_{to_coin}" in pairs or f"USDC_{to_coin}" in pairs):
            return True
        if to_coin == 'USD' and (f"{from_coin}_USDT" in pairs or f"{from_coin}_USDC" in pairs):
            return True
        
        return False
    
    # noinspection PyTypeChecker
    async def _gen_provides(self, *args, **kwargs) -> Set[Tuple[str, str]]:
        async with httpx.AsyncClient() as client:
            data = await client.get(self.PROVIDES_API, timeout=20)
            try:
                data.raise_for_status()
            except HTTPError as e:
                try:
                    data = e.response.json()
                    raise ExchangeDown(f"{self.name} appears to be down. Error was: {data}")
                except (JSONDecodeError, AttributeError, KeyError):
                    raise ExchangeDown(f"{self.name} appears to be down. Error was: {type(e)} {str(e)}")
            res: dict = data.json()
        
        if 'data' not in res:
            raise ExchangeDown(f"'data' missing from {self.name} ({self.code}) PROVIDES API...")
        
        pairs = set()
        for p in res['data']:
            pairs.add((p['base-currency'].upper(), p['quote-currency'].upper()))
        
        return pairs
    
    async def load_pairs(self):
        prov = await self.provides
        res = [f"{f.upper()}_{t.upper()}" for f, t in prov]
        return res

    async def _get_pair(self, from_coin: str, to_coin: str) -> PriceData:
        pairs: List[str] = await self.load_pairs()
        from_coin, to_coin = from_coin.upper(), to_coin.upper()
        orig_from, orig_to = from_coin, to_coin
    
        key = f"{from_coin}_{to_coin}"
        if key not in pairs:
            if from_coin == 'USD':
                from_coin, key = "USDT", f"USDT_{to_coin}"
            if to_coin == 'USD':
                to_coin, key = "USDT", f"{from_coin}_USDT"
        
            if key not in pairs:
                raise PairNotFound(f"The coin pair '{from_coin}/{to_coin}' is not supported by {self.name}")
        
        async with httpx.AsyncClient() as client:
            data = await client.get(f"{self.TICKER_API}{from_coin.lower()}{to_coin.lower()}", timeout=20)
            try:
                data.raise_for_status()
            except HTTPError as e:
                try:
                    data = e.response.json()
                    raise ExchangeDown(f"{self.name} appears to be down. Error was: {data}")
                except (JSONDecodeError, AttributeError, KeyError):
                    raise ExchangeDown(f"{self.name} appears to be down. Error was: {type(e)} {str(e)}")
            res: dict = data.json()

        if 'tick' not in res:
            raise ExchangeDown(f"'tick' missing from {self.name} ({self.code}) TICKER API...")
        
        # Convert all of the numbers into strings - Huobi returns floats which results in weird
        # rounding issues when converted into Decimal.
        ticker: dict = filter_form(res['tick'], 'close', 'high', 'low', 'amount', 'close', 'open', cast=str)
        ticker['bid'] = str(res['tick']['bid'][0])
        ticker['ask'] = str(res['tick']['ask'][0])
    
        return PriceData(
            from_coin=orig_from, to_coin=orig_to, last=ticker['close'], bid=ticker['bid'], ask=ticker['ask'],
            high=ticker['high'], low=ticker['low'], volume=ticker['amount'], close=ticker['close'], open=ticker['open']
        )

