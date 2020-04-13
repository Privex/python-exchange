from json import JSONDecodeError
from typing import Set, Tuple, Optional, AsyncGenerator, Dict, List, Union

from async_property import async_property
from httpx import HTTPError
from privex.helpers import cached, empty, awaitable_class, r_cache, r_cache_async, DictObject

from privex.exchange.base import ExchangeAdapter, PriceData, ExchangeDown, PairNotFound
import httpx

import logging

log = logging.getLogger(__name__)


@awaitable_class
class Bittrex(ExchangeAdapter):
    MARKET_API = 'https://api.bittrex.com/v3/markets'
    
    name = "Bittrex"
    code = "bittrex"
    
    _provides = set()
    _extra_provides = set()

    async def has_pair(self, from_coin: str, to_coin: str) -> bool:
        prov = await self.provides
        pairs = []
        for f, t in prov:
            pairs += [f"{f.upper()}_{t.upper()}"]

        from_coin, to_coin, = from_coin.upper(), to_coin.upper()
        
        if f"{from_coin}_{to_coin}" in pairs: return True
        if from_coin == 'USD' and f"USDT_{to_coin}" in pairs: return True
        if to_coin == 'USD' and f"{from_coin}_USDT" in pairs: return True

        return False

    @r_cache_async(f"pvxex:bittrex:all_pairs", 300)
    async def load_pairs(self) -> List[str]:
        # First try and get the ticker data from cache
        # ckey = f"pvxex:{self.code}:all_pairs"
        # cdata = await cached.get(ckey)
        #
        # if not empty(cdata):
        #     return cdata
        
        # If we don't have it in the privex-helpers cache, query the Bittrex API, cache the data and return it.
        data = []
        async for from_coin, to_coin in self._load_pairs():
            data += [f"{from_coin}_{to_coin}"]

        # await cached.set(ckey, data)
        
        return data

    async def _load_pairs(self) -> AsyncGenerator[Tuple[str, str], None]:
        """
        Used internally by :meth:`.get_tickers`
        
        Queries the Bittrex market API :attr:`.MARKET_API` asynchronously, and returns
        ``Tuple[str, str]`` objects as an async generator::
        
            >>> async for frm_coin, to_coin in self._load_pairs():
            ...     print(frm_coin, to_coin)
        
        :return AsyncGenerator[PriceData,None] ticker: An async generator of ticker pairs
        """
        # Query the Bittrex API and obtain the pairs data as a list of dictionaries
        async with httpx.AsyncClient() as client:
            data = await client.get(self.MARKET_API, timeout=20)
            try:
                data.raise_for_status()
            except HTTPError as e:
                try:
                    data = e.response.json()
                    raise ExchangeDown(f"{self.name} appears to be down. Error was: {data}")
                except (JSONDecodeError, AttributeError, KeyError):
                    raise ExchangeDown(f"{self.name} appears to be down. Error was: {type(e)} {str(e)}")
            res: List[dict] = data.json()
        # Loop over each ticker dictionary and return a PriceData object
        for d in res:   # type: dict
            yield d['baseCurrencySymbol'], d['quoteCurrencySymbol']

    # noinspection PyTypeChecker
    async def _gen_provides(self, *args, **kwargs) -> Set[Tuple[str, str]]:
        t = await self.load_pairs()
        _provides: Set[Tuple[str, str]] = set()
        for k in t:
            _provides.add(tuple(k.split('_')))
        return _provides

    @async_property
    async def provides(self) -> Set[Tuple[str, str]]:
        """
        Binance provides ALL of their tickers through one GET query, so we can generate ``provides``
        simply by querying their API via :meth:`._load_pairs` (using :meth:`._gen_provides`)
        
        We cache the provides Set both class-locally in :attr:`._provides`, as well as via the Privex Helpers
        Cache system - :mod:`privex.helpers.cache`
        
        """
        if empty(self._provides, itr=True):
            _prov = await cached.get(f"pvxex:{self.code}:provides")
            if not empty(_prov):
                self._provides = _prov
            else:
                self._provides = await self._gen_provides()
                await cached.set(f"pvxex:{self.code}:provides", self._provides)
        return self._provides

    async def _query(self, from_coin: str, to_coin: str, endpoint='/') -> Union[list, dict]:
        async with httpx.AsyncClient() as client:
            data = await client.get(f"{self.MARKET_API}/{from_coin}-{to_coin}{endpoint}", timeout=20)
            try:
                data.raise_for_status()
            except HTTPError as e:
                try:
                    data = e.response.json()
                    raise ExchangeDown(f"{self.name} appears to be down. Error was: {data}")
                except (JSONDecodeError, AttributeError, KeyError):
                    raise ExchangeDown(f"{self.name} appears to be down. Error was: {type(e)} {str(e)}")
        return data.json()

    @r_cache_async(lambda self, from_coin, to_coin: f"pvxex:bittrex:tick:{from_coin}:{to_coin}", 30)
    async def _q_ticker(self, from_coin: str, to_coin: str) -> DictObject:
        from_coin, to_coin = from_coin.upper(), to_coin.upper()
        res = await self._query(from_coin, to_coin, endpoint='/ticker')
        return DictObject(last=res['lastTradeRate'], bid=res['bidRate'], ask=res['askRate'])

    @r_cache_async(lambda self, from_coin, to_coin: f"pvxex:bittrex:sum:{from_coin}:{to_coin}", 30)
    async def _q_summary(self, from_coin: str, to_coin: str) -> DictObject:
        from_coin, to_coin = from_coin.upper(), to_coin.upper()
        res = await self._query(from_coin, to_coin, endpoint='/summary')
        return DictObject(high=res['high'], low=res['low'], volume=res['volume'])

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
        
        summary = await self._q_summary(from_coin, to_coin)
        ticker = await self._q_ticker(from_coin, to_coin)
        
        return PriceData(
            from_coin=orig_from, to_coin=orig_to, last=ticker.last, bid=ticker.bid, ask=ticker.ask,
            high=summary.high, low=summary.low, volume=summary.volume
        )
        

