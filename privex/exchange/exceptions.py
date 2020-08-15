from privex.helpers import PrivexException


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
