#!/usr/bin/env python3
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
from os.path import dirname, abspath, join

from setuptools import setup, find_packages
from privex.exchange import VERSION
import warnings

with open("README.md", "r") as fh:
    long_description = fh.read()


extra_commands = {}

try:
    # noinspection PyUnresolvedReferences
    from privex.helpers import settings, BumpCommand, ExtrasCommand

    # This results in an absolute path to the folder where this setup.py file is contained
    BASE_DIR = dirname(abspath(__file__))

    # The file which contains "VERSION = '1.2.3'"
    settings.VERSION_FILE = join(BASE_DIR, 'privex', 'exchange', '__init__.py')

    extra_commands['extras'] = ExtrasCommand
    extra_commands['bump'] = BumpCommand
except (ImportError, AttributeError) as e:
    warnings.warn('Failed to import privex.helpers.setuppy.commands - the commands "extras" and "bump" may not work.')
    warnings.warn(f'Error Reason: {type(e)} - {str(e)}')

setup(
    name='privex_exchange',

    version=VERSION,

    description='A small library for querying Cryptocurrency exchanges and other price sources',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Privex/python-exchange",
    author='Chris (Someguy123) @ Privex',
    author_email='chris@privex.io',

    license='MIT',
    install_requires=[
        'httpx>=0.12.0',
        'attrs',
        'async-property',
        'privex-helpers[cache]>=2.10.0'
    ],
    packages=find_packages(exclude=['tests', 'tests.*', 'test.*']),
    cmdclass=extra_commands,
    extras_require={'dev': [
        'jupyter', 'wheel', 'setuptools', 'twine', 'privex-helpers[dev]', 'pytest', 'pytest-cov', 'coverage',
        'codecov', 'pytest-asyncio', 'nest-asyncio'
    ]},
    classifiers=[
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
