from decimal import Decimal
from json import JSONDecodeError
from typing import Set, Tuple, Optional, AsyncGenerator, Dict, List, Union

from async_property import async_property
from httpx import HTTPError
from privex.helpers import cached, empty, awaitable_class, r_cache_async, DictObject

from privex.exchange.base import ExchangeAdapter, PriceData, ExchangeDown, PairNotFound
import httpx

import logging

log = logging.getLogger(__name__)


@awaitable_class
class CoinGecko(ExchangeAdapter):
    BASE_API = 'https://api.coingecko.com/api/v3'
    
    name = "CoinGecko"
    code = "coingecko"
    
    _provides = set()
    _extra_provides = set()
    
    compare_symbols = ['BTC', 'ETH', 'USD', 'GBP', 'EUR', 'SEK']
    
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
    
    @r_cache_async(f"pvxex:coingecko:allcoins", 300)
    async def load_coins(self) -> dict:
        # If we don't have it in the privex-helpers cache, query the Coingecko API, cache the data and return it.
        data = {}
        async for c_id, c_name, c_symbol in self._load_coins():
            data[c_symbol.upper()] = dict(id=c_id, name=c_name, c_symbol=c_symbol)
        
        return data
    
    async def _load_coins(self) -> AsyncGenerator[Tuple[str, str], None]:
        """
        Used internally by :meth:`.get_tickers`

        Queries the Bittrex market API :attr:`.MARKET_API` asynchronously, and returns
        ``Tuple[str, str]`` objects as an async generator::

            >>> async for frm_coin, to_coin in self._load_coins():
            ...     print(frm_coin, to_coin)

        :return AsyncGenerator[PriceData,None] ticker: An async generator of ticker pairs
        """
        res: List[dict] = await self._query('coins/list')
        for d in res:  # type: dict
            yield d['id'], d['name'], d['symbol']
    
    # noinspection PyTypeChecker
    async def _gen_provides(self, *args, **kwargs) -> Set[Tuple[str, str]]:
        t = await self.load_coins()
        _provides: Set[Tuple[str, str]] = set()
        for k, v in t.items():
            for sym in self.compare_symbols:
                _provides.add((k.upper(), sym.upper(),))
        return _provides
    
    @async_property
    async def provides(self) -> Set[Tuple[str, str]]:
        """
        Coingecko provides ALL of their tickers through one GET query, so we can generate ``provides``
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
    
    async def _query(self, endpoint='') -> Union[list, dict]:
        async with httpx.AsyncClient() as client:
            data = await client.get(f"{self.BASE_API}/{endpoint}", timeout=20)
            try:
                data.raise_for_status()
            except HTTPError as e:
                try:
                    data = e.response.json()
                    raise ExchangeDown(f"{self.name} appears to be down. Error was: {data}")
                except (JSONDecodeError, AttributeError, KeyError):
                    raise ExchangeDown(f"{self.name} appears to be down. Error was: {type(e)} {str(e)}")
        return data.json()

    @r_cache_async(lambda self, from_coin, to_coin: f"pvxex:coingecko:price:{from_coin}:{to_coin}", 30)
    async def _q_price(self, from_coin: str, to_coin: str) -> Decimal:
        from_coin, to_coin = from_coin.upper(), to_coin.upper()
        coins = await self.load_coins()
        c = coins[from_coin]
        
        res: dict = await self._query(f"simple/price?ids={c['id']}&vs_currencies={to_coin.lower()}")
        return Decimal(res[c['id']][to_coin.lower()])
    
    async def _get_pair(self, from_coin: str, to_coin: str) -> PriceData:
        _prov = await self.provides
        pairs: List[str] = [f"{f.upper()}_{v.upper()}" for f, v in _prov]
        from_coin, to_coin = from_coin.upper(), to_coin.upper()
        orig_from, orig_to = from_coin, to_coin
        
        key = f"{from_coin}_{to_coin}"
        if key not in pairs:
            raise PairNotFound(f"The coin pair '{from_coin}/{to_coin}' is not supported by {self.name}")
        
        return PriceData(
            from_coin=orig_from, to_coin=orig_to, last=await self._q_price(from_coin, to_coin)
        )


