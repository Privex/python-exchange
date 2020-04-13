from json import JSONDecodeError
from typing import Set, Tuple, Optional, AsyncGenerator, Dict, List, Union

from async_property import async_property
from httpx import HTTPError
from privex.helpers import cached, empty, awaitable_class, r_cache_async

from privex.exchange.base import ExchangeAdapter, PriceData, ExchangeDown, PairNotFound
import httpx

import logging

log = logging.getLogger(__name__)


@awaitable_class
class Kraken(ExchangeAdapter):
    TICKER_API = 'https://api.kraken.com/0/public'
    
    name = "Kraken"
    code = "kraken"

    symbol_map_expected = {
        'DOGE': ['XDG', 'XXDG'],
        'BTC': ['XXBT', 'XBT'],
        'XBT': ['XXBT', 'XBT'],
        'LTC': ['XLTC', 'LTC'],
        'ETH': ['XETH', 'ETH'],
        'ETC': ['XETC', 'ETC'],
        'XRP': ['XXRP', 'XRP'],
        'XMR': ['XXMR', 'XMR'],
        'USD': ['ZUSD', 'USD', 'USDT', 'USDC'],
        'EUR': ['ZEUR', 'EUR'],
        'GBP': ['ZGBP', 'GBP'],
        'CAD': ['ZCAD', 'CAD'],
        'JPY': ['ZJPY', 'JPY'],
    }
    """
    Kraken's asset pairs are very inconsistent, so this dictionary maps "sane" symbols, to the various symbols
    kraken's asset pairs use, allowing :func:`.get_ticker` to "guess" the symbol combination by trying each
    symbol until it figures out the correct symbol combination for a pair.
    """
    symbol_map = {
        'XXDG': 'DOGE',
        'XDG': 'DOGE',
        'XXBT': 'BTC',
        'XBT': 'BTC',
        'XLTC': 'LTC',
        'ZUSD': 'USD',
        'ZEUR': 'EUR',
        'ZGBP': 'GBP',
        'ZJPY': 'JPY',
    }

    @property
    def symbol_map_inverted(self) -> List[Tuple[str, str]]:
        return [
            (y, x) for x, y in self.symbol_map.items()
        ]

    known_bases = list(symbol_map.keys()) + [
        "BTC", "ETH", "USDT", "USDC",
        "USD", "GBP", "EUR", "JPY",
        "CAD", "CHF", "DAI"
    ]
    
    known_pairs = {
        "BTC_USD": "XXBTZUSD", "LTC_USD": "XLTCZUSD", "ETH_USD": "XETHZUSD",
        "BTC_EUR": "XXBTZEUR", "LTC_EUR": "XLTCZEUR", "ETH_EUR": "XETHZEUR",
        "BTC_GBP": "XXBTZGBP", "LTC_GBP": "XLTCZGBP", "ETH_GBP": "XETHZGBP",
        "EOS_USD": "EOSUSD", "EOS_BTC": "EOSXBT",
        "LTC_BTC": "XLTCXXBT", "ETH_BTC": "XETHXXBT",
        "USD_EUR": "USDTEUR", "USD_GBP": "USDTGBP", "USD_CAD": "USDTCAD",
    }
    """
    Kraken has extremely inconsistent pairs, so we map some of the most common pairs in "sane" format,
    to the format Kraken expects.
    
    If the class doesn't have a registered "known pair", it falls back to brute forcing the pair
    via :attr:`.symbol_map_expected`
    """
    
    _provides = set()
    _extra_provides = set()

    async def _query(self, endpoint='') -> Union[list, dict]:
        url = f"{self.TICKER_API}/{endpoint}"
        async with httpx.AsyncClient() as client:
            data = await client.get(url, timeout=20)
            try:
                data.raise_for_status()
            except HTTPError as e:
                try:
                    data = e.response.json()
                    raise ExchangeDown(f"{self.name} appears to be down. Error was: {data}")
                except (JSONDecodeError, AttributeError, KeyError):
                    raise ExchangeDown(f"{self.name} appears to be down. Error was: {type(e)} {str(e)}")
        j = data.json()
        if not empty(j.get('error'), zero=True, itr=True):
            raise ExchangeDown(f"Error querying {self.name} URL '{url}' - Error is: {j['error']}")
        return j
    
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
        # if from_coin == 'BTC': from_coin = 'XBT'
        # if to_coin == 'BTC': to_coin = 'XBT'
        if f"{from_coin}_{to_coin}" in pairs:
            return True

        if to_coin == 'BTC' and f"{from_coin}_XBT" in pairs:
            return True
        if from_coin == 'USD' and (f"USDT_{to_coin}" in pairs or f"USDC_{to_coin}" in pairs):
            return True
        if to_coin == 'USD' and (f"{from_coin}_USDT" in pairs or f"{from_coin}_USDC" in pairs):
            return True
        
        return False

    @r_cache_async(f"pvxex:kraken:all_pairs", 300)
    async def load_pairs(self) -> List[str]:
        # If we don't have it in the privex-helpers cache, query the Bittrex API, cache the data and return it.
        data = []
        async for pair in self._load_pairs():
            # Kraken pairs are formatted like 'BTCUSD', so we need to scan the pair to figure out what
            # the 'to_coin' symbol actually is, then we can extract the from_coin.
            b = self._find_base(pair)
            if b is None:
                log.debug("Skipping symbol '%s' as could not identify base symbol of pair...", pair)
                continue
            from_coin, to_coin = pair.split(b)[0], b
            if b in self.symbol_map:
                to_coin = self.symbol_map[b]
            if from_coin in self.symbol_map:
                from_coin = self.symbol_map[from_coin]
            data += [f"{from_coin.upper()}_{to_coin.upper()}"]
    
        # await cached.set(ckey, data)
    
        return data

    async def _load_pairs(self) -> AsyncGenerator[str, None]:
        """
        Used internally by :meth:`.get_tickers`

        Queries the Bittrex market API :attr:`.MARKET_API` asynchronously, and returns
        ``Tuple[str, str]`` objects as an async generator::

            >>> async for frm_coin, to_coin in self._load_pairs():
            ...     print(frm_coin, to_coin)

        :return AsyncGenerator[PriceData,None] ticker: An async generator of ticker pairs
        """
        res = await self._query('AssetPairs?info=fees')
        # Loop over each ticker dictionary and return the pair
        for k, v in res['result'].items():  # type: dict
            yield k

    async def _get_ticker(self, pair: str):
        res = await self._query(f'Ticker?pair={pair}')
        res: dict = res['result']
        res = res[list(res.keys())[0]]
        
        return PriceData(
            from_coin=pair, to_coin=pair,
            ask=res['a'][0], bid=res['b'][0], last=res['c'][0],
            open=res['o'], low=res['l'][0], high=res['h'][0],
            volume=res['v'][0]
        )

    async def get_ticker(self, from_coin: str, to_coin: str) -> PriceData:
        from_coin, to_coin = from_coin.upper(), to_coin.upper()
        if f"{from_coin}_{to_coin}" in self.known_pairs:
            
            xpair = self.known_pairs[f"{from_coin}_{to_coin}"]
            log.debug(
                "Using known Kraken pair for %s/%s: '%s'",
                from_coin, to_coin, xpair
            )
            return await self._get_ticker(xpair)
        
        # If we don't have "expected" kraken symbols mapped for the given coins, fallback to the user specified symbols
        from_coins = [from_coin]
        to_coins = [to_coin]
        
        # If we know kraken expects certain symbols for from_coin/to_coin, use those instead of the user's symbol.
        if from_coin in self.symbol_map_expected:
            from_coins = self.symbol_map_expected[from_coin]
        if to_coin in self.symbol_map_expected:
            to_coins = self.symbol_map_expected[to_coin]
        
        # "brute force" the correct Kraken pair, because Kraken's pairs are very inconsistent :)
        for fc in from_coins:
            for tc in to_coins:
                try:
                    log.debug("Trying guessed kraken pair %s/%s", fc, tc)
                    res = await self._get_ticker(f"{fc}{tc}")
                    res.from_coin, res.to_coin = from_coin, to_coin
                    log.debug(
                        "Correct Kraken pair for %s/%s is: '%s%s' - caching this pair map into known_pairs",
                        from_coin, to_coin, fc, tc
                    )
                    self.known_pairs[f"{from_coin}_{to_coin}"] = f"{fc}{tc}"
                    return res
                except ExchangeDown:
                    log.debug("Pair %s/%s appears to be invalid. Trying next pair combo.", fc, tc)
        # Our brute force attempt failed. We have no clue what the correct Kraken pair is, whether the exchange
        # is broken, or the pair just outright doesn't exist...
        raise ExchangeDown("Cannot figure out pair for %s/%s or %s is actually down...", from_coin, to_coin, self.name)

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
        Kraken provides ALL of their tickers through one GET query, so we can generate ``provides``
        simply by querying their API via :meth:`.load_pairs` (using :meth:`._gen_provides`)

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
        from_coin, to_coin = from_coin.upper(), to_coin.upper()
        return await self.get_ticker(from_coin, to_coin)


