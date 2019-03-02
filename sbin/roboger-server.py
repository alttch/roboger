__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2018-2019 Altertech Group"
__license__ = "Apache License 2.0"
__version__ = "1.0.2"

import sys
import os
import argparse

dir_lib = os.path.dirname(os.path.realpath(__file__)) + '/../lib'
sys.path.append(dir_lib)

import roboger.core
import roboger.addr
import roboger.api

import logging

product_build = 2019022701

roboger.core.init()
roboger.core.set_build(product_build)

_me = 'Roboger server version %s build %s ' % (roboger.core.product.version,
                                               roboger.core.product.build)

ap = argparse.ArgumentParser(description=_me)
ap.add_argument(
    '-V',
    '--version',
    help='print version and exit',
    action='store_true',
    dest='_ver')
ap.add_argument(
    '-f', help='alternative config file', dest='_ini', metavar='CONFIGFILE')

a = ap.parse_args()

if a._ver:
    print(_me)
    exit()

cfg = roboger.core.load(fname=a._ini, initial=True)
if not cfg: exit(2)

if not roboger.api.update_config(cfg): exit(4)
if not roboger.endpoints.update_config(cfg): exit(5)

roboger.core.start()

roboger.addr.load()
roboger.endpoints.load()
roboger.events.load_subscriptions()
roboger.events.load_queued_events()

roboger.endpoints.start()
roboger.events.start()
roboger.api.start()
roboger.core.block()
