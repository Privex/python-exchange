from json import JSONDecodeError
from typing import Set, Tuple, Optional, AsyncGenerator, Dict, List
from async_property import async_property
from httpx import HTTPError
from privex.helpers import cached, empty
from privex.exchange.base import ExchangeAdapter, PriceData
from privex.exchange.exceptions import PairNotFound, ExchangeDown
import httpx

import logging

log = logging.getLogger(__name__)


# @awaitable_class
class ExampleExchange(ExchangeAdapter):
    TICKER_API = 'https://example.com/api/v1/ticker'
    
    name = "Example Exchange"
    code = "example"
    
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
    
    @async_property
    async def tickers(self) -> Dict[str, PriceData]:
        return await self.get_tickers()
    
    async def get_tickers(self) -> Dict[str, PriceData]:
        # First try and get the ticker data from cache
        ckey = f"pvxex:{self.code}:all_tickers"
        cdata = await cached.get(ckey)
        
        if not empty(cdata):
            return cdata
        
        # If we don't have it in the privex-helpers cache, query the API, cache the data and return it.
        data = {}
        async for pd in self._get_tickers():
            # Makes a dictionary map of pair > PriceData
            # e.g. data['BTC_USD'] = PriceData(from_coin='BTC', to_coin='USD', last=Decimal('9001.123'))
            data[f"{pd.from_coin}_{pd.to_coin}"] = pd
        
        await cached.set(ckey, data)
        
        return data
    
    async def _get_tickers(self) -> AsyncGenerator[PriceData, None]:
        """

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
        for d in res:  # type: dict
            yield  # PriceData()
            # yield PriceData(
            #     from_coin=sym.split(b)[0], to_coin=b, last=d.get('lastPrice'), bid=d.get('bidPrice'),
            #     ask=d.get('askPrice'), open=d.get('openPrice'), close=d.get('prevClosePrice'),
            #     high=d.get('highPrice'), low=d.get('lowPrice'), volume=d.get('volume')
            # )
    
    # noinspection PyTypeChecker
    async def _gen_provides(self, *args, **kwargs) -> Set[Tuple[str, str]]:
        return
    
    @async_property
    async def provides(self) -> Set[Tuple[str, str]]:
        """
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
        pass


