import asyncio
from abc import ABC, abstractmethod, abstractproperty
from typing import Set, Union, Optional, Awaitable, Dict, Type, Tuple

import attr
from async_property import AwaitableOnly
from privex.helpers import cached, Tuple, List, AttribDictable, Decimal, empty, camel_to_snake, PrivexException, awaitable, await_if_needed
from privex.helpers.cache import adapter_get, adapter_set, AsyncCacheAdapter, AsyncMemoryCache
import logging
import importlib

from decimal import getcontext

getcontext().prec = 30

log = logging.getLogger(__name__)

_curr_adapter = adapter_get()

if not isinstance(_curr_adapter, AsyncCacheAdapter):
    log.warning("WARNING: Current privex.helpers cache adapter is not an Async adapter.")
    log.warning("Current privex.helpers adapter: %s", _curr_adapter.__class__.__name__)
    log.warning("Setting privex.helpers cache adapter to 'AsyncMemoryCache'.")
    adapter_set(AsyncMemoryCache())


class ExchangeException(PrivexException):
    """Base exception for all exceptions that are part of :mod:`privex.exchange`"""
    pass


class PairNotFound(ExchangeException):
    """Raised when a requested coin pair isn't supported by this exchange adapter"""
    pass


class ProxyMissingPair(PairNotFound):
    """Raised when a requested coin pair required for try_proxy does not exist."""
    pass


class ExchangeDown(ExchangeException):
    """Raised when an exchange appears to be down, e.g. timing out or throwing 4xx / 5xx errors."""
    pass


class ExchangeRateLimited(ExchangeDown):
    """Raised when an exchange adapter encounters a rate limit while querying an exchange"""
    pass


def empty_decimal(obj: Optional[Decimal]):
    if empty(obj): return None
    return Decimal(obj)


@attr.s
class PriceData(AttribDictable):
    """Exchange price data object returned by exchange adapters"""
    from_coin = attr.ib(type=str)
    to_coin = attr.ib(type=str)
    last = attr.ib(type=Decimal, converter=empty_decimal)
    
    bid = attr.ib(default=None, type=Decimal, converter=empty_decimal)
    ask = attr.ib(default=None, type=Decimal, converter=empty_decimal)
    
    open = attr.ib(default=None, type=Decimal, converter=empty_decimal)
    close = attr.ib(default=None, type=Decimal, converter=empty_decimal)
    
    high = attr.ib(default=None, type=Decimal, converter=empty_decimal)
    low = attr.ib(default=None, type=Decimal, converter=empty_decimal)

    volume = attr.ib(default=None, type=Decimal, converter=empty_decimal)


PairListOrSet = Union[List[Tuple[str, str]], Set[List[Tuple[str, str]]]]


class ExchangeAdapter(ABC):
    """Abstract base class used by all exchange adapters for interoperability"""
    cache_timeout: int = 120
    
    _provides: Set[Tuple[str, str]] = set()
    _extra_provides: Set[Tuple[str, str]]
    validate_provides: bool
    ex_settings: dict

    def __str__(self):
        return f"[Exchange '{self.name}' (code: '{self.code}')]'"
    
    def __repr__(self):
        return self.__str__()

    @property
    @abstractmethod
    def name(self) -> str:
        return self.__class__.__name__

    @property
    @abstractmethod
    def code(self) -> str:
        return camel_to_snake(self.name)

    def __init__(self, extra_provides: PairListOrSet = None, validate_provides: bool = True, **ex_settings):
        if not empty(extra_provides, itr=True):
            for p in extra_provides:
                if self.has_pair(*p):
                    continue
                self._extra_provides.add(p)
        
        self.validate_provides = validate_provides
        self.ex_settings = dict(ex_settings)
        
    @property
    @abstractmethod
    def provides(self) -> Union[Set[Tuple[str, str]], Awaitable[Set[Tuple[str, str]]]]:
        return set(list(self._provides) + list(self._extra_provides))

    @abstractmethod
    async def has_pair(self, from_coin: str, to_coin: str) -> bool:
        for f, t in self.provides:
            if f.upper() == from_coin.upper() and t.upper() == to_coin.upper():
                return True
        return False
    
    @abstractmethod
    async def _get_pair(self, from_coin: str, to_coin: str) -> PriceData:
        raise NotImplemented
    
    @staticmethod
    async def _get_cache_pricedata(key: str) -> Optional[PriceData]:
        cdata = cached.get(key)
        if empty(cdata):
            return None
        
        if isinstance(cdata, PriceData):
            return cdata
    
        if isinstance(cdata, dict):
            return PriceData(**cdata)
        
        log.warning("Error reading cache key '%s' - Data was neither PriceData nor dict. Data was: %s", key, cdata)
        return None
    
    async def get_pair(self, from_coin: str, to_coin: str) -> PriceData:
        """
        
        **Instantiate an exchange class and get a ticker asynchronously**::
        
            >>> from privex.exchange import Binance
            >>> b = Binance()
            >>> ticker = await b.get_pair('LTC', 'BTC')
            >>> ticker.last
            Decimal('0.00607100')
            >>> ticker.volume
            Decimal('89557.57000000')
        
        **Can use synchronously in non-async applications**::
        
            >>> from privex.exchange import Binance
            >>> b = Binance()
            >>> ticker = b.get_pair('LTC', 'BTC')
            >>> ticker.last
            Decimal('0.00607100')
        
        
        :param from_coin:
        :param to_coin:
        :return:
        """
        if self.validate_provides:
            if not await self.has_pair(from_coin=from_coin, to_coin=to_coin):
                raise PairNotFound(f"The coin pair '{from_coin}/{to_coin}' is not supported by {self.name}")
        
        code = self.code
        ckey = f"pvxex:{code}:{from_coin}_{to_coin}"
        cdata = await cached.get(ckey)
        if not empty(cdata):
            if isinstance(cdata, PriceData):
                return cdata
        
            if isinstance(cdata, dict):
                return PriceData(**cdata)
            log.warning("Error reading cache key '%s' - Data was neither PriceData nor dict. Data was: %s", ckey, cdata)
            log.warning(f"Will call {self.__class__.__name__}._get_pair and re-write cache key...")
        
        data = await self._get_pair(from_coin=from_coin, to_coin=to_coin)
        await cached.set(ckey, data, self.cache_timeout)
        
        return data


class ExchangeManager:
    """
    
    Basic usage::
    
        >>> from privex.exchange import ExchangeManager
        >>> exm = ExchangeManager()
        >>> await exm.get_pair('btc', 'usd')
        Decimal('6694.53000000')
        >>> await exm.get_pair('ltc', 'usd')
        Decimal('40.15000000')
    
    Converting arbitrary cryptos between each other, seamlessly::
        
        >>> await exm.get_pair('eos', 'ltc')    # LTC per 1 EOS
        Decimal('0.05957304869913275517011340894')
        >>> await exm.get_pair('hive', 'eos')   # EOS per 1 HIVE
        Decimal('0.04325307950727883538633818590')
    
    
    """
    available_adapters: List[Tuple[str, str]] = [
        ('privex.exchange.Binance', 'Binance'),
        ('privex.exchange.Bittrex', 'Bittrex'),
        ('privex.exchange.Kraken', 'Kraken'),
        ('privex.exchange.CoinGecko', 'CoinGecko'),
    ]
    
    ex_instances: Dict[str, ExchangeAdapter] = {}
    ex_code_map: Dict[str, str] = {}
    ex_name_map: Dict[str, str] = {}

    ex_pair_map: Dict[str, List[ExchangeAdapter]] = {}
    ex_pair_map_inv: Dict[ExchangeAdapter, Set[Tuple[str, str]]] = {}

    map_tether_real: bool = True
    
    tether_map = {
        'USDT': 'USD',
        'USDC': 'USD',
    }
    
    proxy_coins = ['BTC', 'USD', 'USDT']
    
    loaded = False

    @classmethod
    async def load_exchange(cls, package: str, name: str) -> ExchangeAdapter:
        obj_path = '.'.join([package, name])
        log.debug("Checking if adapter '%s' is already registered...", obj_path)
        
        if obj_path not in cls.ex_instances:
            log.debug("Importing module '%s'", package)
            # Try importing the package
            pkg = importlib.import_module(package)
            log.debug("Extracting object '%s' from module '%s'", name, package)
            # Then try pulling the object out of the package
            obj: Type[ExchangeAdapter] = pkg.__dict__[name]
            # Instantiate the adapter and add it to the exchange maps
            log.debug("Instantiating object '%s' and mapping it...", obj)
            inst: ExchangeAdapter = obj()
            cls.ex_instances[obj_path] = inst
            cls.ex_code_map[inst.code] = obj_path
            cls.ex_name_map[inst.name] = obj_path
            # Populate ExchangeManager.ex_pair_map
            await cls._import_pairs(inst)

        return cls.ex_instances[obj_path]

    @classmethod
    async def _import_pairs(cls, inst: ExchangeAdapter):
        log.debug("Importing pairs for exchange adapter: %s", inst)
        # Grab the .provides set of tuples from the instance.
        _prov: Union[Set[Tuple[str, str]], Awaitable[Set[Tuple[str, str]]]] = inst.provides
        
        # Some classes may have an async_property .provides, so we need to check if it's a coroutine.
        # If it is a coroutine, then we have to await it before we can scan it.
        # noinspection PyTypeChecker
        if asyncio.iscoroutine(_prov) or asyncio.iscoroutinefunction(_prov) or isinstance(_prov, AwaitableOnly):
            log.debug(f"{inst.__class__.__name__}.provides is async. Awaiting it...")
            _prov = await _prov

        cls.ex_pair_map_inv[inst] = _prov
        # Iterate over each supported coin pair, and append the adapter instance to each pair in ex_pair_map
        for frm_coin, to_coin in _prov:
            cls._map_pair(frm_coin, to_coin, inst)

            if cls.map_tether_real:
                if frm_coin in cls.tether_map.keys():
                    log.debug(
                        "Detected frm_coin '%s' is a tethered coin. Adding extra pair map for %s/%s",
                        frm_coin, cls.tether_map[frm_coin], to_coin
                    )
                    cls._map_pair(cls.tether_map[frm_coin], to_coin, inst)
                elif to_coin in cls.tether_map.keys():
                    log.debug(
                        "Detected to_coin '%s' is a tethered coin. Adding extra pair map for %s/%s",
                        to_coin, frm_coin, cls.tether_map[to_coin]
                    )
                    cls._map_pair(frm_coin, cls.tether_map[to_coin], inst)
        
        return _prov

    @classmethod
    def list_pairs_from(cls, frm_coin: str) -> Dict[str, ExchangeAdapter]:
        return {
            pair: adapters for pair, adapters in cls.ex_pair_map.items()
            if pair.split('_')[0] == frm_coin.upper()
        }

    @classmethod
    def list_pairs_to(cls, to_coin: str) -> Dict[str, ExchangeAdapter]:
        return {
            pair: adapters for pair, adapters in cls.ex_pair_map.items()
            if pair.split('_')[1] == to_coin.upper()
        }
    
    @classmethod
    def _map_pair(cls, frm_coin: str, to_coin: str, inst: ExchangeAdapter):
        k = f"{frm_coin.upper()}_{to_coin.upper()}"
        log.debug("Mapping pair %s for exchange: %s", k, inst)
        if k in cls.ex_pair_map:
            if inst in cls.ex_pair_map[k]:
                log.debug("Exchange already exists in pair map for %s. Exchange: %s", k, inst)
                return
            log.debug("Pair %s exists in ex_pair_map. Appending exchange: %s", k, inst)
        
            cls.ex_pair_map[k].append(inst)
        else:
            log.debug("Pair %s did not exist in ex_pair_map. Creating pair with exchange: %s", k, inst)
            cls.ex_pair_map[k] = [inst]

    @classmethod
    async def load_exchanges(cls):
        for pkg_path, obj_name in cls.available_adapters:
            obj_path = '.'.join([pkg_path, obj_name])
            if obj_path in cls.ex_instances:
                continue
            try:
                await cls.load_exchange(pkg_path, obj_name)
            except:
                log.exception("Skipping adapter %s due to exception ...", obj_path)
        
        cls.loaded = True
    
    @classmethod
    def exchange_by_code(cls, code: str) -> ExchangeAdapter:
        return cls.ex_instances[cls.ex_code_map[code]]

    @classmethod
    def exchange_by_name(cls, name: str) -> ExchangeAdapter:
        return cls.ex_instances[cls.ex_name_map[name]]

    @classmethod
    def exchange_by_path(cls, obj_path: str) -> ExchangeAdapter:
        return cls.ex_instances[obj_path]

    @classmethod
    def pair_exists(cls, from_coin: str, to_coin: str, should_raise=False) -> bool:
        pair = f"{from_coin.upper()}_{to_coin.upper()}"
        if pair in cls.ex_pair_map and len(cls.ex_pair_map[pair]) > 0:
            return True
        
        if should_raise:
            raise PairNotFound(f"Pair '{pair}' does not exist / no usable exchanges in {cls.__name__}.ex_pair_map")
        
        return False
    
    @classmethod
    def _pair_exchanges(cls, from_coin: str, to_coin: str) -> List[ExchangeAdapter]:
        pair = f"{from_coin.upper()}_{to_coin.upper()}"
        if pair not in cls.ex_pair_map:
            raise PairNotFound(f"Pair '{pair}' does not exist in {cls.__name__}.ex_pair_map")
    
        if len(cls.ex_pair_map[pair]) == 0:
            raise PairNotFound(f"Pair '{pair}' has no listed exchanges in {cls.__name__}.ex_pair_map")
        
        return cls.ex_pair_map[pair]
    
    @classmethod
    async def try_proxy(cls, from_coin: str, to_coin: str, proxy: str = "BTC", rate='last', adapter: ExchangeAdapter = None):
        """
        
            >>> exm = ExchangeManager()
            >>> await exm.load_exchanges()
            >>> await exm.try_proxy('HIVE', 'USD', proxy='BTC')
        
        :param from_coin:
        :param to_coin:
        :param proxy:
        :param rate:
        :param adapter:
        :return:
        """
        if not cls.loaded: await cls.load_exchanges()
        from_coin, to_coin, proxy = from_coin.upper(), to_coin.upper(), proxy.upper()
        log.info("Attempting to get '%s' price for %s / %s using proxy coin %s", rate, from_coin, to_coin, proxy)
        
        inv_to = False
        
        if adapter:
            log.debug("Custom adapter was specified. Proxying exclusively via: %s", adapter)
        
        pair_exists = cls.pair_exists if adapter is None else adapter.has_pair
        get_ticker = cls._get_ticker if adapter is None else adapter.get_pair

        if not await await_if_needed(pair_exists, from_coin, proxy):
            raise ProxyMissingPair(f"No pairs available for {from_coin} -> {proxy}")
        if not await await_if_needed(pair_exists, proxy, to_coin):
            log.debug("Did not find pair %s/%s - checking if we can do inverted %s/%s", proxy, to_coin, to_coin, proxy)
            if await await_if_needed(pair_exists, to_coin, proxy):
                log.debug("Found inverted proxy %s/%s", to_coin, proxy)
                inv_to = True
            else:
                raise ProxyMissingPair(f"No pairs available for {proxy} -> {to_coin}")
        
        # pair = f"{from_coin}_{to_coin}"
        
        # e.g. if from=HIVE, to=USD, proxy=BTC
        # get ticker for HIVE/BTC - get ticker for USD/BTC
        # e.g. HIVE/BTC = 0.00001545    BTC/USD = 6900
        # 0.00001545 * 6900 = 0.106605 USD per HIVE
        ex_from = await get_ticker(from_coin, proxy)
        if inv_to:
            ex_to = await get_ticker(to_coin, proxy)
            log.debug("Original rates from reverse proxy %s/%s - rates: %s", to_coin, proxy, ex_to)
            ex_to = ExchangeManager._invert_data(ex_to)
            log.debug("Inverted rates - converted pair into %s/%s : %s", proxy, to_coin, ex_to)
        else:
            ex_to = await get_ticker(proxy, to_coin)

        r_from, r_to = Decimal(ex_from[rate]), Decimal(ex_to[rate])
        
        log.debug(f"{from_coin}/{proxy} price: {r_from:.8f} {proxy} per 1 {from_coin}")
        log.debug(f"{proxy}/{to_coin} price: {r_to:.8f} {to_coin} per 1 {proxy}")
        log.debug(f"{r_from} * {r_to} = %f", r_from * r_to)
        return r_from * r_to
    
    @staticmethod
    def _invert_data(data: PriceData):
        inv_keys = ['last', 'bid', 'ask', 'open', 'close', 'high', 'low', 'volume']
        new_pd = PriceData(**dict(data))
        
        # Invert each ticker price, e.g. for BTC/USD into USD/BTC
        for k in inv_keys:
            if empty(new_pd[k], zero=True):
                continue
            setattr(new_pd, k, Decimal('1') / new_pd[k])
        
        # Atomic swap from_coin and to_coin with eachother
        new_pd.from_coin, new_pd.to_coin = new_pd.to_coin, new_pd.from_coin
        
        return new_pd
    
    @classmethod
    async def _get_ticker(cls, from_coin: str, to_coin: str, ex_index: int = 0) -> PriceData:
        if not cls.loaded: await cls.load_exchanges()
        from_coin, to_coin = from_coin.upper(), to_coin.upper()
        
        try:
            cls.pair_exists(from_coin, to_coin, should_raise=True)
        except PairNotFound:
            log.info("Pair %s/%s was not found. Trying inverse query using %s/%s", from_coin, to_coin, to_coin, from_coin)
            cls.pair_exists(to_coin, from_coin, should_raise=True)
            
            adp = cls.ex_pair_map[f"{to_coin}_{from_coin}"][ex_index]
            return ExchangeManager._invert_data(await adp.get_pair(to_coin, from_coin))
        
        adp = cls.ex_pair_map[f"{from_coin}_{to_coin}"][ex_index]
        log.info("Found pair %s/%s - querying exchange: %s", from_coin, to_coin, adp)
        return await adp.get_pair(from_coin, to_coin)

    @classmethod
    async def get_tickers(cls, from_coin: str, to_coin: str, rate='last') -> Dict[str, Decimal]:
        if not cls.loaded: await cls.load_exchanges()
        from_coin, to_coin = from_coin.upper(), to_coin.upper()
        data = {}
        
        for _, adp in cls.ex_instances.items(): # type: ExchangeAdapter
            if await adp.has_pair(from_coin, to_coin):
                try:
                    d = await adp.get_pair(from_coin, to_coin)
                    data[adp.code] = d[rate]
                except Exception as e:
                    log.warning(
                        "Error obtaining %s/%s exchange rate from %s - reason: %s %s",
                        from_coin, to_coin, adp.name, type(e), str(e)
                    )
            elif await adp.has_pair(to_coin, from_coin):
                log.info("Pair %s/%s was not found. Trying inverse query using %s/%s", from_coin, to_coin, to_coin, from_coin)
                try:
                    data[adp.code] = ExchangeManager._invert_data(await adp.get_pair(to_coin, from_coin))[rate]
                except Exception as e:
                    log.warning(
                        "Error obtaining %s/%s exchange rate from %s - reason: %s %s",
                        from_coin, to_coin, adp.name, type(e), str(e)
                    )
            else:
                try:
                    proxy = await cls._find_proxy(from_coin, to_coin, adapter=adp)
                    data[adp.code] = await cls.try_proxy(from_coin, to_coin, proxy, adapter=adp)
                except (ProxyMissingPair, PairNotFound):
                    log.warning(
                        "Error obtaining %s/%s exchange rate from %s - cannot find a proxy pair.",
                        from_coin, to_coin, adp.name
                    )
            
        return data
        # data = {}
        # try:
        #     cls.pair_exists(from_coin, to_coin, should_raise=True)
        # except PairNotFound:
        #     log.info("Pair %s/%s was not found. Trying inverse query using %s/%s", from_coin, to_coin, to_coin, from_coin)
        #     cls.pair_exists(to_coin, from_coin, should_raise=True)
        #     for adp in cls.ex_pair_map[f"{to_coin}_{from_coin}"]:
        #         data[adp.code] = ExchangeManager._invert_data(await adp.get_pair(to_coin, from_coin))[rate]
        #     return data
        #
        # for adp in cls.ex_pair_map[f"{from_coin}_{to_coin}"]:
        #     d = await adp.get_pair(from_coin, to_coin)
        #     data[adp.code] = d[rate]
        #
        # return data

    @classmethod
    async def _find_proxy(cls, from_coin: str, to_coin: str, adapter: ExchangeAdapter = None) -> str:
        """
        
            >>> await cls._find_proxy('HIVE', 'USD')
            'BTC'
        
        :param from_coin:
        :param to_coin:
        :return:
        """
        if not cls.loaded: await cls.load_exchanges()
        from_coin, to_coin = from_coin.upper(), to_coin.upper()

        for c in cls.proxy_coins:
            if adapter:
                if not await adapter.has_pair(from_coin, c): continue
                if await adapter.has_pair(c, to_coin): return c
                if await adapter.has_pair(to_coin, c): return c
                continue
            
            if f"{from_coin}_{c}" not in cls.ex_pair_map:
                log.debug("Cannot proxy via %s - pair %s not found", c, f"{from_coin}_{c}")
                continue
            
            if f"{c}_{to_coin}" in cls.ex_pair_map:
                log.debug("Found forward proxy via %s - pair %s found", c, f"{c}_{to_coin}")
                return c
            
            if f"{to_coin}_{c}" in cls.ex_pair_map:
                log.debug("Found reverse proxy via %s - pair %s found", c, f"{to_coin}_{c}")
                return c
        raise ProxyMissingPair(f"Could not find a viable proxy route for {from_coin} -> {to_coin}")
    
    async def get_pair(self, from_coin: str, to_coin: str, rate='last', use_proxy: bool = True):
        if not self.loaded:
            await self.load_exchanges()
        
        pair = f"{from_coin.upper()}_{to_coin.upper()}"
        
        if pair not in self.ex_pair_map:
            if not use_proxy:
                raise PairNotFound(f"Pair {pair} was not found in ex_pair_map, and no proxying requested.")
            try:
                log.debug("Pair %s not found - trying to find a proxy route...", pair)
                proxy = await self._find_proxy(from_coin, to_coin)
                log.debug("Found proxy to %s via %s - trying proxy...", to_coin, proxy)
                rate_proxy = await self.try_proxy(from_coin, to_coin, proxy, rate=rate)
                log.debug("Got proxy rate: %f %s per %s", rate_proxy, to_coin, from_coin)
                return rate_proxy
            except ProxyMissingPair:
                raise PairNotFound(f"Pair {pair} not found, nor a viable proxy route.")
        
        adp = self.ex_pair_map[pair][0]
        log.debug("Pair %s found - getting exchange rate directly", pair)

        data = await adp.get_pair(from_coin, to_coin)
        return data[rate]


__all__ = [
    'PairNotFound', 'ExchangeRateLimited', 'ExchangeException', 'ExchangeAdapter', 'ExchangeDown', 'PriceData',
    'ExchangeManager'
]
