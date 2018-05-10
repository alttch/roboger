__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2018 Altertech Group"
__license__ = "See https://www.roboger.com/"
__version__ = "1.0.0"

import sys
import os
import getopt

dir_lib = os.path.dirname(os.path.realpath(__file__)) + '/../lib'
sys.path.append(dir_lib)

import roboger.core
import roboger.addr
import roboger.api

import logging

def usage(version_only = False):
    print('Roboger version %s build %s ' % \
            (
                roboger.core.version,
                roboger.core.product_build
            )
        )
    if version_only: return
    print ("""Usage: roboger-server.py [-f config_file ]

 -f config_file     start with an alternative config file

for production use roboger only to start/stop Roboger server
""")

product_build = 2018051101

roboger.core.init()
roboger.core.set_build(product_build)

_ini = None

try:
    optlist, args = getopt.getopt(sys.argv[1:], 'f:hV')
except:
    usage()
    sys.exit(99)

for o, a in optlist:
    if o == '-f': _ini = a
    if o == '-V':
        usage(version_only = True)
        sys.exit()
    if o == '-h':
        usage()
        sys.exit()

cfg = roboger.core.load(fname = _ini, initial = True)
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

