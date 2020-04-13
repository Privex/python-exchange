from json import JSONDecodeError
from typing import Set, Tuple, Optional, AsyncGenerator, Dict, List

from async_property import async_property
from httpx import HTTPError
from privex.helpers import cached, empty, awaitable_class

from privex.exchange.base import ExchangeAdapter, PriceData, ExchangeDown, PairNotFound
import httpx

import logging

log = logging.getLogger(__name__)


@awaitable_class
class Binance(ExchangeAdapter):
    TICKER_API = 'https://api.binance.com/api/v1/ticker/24hr'
    
    name = "Binance"
    code = "binance"
    
    known_bases = [
        "BTC", "USDT", "USDC",
        "BUSD", "TUSD", "USD",
        "ETH", "TRX", "XRP",
        "PAX", "BKRW", "EUR",
        "NGN", "RUB", "TRY",
        "ZAR"
    ]
    
    _provides = set()
    _extra_provides = set()

    def _find_base(self, pair: str) -> Optional[str]:
        pair = pair.upper()
        for b in self.known_bases:
            if pair.endswith(b):
                return b
        return None

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

    @async_property
    async def tickers(self) -> Dict[str, PriceData]:
        return await self.get_tickers()

    async def get_tickers(self) -> Dict[str, PriceData]:
        # First try and get the ticker data from cache
        ckey = f"pvxex:{self.code}:all_tickers"
        cdata = await cached.get(ckey)
        
        if not empty(cdata):
            return cdata
        
        # If we don't have it in the privex-helpers cache, query the Binance API, cache the data and return it.
        data = {}
        async for pd in self._get_tickers():
            # Makes a dictionary map of pair > PriceData
            # e.g. data['BTC_USD'] = PriceData(from_coin='BTC', to_coin='USD', last=Decimal('9001.123'))
            data[f"{pd.from_coin}_{pd.to_coin}"] = pd
            # if pd.from_coin == 'USDT':
            #     data[f"USD_{pd.to_coin}"] = pd
            # elif pd.to_coin == 'USDT':
            #     data[f"{pd.from_coin}_USD"] = pd

        await cached.set(ckey, data)
        
        return data

    async def _get_tickers(self) -> AsyncGenerator[PriceData, None]:
        """
        Used internally by :meth:`.get_tickers`
        
        Queries the Binance 24hr ticker API :attr:`.TICKER_API` asynchronously, and returns
        :class:`.PriceData` objects as an async generator (``async for x in self._get_tickers()``)
        
        :return AsyncGenerator[PriceData,None] ticker: An async generator of :class:`.PriceData` tickers
        """
        # Query the Binance API and obtain the ticker data as a list of dictionaries
        async with httpx.AsyncClient() as client:
            data = await client.get(self.TICKER_API, timeout=20)
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
            sym: str = d['symbol']
            # Binance pairs are formatted like 'BTCUSD', so we need to scan the pair to figure out what
            # the 'to_coin' symbol actually is, then we can extract the from_coin.
            b = self._find_base(sym)
            if b is None:
                log.debug("Skipping symbol '%s' as could not identify base symbol of pair...", sym)
                continue
            
            yield PriceData(
                from_coin=sym.split(b)[0], to_coin=b, last=d.get('lastPrice'), bid=d.get('bidPrice'),
                ask=d.get('askPrice'), open=d.get('openPrice'), close=d.get('prevClosePrice'),
                high=d.get('highPrice'), low=d.get('lowPrice'), volume=d.get('volume')
            )

    # noinspection PyTypeChecker
    async def _gen_provides(self, *args, **kwargs) -> Set[Tuple[str, str]]:
        t = await self.get_tickers()
        _provides: Set[Tuple[str, str]] = set()
        for k, _ in t.items():
            _provides.add(tuple(k.split('_')))
        return _provides

    @async_property
    async def provides(self) -> Set[Tuple[str, str]]:
        """
        Binance provides ALL of their tickers through one GET query, so we can generate ``provides``
        simply by querying their API via :meth:`._get_tickers` (using :meth:`._gen_provides`)
        
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

    async def _get_pair(self, from_coin: str, to_coin: str) -> PriceData:
        tickers = await self.tickers
        from_coin, to_coin = from_coin.upper(), to_coin.upper()
        key = f"{from_coin}_{to_coin}"
        if key not in tickers:
            if from_coin == 'USD': key = f"USDT_{to_coin}"
            if to_coin == 'USD': key = f"{from_coin}_USDT"
            if key in tickers: return tickers[key]
            
            if from_coin == 'USD': key = f"USDC_{to_coin}"
            if to_coin == 'USD': key = f"{from_coin}_USDC"
            if key in tickers: return tickers[key]
            
            raise PairNotFound(f"The coin pair '{from_coin}/{to_coin}' is not supported by {self.name}")
        
        return tickers[key]
        

