from decimal import Decimal
from typing import Union

Number = Union[Decimal, int, float]


def assert_almost(orig: Number, compare: Number, tolerance=Decimal('0.01')):
    orig, compare = Decimal(orig), Decimal(compare)
    
    assert (compare - tolerance) < orig < (compare + tolerance)


assert_approx = assert_almost

__all__ = [
    'assert_almost', 'assert_approx'
]
