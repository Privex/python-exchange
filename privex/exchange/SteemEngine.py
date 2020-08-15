from typing import Set, Tuple, Optional, List
from async_property import async_property
from privex.helpers import empty, r_cache_async, empty_if
from privex.steemengine.exceptions import NoResults
from privex.exchange.base import AsyncProvidesAdapter, PriceData
from privex.exchange.exceptions import PairNotFound
from privex.steemengine import SteemEngineToken, Token
import logging

log = logging.getLogger(__name__)


class SteemEngine(AsyncProvidesAdapter):
    seng = SteemEngineToken(network='steem')
    
    name = "Steem Engine DEX"
    code = "steemengine"
    base_token = 'STEEMP'
    peg_prefix = ''
    peg_suffix = 'P'
    token_limit = 200
    
    _provides = set()
    _extra_provides = set()
    
    linked_symbols = {
        'BTC': 'BTCP',
        'EOS': 'EOSP',
        'TLOS': 'TLOSP',
        'LTC': 'LTCP',
        'DOGE': 'DOGEP',
        'BTS': 'BTSP',
        'SWIFT': 'SWIFTP',
        'STEEM': 'STEEMP',
        'HIVE': 'HIVEP',
    }
    """
    To prevent imposter coins, ``linked_symbols`` contains a map of important "standard" coin symbols, mapped to the
    official pegged version for SteemEngine, ensuring that ``BTC`` for example, never retrieves data for the token ``BTC``,
    since ``BTCP`` is the **real** BTC on SteemEngine
    """
    
    def __init__(self, **ex_settings):
        super().__init__(**ex_settings)
        if 'privex.exchange' not in SteemEngineToken.CACHE_BLACKLIST_MODS:
            SteemEngineToken.CACHE_BLACKLIST_MODS.append('privex.exchange')
        if 'privex.exchange.SteemEngine' not in SteemEngineToken.CACHE_BLACKLIST:
            SteemEngineToken.CACHE_BLACKLIST.append('privex.exchange.SteemEngine')

    @classmethod
    def remove_prefix(cls, token: str) -> str:
        if empty(cls.peg_prefix): return token
        return token[len(cls.peg_prefix):] if token.startswith(cls.peg_prefix) else token

    @classmethod
    def remove_suffix(cls, token: str) -> str:
        if empty(cls.peg_suffix): return token
        return token[:-len(cls.peg_suffix)] if token.endswith(cls.peg_suffix) else token
    
    @classmethod
    def remove_affixes(cls, token: str) -> str:
        return cls.remove_suffix(cls.remove_prefix(token))

    @classmethod
    def _affix_combos(cls, c: str) -> List[str]:
        return [c, cls.remove_prefix(c), cls.remove_suffix(c), cls.remove_affixes(c)]
    
    @property
    def base_token_affixes(self): return self._affix_combos(self.base_token)
    
    @async_property
    async def pairs(self):
        return [f"{f.upper()}_{t.upper()}" for f, t in await self.provides]
    
    @classmethod
    def _find_pair_affix(cls, from_coin: str, to_coin: str, pairs: List[str]) -> Optional[str]:
        from_coin, to_coin, = from_coin.upper(), to_coin.upper()
        from_combos, to_combos = cls._affix_combos(from_coin), cls._affix_combos(to_coin)
        from_combos += [f"{from_coin}{cls.peg_suffix}", f"{cls.peg_prefix}{from_coin}", f"{cls.peg_prefix}{from_coin}{cls.peg_suffix}"]
        for fc in from_combos:
            for tc in to_combos:
                if f"{fc}_{tc}" not in pairs:
                    continue
                return f"{fc}_{tc}"
        return None
    
    async def find_pair_affix(self, from_coin: str, to_coin: str) -> Optional[str]:
        return self._find_pair_affix(from_coin=from_coin, to_coin=to_coin, pairs=await self.pairs)
    
    async def has_pair(self, from_coin: str, to_coin: str) -> bool:
        if to_coin not in self.base_token_affixes:
            return False
        to_coin = self.base_token
        if not empty(await self.find_pair_affix(from_coin=from_coin, to_coin=to_coin)):
            return True
        return False
    
    @async_property
    @r_cache_async(lambda self: f'pvxex:{self.code}:tokens', 600)
    async def tokens(self) -> List[Token]:
        tokens = []
        tokens_loaded = 0
        lim = self.token_limit
        last_res = range(lim)
        batch = 0
        
        while len(last_res) >= lim:
            log.debug("[Batch %d || %d tokens loaded] Loading tokens for %s", batch + 1, tokens_loaded, self.name)
            last_res = self.seng.list_tokens(limit=lim, offset=lim * batch)
            tokens_loaded += len(last_res)
            batch += 1
            tokens += last_res
        
        log.debug("Finished loading %d tokens for %s after %d batches", tokens_loaded, self.name, batch + 1)
        return tokens
    
    @async_property
    @r_cache_async(lambda self: f'pvxex:{self.code}:token_symbols', 600)
    async def token_symbols(self) -> List[str]:
        return list(set([t.symbol for t in await self.tokens]))
    
    async def _gen_provides(self, *args, **kwargs) -> Set[Tuple[str, str]]:
        token_map = set()
        for t in await self.token_symbols:
            t, bt = t.upper(), self.base_token.upper()
            if t == bt:
                continue
            for trim_t in self._affix_combos(t):
                for trim_bt in self._affix_combos(bt):
                    token_map.add((trim_t, trim_bt,))
        return token_map
    
    async def _get_pair(self, from_coin: str, to_coin: str = None) -> PriceData:
        to_coin = empty_if(to_coin, self.base_token)
        from_coin, to_coin = from_coin.upper(), to_coin.upper()
        
        # Avoid imposter tokens by correcting "standard" symbols into their known official symbol on the exchange.
        if from_coin in self.linked_symbols:
            from_coin = self.linked_symbols[from_coin]
        
        if to_coin not in self.base_token_affixes:
            raise PairNotFound(f"Symbol {to_coin} is not supported by {self.name} ({self.code}). Only {self.base_token} is, plus "
                               f"it's symbol variations: {self.base_token_affixes}")
        to_coin = self.base_token
        
        pair = self._find_pair_affix(from_coin, to_coin, await self.pairs)
        if empty(pair):
            raise PairNotFound(f"[No valid pair] Symbol {from_coin} is not supported by {self.name} ({self.code})")
        from_coin = pair.split('_')[0]
        if empty(from_coin):
            raise PairNotFound(f"[from_coin is empty?] Symbol {from_coin} is not supported by {self.name} ({self.code})")
        try:
            ticker = self.seng.get_ticker(from_coin)
        except NoResults:
            raise PairNotFound(f"No ticker found for {from_coin}/{to_coin}")
    
        return PriceData(
            from_coin=from_coin, to_coin=self.base_token, last=ticker.lastPrice, bid=ticker.highestBid,
            ask=ticker.lowestAsk, open=ticker.lastDayPrice, close=ticker.lastDayPrice, volume=ticker.volume
        )

    async def get_pair(self, from_coin: str, to_coin: str = None) -> PriceData:
        to_coin = empty_if(to_coin, self.base_token)
        from_coin = from_coin.upper()
        # Avoid imposter tokens by correcting "standard" symbols into their known official symbol on the exchange.
        if from_coin in self.linked_symbols:
            from_coin = self.linked_symbols[from_coin]
        return await super().get_pair(from_coin=from_coin, to_coin=to_coin)


class HiveEngine(SteemEngine):
    seng = SteemEngineToken(network='hive')
    
    name = "Hive Engine DEX"
    code = "hiveengine"
    base_token = 'SWAP.HIVE'
    peg_prefix = 'SWAP.'
    peg_suffix = ''
    
    _provides = set()
    _extra_provides = set()
    
    linked_symbols = {
        'BTC':   'SWAP.BTC',
        'EOS':   'SWAP.EOS',
        'TLOS':  'SWAP.TLOS',
        'LTC':   'SWAP.LTC',
        'DOGE':  'SWAP.DOGE',
        'BTS':   'SWAP.BTS',
        'SWIFT': 'SWAP.SWIFT',
        'STEEM': 'SWAP.STEEM',
        'HIVE':  'SWAP.HIVE',
    }

