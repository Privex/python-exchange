from decimal import Decimal
from typing import List, Optional, Union, Tuple, Set

from privex.helpers import dec_round, empty
from privex.helpers.types import NumberStr
from privex.steemengine import conv_dec
import logging

log = logging.getLogger(__name__)

__all__ = [
    'OptNumStr', 'avg', 'mean', 'med_avg', 'med_avg_out', 'trim_outliers', 'empty_decimal', 'PairListOrSet'
]

OptNumStr = Optional[NumberStr]


def avg(*vals: NumberStr, dp: OptNumStr = '8', rounding: str = None) -> Decimal:
    vals = [conv_dec(v) for v in list(vals) if not empty(v)]
    if len(vals) == 1:
        return vals[0] if empty(dp) else dec_round(vals[0], dp, rounding)
    _avg = conv_dec(sum(vals)) / Decimal(len(vals))
    return _avg if empty(dp) else dec_round(_avg, dp, rounding)


mean = avg


def med_avg_out(*vals: NumberStr, dp: OptNumStr = '8', out_pct: OptNumStr = '50', rounding: str = None) -> Decimal:
    """
    A more advanced version of the standard **median average** mathematical concept.
    
    By default, obtains a standard median average, and then uses ``out_pct`` to filter outlier values which are more than ``out_pct``
    percent bigger or smaller than the median average.
    
    When ``out_pct`` is a valid non-zero number (str, :class:`.Decimal`, float, int):
        
        This function calls :func:`.trim_outliers` to remove any outlier numbers that are more than ``out_pct`` (default: 50%)
        greater or smaller than the median average of ``vals``.
        
        For example, given the numbers ``1, 2, 4, 5, 8, 9``, the median average (midpoint) is 4.5 - and with a 50 ``out_pct``,
        any value smaller than 2.25 (4.5 * 0.5) or larger than 6.75 (4.5 * 1.5) would be removed. The remaining numbers
        are then added together, and divided by the amount of remaining numbers to obtain an average.
        
        However, you can adjust ``out_pct`` to a different percentage, or set it to either ``None`` / ``0`` to disable
        percentage based outlier filtering.
    
    When ``out_pct`` is ``None`` or ``0``:
        
        If there are 3 or less values, then ``vals`` are passed to :func:`.med_avg` to return a simple median average.
        
        If there are 4 to 8 values, then the smallest and largest value are removed.
        
        If there are more than 8 values, then 1/4 of the smallest values and 1/4 of the largest values will be removed.
        An integer 1/4 is used, so for example, 1/4 of 11 values would mean the 2 (2.75 rounded down) largest and smallest
        values are removed from the list.
        
        Once the 1/4 biggest + smallest outliers are removed, the remaining numbers are summed and divided by the number
        of remaining values to obtain an average.
    
    Basic usage - Averaging a mix of decimals and integers (as strings)::
    
        >>> med_avg_out('0.1', '0.2', '2', '2.3', '2.5', '3', '2.1', '8', '15')
        Decimal('2.38000000')
    
    Averaging 9 float values with the default 50% ``out_pct``, and without ``out_pct`` outlier trimming::
    
        >>> med_avg_out(10.10, 60.818, 50.9, 40.111, 45.831, 55.398, 52.155, 90.324, 429.829)
        Decimal('50.86883333')
        >>> med_avg_out(10.10, 60.818, 50.9, 40.111, 45.831, 55.398, 52.155, 90.324, 429.829, out_pct=None)
        Decimal('53.02040000')
    
    Using ``dp`` you can adjust how many decimal places to round the output by (or set it to ``None`` to disable DP rounding)::
    
        >>> med_avg_out(1.211, 3, 5.325, 8.12, dp=2)
        Decimal('4.16')
        >>> med_avg_out(1.211, 3, 5.325, 8.12)
        Decimal('4.16250000')
    
    
    :param NumberStr vals:    Two or more numbers passed as positional arguments to obtain an average for
    
    :param NumberStr dp:      Round (quantize) the resulting :class:`.Decimal` to this many decimal places
    
    :param NumberStr out_pct: When ``out_pct`` isn't empty, outliers will be filtered from ``vals`` if they're more than ``out_pct``
                              percent larger or smaller than the midpoint value. e.g. ``10`` means 10% - if the midpoint was ``50``,
                              then values larger than ``55`` or smaller than ``45`` would be removed.
    
    :param str rounding:      Optional rounding method, e.g. ``ROUND_HALF_DOWN`` or ``ROUND_UP``
    
    :return Decimal avg: The median average of ``vals`` with outliers removed.
    """
    dp = int(dp)
    rate_vals = sorted(list([conv_dec(v) for v in vals]))
    log.debug("got %d rate_vals (before removing outliers): %s", len(rate_vals), rate_vals)
    if not empty(out_pct, zero=True):
        out_pct = conv_dec(out_pct)
        log.debug("out_pct is not empty. trimming outliers using trim_outliers with %f%% tolerance", out_pct)
        rm_out = sorted(trim_outliers(*rate_vals, pct=out_pct))
    # If there's 3 or less values, then we simply return the normal median avg value
    elif len(rate_vals) <= 3:
        log.debug("only %d values (<= 3). returning median average.", len(rate_vals))
        return med_avg(*rate_vals, dp=dp, rounding=rounding)
    
    # Otherwise, we trim away the lowest and highest value(s), depending on how many values there are.
    elif len(rate_vals) <= 8:  # If there are 8 or less values, then we trim away just the first and last value
        log.debug("%d values (<= 8). trimming smallest and largest value.", len(rate_vals))
        rm_out = rate_vals[1:-1]
    else:  # If there are more than 8, we trim away 1/4 of the smallest and largest values.
        qt = int(len(rate_vals) // 4)
        log.debug("%d values (> 8). trimming %d values (1/4) from start and end.", len(rate_vals), qt)
        rm_out = rate_vals[qt:-qt]
    
    log.debug("averaging %d outlier-trimmed values: %s", len(rm_out), rm_out)
    # x = conv_dec(sum(rm_out))
    # mavg = Decimal(x / Decimal(len(rm_out)))
    # mavg = avg(*rm_out, dp=dp, rounding=rounding)
    return avg(*rm_out, dp=dp, rounding=rounding)


def trim_outliers(*vals: NumberStr, pct: NumberStr = '10') -> List[Decimal]:
    """
    Remove outlier values from a set of numbers, based on whether a number is more than ``pct`` percent larger or smaller
    than the median average (midpoint) of the values.
    
    Trimming outliers for integers with the default 10% outlier limit (midpoint is 8700)::
    
        >>> trim_outliers(5000, 7000, 6000, 9000, 9500, 8500, 9700, 8900, 14000, 18000, 2000)
        [Decimal('8500'), Decimal('8900'), Decimal('9000'), Decimal('9500')]
    
    Trimming outliers for decimals with a custom 60% outlier limit (midpoint is 0.425)::
    
        >>> trim_outliers('0.01', '0.4', '0.2', '0.9', '0.35', '4', '0.45', '88.253', '0.6', pct='60')
        [Decimal('0.2'), Decimal('0.35'), Decimal('0.4'), Decimal('0.45'), Decimal('0.6')]
        
    
    :param NumberStr vals:  Multiple numbers specified as positional arguments - to trim outliers from.
    
    :param NumberStr pct:   (kwarg - default: ``10``) A tolerance percentage for outliers, e.g. ``10`` removes any numbers
                            which are 10% larger or smaller than the median average of the numbers.
    
    :return List[Decimal] vals: The original ``vals`` as a list of :class:`.Decimal` 's, minus any outliers
    """
    if len(vals) == 0: raise ValueError("No values passed to trim_outliers... you must pass at least one number!")
    if len(vals) == 1: return [conv_dec(vals[0])]
    pct = conv_dec(pct) / Decimal('100')
    pct_low, pct_high = Decimal('1') - pct, Decimal('1') + pct
    vals = [conv_dec(v) for v in vals]
    mid_val = med_avg(*vals)
    log.debug('trim_outliers midpoint is: %f', mid_val)
    return list(sorted([v for v in vals if (mid_val * pct_low) <= v <= (mid_val * pct_high)]))


def med_avg(*vals: NumberStr, dp: OptNumStr = '8', rounding: str = None) -> Decimal:
    """
    Standard median average.
    
    If there are 3 or less values, the midpoint value will be returned.
    
    If there are 4 or more values, the midpoint, and value before the midpoint will be added together, and then
    divided by two to get the median average.
    
    :param NumberStr vals:   Two or more values to median average.
    :param NumberStr dp:     Decimal places to round to (can be ``None`` to disable rounding)
    :param str rounding:     Optional rounding method, e.g. ``ROUND_HALF_DOWN`` or ``ROUND_UP``
    
    :return Decimal med_avg: The median average of ``vals``
    """
    if len(vals) == 0:
        raise ValueError("No values passed to med_avg... you must pass at least one number!")
    dp = int(dp)
    rate_vals = sorted(list([conv_dec(v) for v in vals]))
    midpoint = int(len(rate_vals) // 2)
    if len(rate_vals) == 1: return rate_vals[0]
    if len(rate_vals) <= 3:
        return rate_vals[midpoint] if empty(dp) else dec_round(rate_vals[midpoint], dp, rounding)
    # mavg = avg(rate_vals[midpoint - 1], rate_vals[midpoint], dp=dp, rounding=rounding)
    # mavg = Decimal((rate_vals[midpoint - 1] + rate_vals[midpoint]) / Decimal('2'))
    # return mavg if empty(dp) else dec_round(mavg, dp, rounding)
    return avg(rate_vals[midpoint - 1], rate_vals[midpoint], dp=dp, rounding=rounding)


def empty_decimal(obj: Optional[Decimal]):
    if empty(obj): return None
    return Decimal(obj)


PairListOrSet = Union[List[Tuple[str, str]], Set[List[Tuple[str, str]]]]
