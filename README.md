# Python Crytocurrency Exchange all-in-one Library

[![Build Status](https://travis-ci.com/Privex/python-exchange.svg?branch=master)](https://travis-ci.com/Privex/python-exchange)

A small library for querying Cryptocurrency exchanges and other price sources

**Official Repo:** https://github.com/privex/python-exchange

**WARNING:** Under construction

# Information

This Python Exchange library has been developed at [Privex Inc.](https://www.privex.io) by @someguy123 for 
easily obtaining exchange rates between arbitrary coins, including ones which don't generally have pairs
on exchanges such as `HIVE/LTC`

It uses the following libraries:
 
 - [HTTPX](https://www.python-httpx.org/) for async requests to exchanges
 - [Attrs](https://www.attrs.org/en/stable/) for nicer objects like `privex.exchange.base.PriceData`
 - [Privex's Helpers library](https://github.com/Privex/python-helpers) for various small functions used throughout the package.


```
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
```


# Quick Install / Usage

```bash
pip3 install privex-exchange
```

```python
from privex.exchange import ExchangeManager

exm = ExchangeManager()

async def main():
    rate = await exm.get_pair('btc', 'usd')
    print(rate)
    # 6900.318
    tickers = await exm.get_tickers('btc', 'usd')
    print(tickers)
    # {'binance': Decimal('6679.70000000'),
    #  'bittrex': Decimal('6691.56500000'),
    #  'kraken': Decimal('6689.10000'),
    #  'coingecko': Decimal('6704.97999999')}



```

For full parameter documentation, IDEs such as PyCharm and even Visual Studio Code should show our PyDoc
comments when you try to use the class.

![Screenshot of PyCharm SteemEngine Help](https://i.imgur.com/R9oewTY.png)

For PyCharm, press F1 with your keyboard cursor over the class to see full function documentation, including
return types, parameters, and general usage information. You can also press CMD-P with your cursor inside of 
a method's brackets (including the constructor brackets) to see the parameters you can use.

Alternatively, just view the files inside of `privex/steemengine/` - most methods and constructors
are adequately commented with PyDoc.

# Documentation

[![Read the Documentation](https://read-the-docs-guidelines.readthedocs-hosted.com/_images/logo-wordmark-dark.png)](
https://python-exchange.readthedocs.io/en/latest/)

Full documentation for this project is available above (click the Read The Docs image), including:

 - How to install the application and it's dependencies 
 - How to use the various functions and classes
 - General documentation of the modules and classes for contributors

**To build the documentation:**

```bash
git clone https://github.com/Privex/python-exchange
cd python-exchange/docs
pip3 install -r requirements.txt

# It's recommended to run make clean to ensure old HTML files are removed
# `make html` generates the .html and static files in docs/build for production
make clean && make html

# After the files are built, you can live develop the docs using `make live`
# then browse to http://127.0.0.1:8100/
# If you have issues with content not showing up correctly, try make clean && make html
# then run make live again.
make live
```

# Install

We recommend that you use at least Python 3.4+ due to the usage of parameter and return type hinting.

### Install from PyPi using `pip`

You can install this package via pip:

```sh
pip3 install privex-exchange
```

### (Alternative) Manual install from Git

If you don't want to PyPi (e.g. for development versions not on PyPi yet), you can install the 
project directly from our Git repo.

Unless you have a specific reason to manually install it, you **should install it using pip3 normally**
as shown above.

**Option 1 - Use pip to install straight from Github**

```sh
pip3 install git+https://github.com/Privex/python-exchange
```

**Option 2 - Clone and install manually**

```bash
# Clone the repository from Github
git clone https://github.com/Privex/python-exchange
cd python-exchange

# RECOMMENDED MANUAL INSTALL METHOD
# Use pip to install the source code
pip3 install .

# ALTERNATIVE INSTALL METHOD
# If you don't have pip, or have issues with installing using it, then you can use setuptools instead.
python3 setup.py install
```


# Logging

By default, this package will log anything >=WARNING to the console. You can override this by adjusting the
`privex.exchange` logger instance. 

We recommend checking out our Python package [Python Loghelper](https://github.com/Privex/python-loghelper) which
makes it easy to manage your logging configuration, and copy it to other logging instances such as this one.

```python
# Without LogHelper
import logging
l = logging.getLogger('privex.exchange')
l.setLevel(logging.ERROR)

# With LogHelper (pip3 install privex-loghelper)
from privex.loghelper import LogHelper
# Set up logging for **your entire app**. In this case, log only messages >=error
lh = LogHelper('myapp', handler_level=logging.ERROR)
lh.add_file_handler('test.log')        # Log messages to the file `test.log` in the current directory
lh.copy_logger('privex.exchange')   # Easily copy your logging settings to any other module loggers
log = lh.get_logger()                  # Grab your app's logging instance, or use logging.getLogger('myapp')
log.error('Hello World')
```

# Unit Tests

Unit tests are available in `tests/`. We also have the project set up with [Travis CI](https://travis-ci.com/Privex/python
-exchange)
to alert us when new releases cause the tests to break.

To run the tests manually, use pytest:

```sh
git clone https://github.com/Privex/python-exchange
cd python-exchange
pipenv install --dev
pipenv shell

python3 -m pytest -v -rxXs --log-cli-level=INFO tests/
```

# Contributing

We're very happy to accept pull requests, and work on any issues reported to us. 

Here's some important information:

**Reporting Issues:**

 - For bug reports, you should include the following information:
     - Version of `privex-exchange`, `httpx`, and other libraries tested on - use `pip3 freeze`
        - If not installed via a PyPi release, git revision number that the issue was tested on - `git log -n1`
     - Your python3 version - `python3 -V`
     - Your operating system and OS version (e.g. Ubuntu 18.04, Debian 7)
 - For feature requests / changes
     - Please avoid suggestions that require new dependencies. This tool is designed to be lightweight, not filled with
       external dependencies.
     - Clearly explain the feature/change that you would like to be added
     - Explain why the feature/change would be useful to us, or other users of the tool
     - Be aware that features/changes that are complicated to add, or we simply find un-necessary for our use of the tool 
       may not be added (but we may accept PRs)
    
**Pull Requests:**

 - We'll happily accept PRs that only add code comments or README changes
 - Use 4 spaces, not tabs when contributing to the code
 - You can use features from Python 3.4+ (we run Python 3.7+ for our projects)
    - Features that require a Python version that has not yet been released for the latest stable release
      of Ubuntu Server LTS (at this time, Ubuntu 18.04 Bionic) will not be accepted. 
 - Clearly explain the purpose of your pull request in the title and description
     - What changes have you made?
     - Why have you made these changes?
 - Please make sure that code contributions are appropriately commented - we won't accept changes that involve 
   uncommented, highly terse one-liners.

**Legal Disclaimer for Contributions**

Nobody wants to read a long document filled with legal text, so we've summed up the important parts here.

If you contribute content that you've created/own to projects that are created/owned by Privex, such as code or 
documentation, then you might automatically grant us unrestricted usage of your content, regardless of the open source 
license that applies to our project.

If you don't want to grant us unlimited usage of your content, you should make sure to place your content
in a separate file, making sure that the license of your content is clearly displayed at the start of the file 
(e.g. code comments), or inside of it's containing folder (e.g. a file named LICENSE). 

You should let us know in your pull request or issue that you've included files which are licensed
separately, so that we can make sure there's no license conflicts that might stop us being able
to accept your contribution.

If you'd rather read the whole legal text, it should be included as `privex_contribution_agreement.txt`.

# License

This project is licensed under the **X11 / MIT** license. See the file **LICENSE** for full details.

Here's the important bits:

 - You must include/display the license & copyright notice (`LICENSE`) if you modify/distribute/copy
   some or all of this project.
 - You can't use our name to promote / endorse your product without asking us for permission.
   You can however, state that your product uses some/all of this project.



# Thanks for reading!

**If this project has helped you, consider [grabbing a VPS or Dedicated Server from Privex](https://www.privex.io) - 
prices start at as little as US$8/mo (we take cryptocurrency!)**
