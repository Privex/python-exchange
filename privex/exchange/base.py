import asyncio
import attr
import logging
import importlib
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Set, Union, Optional, Awaitable, Dict, Type, Tuple, List
from decimal import Decimal, getcontext
from async_property import AwaitableOnly, async_property
from privex.helpers import AttribDictable, empty, camel_to_snake, await_if_needed, dec_round, r_cache_async, empty_if
from privex.helpers.cache import async_adapter_get, async_adapter_set, AsyncCacheAdapter, AsyncMemoryCache
from privex.exchange.exceptions import PairNotFound, ProxyMissingPair
from privex.exchange.helpers import med_avg_out, avg, empty_decimal, PairListOrSet

getcontext().prec = 30

log = logging.getLogger(__name__)

ZERO, ONE, TWO = Decimal('0'), Decimal('1'), Decimal('2')
_curr_adapter = async_adapter_get()

if not isinstance(_curr_adapter, AsyncCacheAdapter):
    log.warning("WARNING: Current privex.helpers cache adapter is not an Async adapter.")
    log.warning("Current privex.helpers adapter: %s", _curr_adapter.__class__.__name__)
    log.warning("Setting privex.helpers cache adapter to 'AsyncMemoryCache'.")
    async_adapter_set(AsyncMemoryCache())

cached = async_adapter_get()
# cached = async_cached
# cached.ins_exit_close = False
# cached.ins_enter_reconnect = False


def disable_cache_context_reset():
    try:
        from privex.helpers.cache import AsyncRedisCache
        if isinstance(cached, AsyncRedisCache):
            cached.ins_exit_close = False
            cached.ins_enter_reconnect = False
        AsyncRedisCache.adapter_enter_reconnect = False
        AsyncRedisCache.adapter_exit_close = False
    except ImportError:
        pass


disable_cache_context_reset()


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
    def cache(self) -> AsyncCacheAdapter:
        return cached
    
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
        with cached:
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
    
    **Basic Usage**
    
    First create an :class:`.ExchangeManager` instance::
    
        >>> from privex.exchange import ExchangeManager
        >>> exm = ExchangeManager()
    
    Using :meth:`.get_avg` - we can get the average price for a given coin pair based on all exchanges which support that pair, as well
    as exchanges which have a proxy route (e.g. ``LTC -> BTC -> USD``)::
    
        >>> await exm.get_avg('btc', 'usd')
        Decimal('9252.50525000')
    
    You can also use :meth:`.get_pair`, which simply finds the simplest route (including proxies) via one or two exchanges to
    obtain a price::
    
        >>> await exm.get_pair('btc', 'usd')
        Decimal('9249.03000000')
        >>> await exm.get_pair('ltc', 'usd')
        Decimal('43.88000000')
    
    Converting arbitrary cryptos between each other, seamlessly::
    
        >>> await exm.get_avg('eos', 'ltc')     # LTC per 1 EOS (average via all exchanges)
        Decimal('0.0580638770094616213117276469457')
        >>> await exm.get_pair('eos', 'ltc')    # LTC per 1 EOS (direct / semi-direct)
        Decimal('0.05957304869913275517011340894')
        >>> await exm.get_avg('hive', 'eos')   # EOS per 1 HIVE
        Decimal('0.0878733984247395738811658379006')
    
    
    """
    available_adapters: List[Tuple[str, str]] = [
        ('privex.exchange.Binance', 'Binance'),
        ('privex.exchange.Bittrex', 'Bittrex'),
        ('privex.exchange.Kraken', 'Kraken'),
        ('privex.exchange.Huobi', 'Huobi'),
        ('privex.exchange.CoinGecko', 'CoinGecko'),
        ('privex.exchange.SteemEngine', 'SteemEngine'),
        ('privex.exchange.SteemEngine', 'HiveEngine'),
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
    
    proxy_coins = ['BTC', 'USD', 'USDT', 'HIVE', 'STEEM']
    common_proxies = ['BTC', 'USD']
    _proxy_rates: Dict[str, Decimal] = {}
    proxy_rates_timestamp: Optional[datetime] = None
    proxy_rates_timeout: Union[int, float] = 300
    
    loaded = False

    def __init__(self):
        disable_cache_context_reset()
        if getcontext().prec is None or getcontext().prec < 30:
            getcontext().prec = 30

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
    async def reload_all_pairs(cls):
        for obj_path, inst in cls.ex_instances.items():
            log.debug("Reloading pairs for adapter %s", obj_path)
            await cls._import_pairs(inst)
        log.debug("Finished reloading all provider pairs")
        return cls.ex_pair_map

    @classmethod
    async def reload_inst_pairs(cls, obj_path: str):
        inst = cls.ex_instances[obj_path]
        return await cls._import_pairs(inst)

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
        coros = []
        for pkg_path, obj_name in cls.available_adapters:
            obj_path = '.'.join([pkg_path, obj_name])
            if obj_path in cls.ex_instances:
                continue
            coros.append(cls.load_exchange(pkg_path, obj_name))
            # try:
            # except:
            #     log.exception("Skipping adapter %s due to exception ...", obj_path)
        if len(coros) > 0:
            await asyncio.gather(*coros, return_exceptions=True)
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
    async def get_proxy_avg(cls, from_coin: str, to_coin: str) -> Decimal:
        """
        Attempt to retrieve the average exchange rate for ``from_coin/to_coin`` using the proxy coin averages, which
        are retrieved and cached from :meth:`.get_proxy_rates`
        
            >>> await ExchangeManager.get_proxy_avg('BTC', 'USD')
            Decimal('9194.89249999')
        
            >>> await ExchangeManager.get_proxy_avg('HIVE', 'USD')
            Decimal('0.21594933')
            >>> await ExchangeManager.get_proxy_avg('USD', 'HIVE')
            
        :param from_coin:
        :param to_coin:
        :return:
        """
        pr = await cls.get_proxy_rates()
        from_coin, to_coin = from_coin.upper(), to_coin.upper()
        if f"{from_coin}_{to_coin}" in pr:
            return pr[f"{from_coin}_{to_coin}"]
        if f"{to_coin}_{from_coin}" in pr:
            return ONE / pr[f"{to_coin}_{from_coin}"]
        raise ProxyMissingPair(f"Could not find average proxy rate for {from_coin}/{to_coin}")
    
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
        try:
            ex_from = {rate: await cls.get_proxy_avg(from_coin=from_coin, to_coin=proxy)}
        except ProxyMissingPair:
            ex_from = await get_ticker(from_coin, proxy)
        if inv_to:
            try:
                ex_to = {rate: await cls.get_proxy_avg(from_coin=to_coin, to_coin=proxy)}
            except ProxyMissingPair:
                ex_to = await get_ticker(to_coin, proxy)
            log.debug("Original rates from reverse proxy %s/%s - rates: %s", to_coin, proxy, ex_to)
            ex_to = ExchangeManager._invert_data(ex_to)
            log.debug("Inverted rates - converted pair into %s/%s : %s", proxy, to_coin, ex_to)
        else:
            try:
                ex_to = {rate: await cls.get_proxy_avg(from_coin=proxy, to_coin=to_coin)}
            except ProxyMissingPair:
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
    
    @async_property
    async def proxy_rates(self) -> Dict[str, Decimal]:
        """This is just an AsyncIO property for :meth:`.get_proxy_rates`"""
        return await self.get_proxy_rates()
    
    @classmethod
    @r_cache_async(lambda cls: f"pvxex:exm:proxy_rates:{','.join(cls.proxy_coins)}", cache_time=proxy_rates_timeout)
    async def get_proxy_rates(cls) -> Dict[str, Decimal]:
        """
        Retrieves and caches proxy rates from :meth:`.prep_proxy_rates`
        """
        pr = await cls.prep_proxy_rates()
        return pr
    
    @classmethod
    async def prep_proxy_rates(cls) -> Dict[str, Decimal]:
        """
        Internal usage. Initialises / updates :attr:`._proxy_rates` with string coin pairs mapped to their exchange rate.
        
        
        Sets :attr:`._proxy_rates` and returns a dictionary of proxy coin pairs mapped to their ex rate::
        
            {'BTC_USD': Decimal('9183.20224999'), 'BTC_USDT': Decimal('9190.78333333'), 'BTC_HIVE': Decimal('42500.00000000'),
             'BTC_STEEM': Decimal('44900.00000000'), 'USD_USDT': Decimal('1.00085000'), 'USDT_BTC': Decimal('0.00010869'),
             'USDT_USD': Decimal('0.99920000'), 'HIVE_BTC': Decimal('0.00002362'), 'HIVE_USD': Decimal('0.21596266'),
             'HIVE_USDT': Decimal('0.21577000'), 'HIVE_STEEM': Decimal('1.06000100'), 'STEEM_BTC': Decimal('0.00002231'),
             'STEEM_USD': Decimal('0.20394399'), 'STEEM_HIVE': Decimal('0.92999999')
             }
        
        """
        if not cls.loaded: await cls.load_exchanges()
        
        # ex_rates: Dict[str, Dict[str, Decimal]] = {}
        ex_rates_avg: Dict[str, Decimal] = {}
        
        rate_coros = []
        
        async def x_rates(f, t):
            rates = await cls.get_all_rates(from_coin=f, to_coin=t)
            return f"{f}_{t}", rates
        
        for frm in cls.proxy_coins:
            for to in cls.proxy_coins:
                if frm == to: continue
                rate_coros.append(x_rates(frm, to))
                # pair = f"{frm}_{to}"
                # for _, adp in cls.ex_instances.items():
                #     try:
                #         if not await adp.has_pair(frm, to): continue
                #         if pair not in ex_rates:
                #             ex_rates[pair] = {}
                #         log.debug(f"Getting proxy rate for {pair} from exchange '{adp.code}'")
                #         pd = await adp.get_pair(from_coin=frm, to_coin=to)
                #         if empty(pd.last, zero=True):
                #             raise ValueError(f"Price data 'last' from exchage '{adp.code}' was empty / zero!")
                #         ex_rates[pair][adp.code] = pd.last
                #     except Exception as e:
                #         log.warning(f"Failed to get {pair} from exchange '{adp.code}'. Reason: %s %s", type(e), str(e))
        
        rate_res = await asyncio.gather(*rate_coros, return_exceptions=True)
        # for p, rates in ex_rates.items():
        for res in rate_res:
            if not isinstance(res, tuple): continue
            
            if len(res[1].values()) < 1:
                # log.debug("Pair %s has no values. Skipping.", p)
                continue
            ex_rates_avg[res[0]] = med_avg_out(*res[1].values())
            log.debug("Average rate for %s is %f - based on: %s", res[0], ex_rates_avg[res[0]], res[1])
        
        log.debug("Got proxy averages: %s", ex_rates_avg)
        cls._proxy_rates = ex_rates_avg
        return cls._proxy_rates
    
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
    
    @classmethod
    async def get_all_rates(cls, from_coin: str, to_coin: str, rate='last', invert=False):
        if not cls.loaded: await cls.load_exchanges()
        from_coin, to_coin = from_coin.upper(), to_coin.upper()
        # frm, to = from_coin, to_coin
        pair = f"{from_coin}_{to_coin}"
        ex_rates = {}
        
        async def _get_rate(frm, to, adp, rate_key):
            try:
                if not await adp.has_pair(frm, to): return None
                # if pair not in ex_rates: ex_rates[pair] = {}
                log.debug(f"Getting rate for {pair} from exchange '{adp.code}'")
                pd = await adp.get_pair(from_coin=frm, to_coin=to)
                if empty(pd.last, zero=True):
                    raise ValueError(f"Price data 'last' from exchange '{adp.code}' was empty / zero!")
                # ex_rates[adp.code] = pd[rate]
                return adp.code, pd[rate_key]
            except Exception as e:
                log.warning(f"Failed to get {pair} from exchange '{adp.code}'. Reason: %s %s", type(e), str(e))
                return None
        
        rate_tasks = [_get_rate(from_coin, to_coin, adapter, rate) for adapter in cls.ex_instances.values()]
        rate_res = await asyncio.gather(*rate_tasks, return_exceptions=True)
        
        for r in rate_res:
            if not isinstance(r, tuple): continue
            ex_rates[r[0]] = ONE / r[1] if invert else r[1]
        # for _, adapter in cls.ex_instances.items():
        #     try:
        #         if not await adp.has_pair(frm, to): continue
        #         # if pair not in ex_rates: ex_rates[pair] = {}
        #         pd = await adp.get_pair(from_coin=frm, to_coin=to)
        #         if empty(pd.last, zero=True):
        #             raise ValueError(f"Price data 'last' from exchage '{adp.code}' was empty / zero!")
        #         ex_rates[adp.code] = pd[rate]
        #         log.debug(f"Getting rate for {pair} from exchange '{adp.code}'")
        #     except Exception as e:
        #         log.warning(f"Failed to get {pair} from exchange '{adp.code}'. Reason: %s %s", type(e), str(e))
        log.debug("All rates (inverted: %s) for %s/%s: %s", invert, from_coin, to_coin, ex_rates)
        return ex_rates
    
    @classmethod
    async def get_direct_rate_avg(cls, from_coin: str, to_coin: str, rate='last', invert=False) -> Optional[Decimal]:
        if rate == 'last':
            try:
                r = await cls.get_proxy_avg(from_coin, to_coin)
                return ONE / r if invert else r
            except ProxyMissingPair:
                pass
        # proxy_rates = await cls.get_proxy_rates()
        # pair, inv_pair = f"{from_coin}_{to_coin}", f"{to_coin}_{from_coin}"
        # if pair in proxy_rates:
        #     return ONE / proxy_rates[pair] if invert else proxy_rates[pair]
        # if inv_pair in proxy_rates:
        #     return proxy_rates[inv_pair] if invert else ONE / proxy_rates[inv_pair]
        
        rates = await cls.get_all_rates(from_coin, to_coin, rate=rate, invert=invert)
        if len(rates) < 1:
            return None
        return med_avg_out(*rates.values())
    
    @classmethod
    async def _get_avg_proxy(cls, from_coin: str, to_coin: str, proxy: str = 'BTC', fail=False, rate='last') -> Optional[Decimal]:
        if not cls.loaded: await cls.load_exchanges()
        from_coin, to_coin, proxy = from_coin.upper(), to_coin.upper(), proxy.upper()
        
        # To make the below proxy routes easier to understand, they're commented with examples
        # based on: from_coin='HIVE', to_coin='USD', proxy='BTC' (HIVE/USD via BTC proxy)
        
        # HIVE/BTC -> BTC/USD
        if cls.pair_exists(from_coin, proxy) and cls.pair_exists(proxy, to_coin):
            avg_frm = await cls.get_direct_rate_avg(from_coin, proxy, rate=rate)  # HIVE -> BTC
            avg_to = await cls.get_direct_rate_avg(proxy, to_coin, rate=rate)  # BTC -> USD
        # HIVE/BTC -> USD/BTC
        elif cls.pair_exists(from_coin, proxy) and cls.pair_exists(to_coin, proxy):
            avg_frm = await cls.get_direct_rate_avg(from_coin, proxy, rate=rate)
            avg_to = ONE / (await cls.get_direct_rate_avg(to_coin, proxy, rate=rate))
        # BTC/HIVE -> BTC/USD
        elif cls.pair_exists(proxy, from_coin) and cls.pair_exists(proxy, to_coin):
            avg_frm = ONE / (await cls.get_direct_rate_avg(proxy, from_coin, rate=rate))
            avg_to = await cls.get_direct_rate_avg(proxy, to_coin, rate=rate)
        # BTC/HIVE -> USD/BTC
        elif cls.pair_exists(proxy, from_coin) and cls.pair_exists(to_coin, proxy):
            avg_frm = ONE / (await cls.get_direct_rate_avg(proxy, from_coin, rate=rate))
            avg_to = ONE / (await cls.get_direct_rate_avg(to_coin, proxy, rate=rate))
            
        else:
            log.info("Failed to find a proxy for %s / %s via %s", from_coin, to_coin, proxy)
            if fail:
                raise ProxyMissingPair(f"Could not find any route to get {from_coin} -> {to_coin} via {proxy}")
            return None
        
        return avg_frm * avg_to

    @classmethod
    async def _get_avg_proxies(cls, from_coin: str, to_coin: str, *proxies, fail=False, rate='last') -> Optional[Decimal]:
        proxies = [v.upper() for v in empty_if(proxies, cls.common_proxies, itr=True)]
        for c in proxies:
            avg_rate = await cls._get_avg_proxy(from_coin, to_coin, proxy=c, fail=False, rate=rate)
            if not empty(avg_rate, True, True):
                return avg_rate
        if fail:
            raise ProxyMissingPair(f"Could not find any route to get {from_coin} -> {to_coin} via proxies: {proxies}")
        return None
    
    async def get_avg(self, from_coin: str, to_coin: str, use_proxy=True, rate='last', dp: int = 8) -> Decimal:
        from_coin, to_coin = from_coin.upper(), to_coin.upper()
        if not self.loaded:
            await self.load_exchanges()
        
        # async def get_inverted(frm, to, xrate):
        #     log.debug()
        #     x = await self.get_direct_rate_avg(to, frm, rate=xrate)
        #     if empty(x): return None
        #     return ONE / x
        
        coros = []
        
        if use_proxy:
            coros.append(self._get_avg_proxies(from_coin, to_coin, fail=True, rate=rate))
        
        pair = f"{from_coin}_{to_coin}"
        if pair in self.ex_pair_map:
            coros.append(self.get_direct_rate_avg(from_coin, to_coin, rate=rate))
        elif f"{to_coin}_{from_coin}" in self.ex_pair_map:
            coros.append(self.get_direct_rate_avg(to_coin, from_coin, rate=rate, invert=True))
        
        # if pair not in self.ex_pair_map:
        #     if not use_proxy:
        #         raise PairNotFound(f"Pair {pair} was not found in ex_pair_map, and no proxying requested.")
        #     log.debug("%s not found in pair map - only using proxies", pair)
        #     avg_rate = await self._get_avg_proxies(from_coin, to_coin, fail=True, rate=rate)
        #     return avg_rate
        # log.debug("%s WAS found in pair map - using both proxies and direct rates")
        #
        # _rates = await asyncio.gather(self._get_avg_proxies(from_coin, to_coin, fail=False, rate=rate),
        #                               self.get_direct_rate_avg(from_coin, to_coin, rate=rate))
        _rates = await asyncio.gather(*coros, return_exceptions=True)
        return avg(*_rates, dp=dp)
        # proxy_rate = await self._get_avg_proxies(from_coin, to_coin, fail=False, rate=rate)
        # direct_rate = await self.get_direct_rate_avg(from_coin, to_coin, rate=rate)
        # if empty(proxy_rate, True):
        #     return direct_rate
        # if empty(direct_rate, True):
        #     return proxy_rate
        # combined_avg = (proxy_rate + direct_rate) / TWO
        # return dec_round(combined_avg, dp=8)
        
    async def get_pair(self, from_coin: str, to_coin: str, rate='last', use_proxy: bool = True, dp: int = 8):
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
        return dec_round(data[rate], dp=dp)


class AsyncProvidesAdapter(ExchangeAdapter, ABC):
    code: str
    cache: AsyncCacheAdapter
    _gen_provides: callable
    
    PROVIDES_CACHE_TIME: Union[int, float] = 300
    """Amount of time (in seconds) to cache :attr:`.provides` for"""
    
    @async_property
    async def provides(self) -> Set[Tuple[str, str]]:
        """
        Kraken provides ALL of their tickers through one GET query, so we can generate ``provides``
        simply by querying their API via :meth:`.load_pairs` (using :meth:`._gen_provides`)

        We cache the provides Set both class-locally in :attr:`._provides`, as well as via the Privex Helpers
        Cache system - :mod:`privex.helpers.cache`

        """
        if empty(self._provides, itr=True):
            log.debug("Getting _provides from cache for %s", self.code)
            _prov = await self.cache.get(f"pvxex:{self.code}:provides")
            if not empty(_prov):
                # log.debug("Got _provides from cache")
                self._provides = _prov
            else:
                # log.debug("Calling _gen_provides for %s", self.code)
                self._provides = await self._gen_provides()
                # log.debug("Adding _provides to cache for %s : %s", self.code, self._provides)
                await self.cache.set(f"pvxex:{self.code}:provides", self._provides, timeout=self.PROVIDES_CACHE_TIME)
        # log.debug("Returning _provides")
        return self._provides


__all__ = [
    'ExchangeAdapter', 'PriceData',
    'ExchangeManager', 'AsyncProvidesAdapter'
]
