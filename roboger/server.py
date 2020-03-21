__author__ = 'Altertech, http://www.altertech.com/'
__copyright__ = 'Copyright (C) 2018-2020 Altertech Group'
__license__ = 'Apache License 2.0'
__version__ = '2.0.31'

import sys
import os
import argparse
from pathlib import Path

from . import core

product_build = 'stable'

core.set_build(product_build)
core.load()

app = core.get_app()

core.logger.debug('SERVER Roboger worker is running')
