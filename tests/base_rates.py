"""
This file contains "base rates", which are minimum prices expected for certain pairs for validating
the rates returned by exchanges.

These will need to be updated occasionally as exchange rates fluctuate, otherwise tests will fail.

"""
from decimal import Decimal

BTC_USD = Decimal('3000')
LTC_USD = Decimal('10')
HIVE_USD = Decimal('0.01')

LTC_BTC = Decimal('0.001')
HIVE_BTC = Decimal('0.000001')

__all__ = [
    'BTC_USD', 'LTC_USD', 'HIVE_USD',
    'LTC_BTC', 'HIVE_BTC'
]

