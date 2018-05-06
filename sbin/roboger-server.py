__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2018 Altertech Group"
__license__ = "See https://www.roboger.com/"
__version__ = "0.0.1"

import sys
import os

dir_lib = os.path.dirname(os.path.realpath(__file__)) + '/../lib'
sys.path.append(dir_lib)

import roboger.core
import roboger.addr
import roboger.api

import logging

product_build = 2018050101

roboger.core.init()
roboger.core.set_build(product_build)

_ini = None

cfg = roboger.core.load(fname = _ini, initial = True)
if not cfg: sys.exit(2)

roboger.core.write_pid_file()

if not roboger.db.update_config(cfg): sys.exit(3)

if not roboger.api.update_config(cfg): sys.exit(4)

roboger.addr.load()

u = roboger.addr.get_addr(addr_id = 53)

roboger.endpoints.load()

roboger.events.load_subscriptions()

roboger.events.load_queued_events()

roboger.events.start()

roboger.api.start()

roboger.core.block()
