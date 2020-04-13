import logging
import sys
import warnings

name = 'exchange'

VERSION = '0.1.0'

try:
    from privex.exchange.base import *
    from privex.exchange.Binance import Binance
    from privex.exchange.Bittrex import Bittrex
    from privex.exchange.CoinGecko import CoinGecko
    from privex.exchange.Kraken import Kraken
except (ImportError, ModuleNotFoundError) as e:
    warnings.warn(f"Failed to import one or more modules: {type(e)} {str(e)}")

# If the privex.steemengine logger has no handlers, assume it hasn't been configured and set up a console logger
# for any logs >=WARNING
_l = logging.getLogger(__name__)
if len(_l.handlers) == 0:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s'))
    _handler.setLevel(logging.WARNING)
    _l.setLevel(logging.WARNING)
    _l.addHandler(_handler)

"""
+===================================================+
|                 © 2020 Privex Inc.                |
|               https://www.privex.io               |
+===================================================+
|                                                   |
|        Python Exchange Library                    |
|        License: X11/MIT                           |
|                                                   |
|        Core Developer(s):                         |
|                                                   |
|          (+)  Chris (@someguy123) [Privex]        |
|                                                   |
+===================================================+

Python Exchange Library - A small library for querying Cryptocurrency exchanges and other price sources
Copyright (c) 2020    Privex Inc. ( https://www.privex.io )

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy,
modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of
the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS
OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Except as contained in this notice, the name(s) of the above copyright holders shall not be used in advertising or
otherwise to promote the sale, use or other dealings in this Software without prior written authorization.
"""
