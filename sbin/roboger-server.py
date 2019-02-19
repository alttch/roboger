__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2018 Altertech Group"
__license__ = "See https://www.roboger.com/"
__version__ = "1.0.0"

import sys
import os
import argparse

dir_lib = os.path.dirname(os.path.realpath(__file__)) + '/../lib'
sys.path.append(dir_lib)

import roboger.core
import roboger.addr
import roboger.api

import logging

product_build = 2019021901

roboger.core.init()
roboger.core.set_build(product_build)

_me = 'Roboger server version %s build %s ' % (roboger.core.version,
                                               roboger.core.product_build)

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
    sys.exit()

cfg = roboger.core.load(fname=a._ini, initial=True)
if not cfg: sys.exit(2)

roboger.core.write_pid_file()

if not roboger.db.update_config(cfg): sys.exit(3)

if not roboger.api.update_config(cfg): sys.exit(4)

if not roboger.endpoints.update_config(cfg): sys.exit(5)

roboger.addr.load()

roboger.endpoints.load()

roboger.events.load_subscriptions()

roboger.events.load_queued_events()

roboger.endpoints.start()

roboger.events.start()

roboger.api.start()

roboger.core.block()
