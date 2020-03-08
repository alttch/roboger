__author__ = 'Altertech, http://www.altertech.com/'
__copyright__ = 'Copyright (C) 2018-2020 Altertech Group'
__license__ = 'Apache License 2.0'
__version__ = '1.5.0'

import platform
import os
import sys
import importlib
import logging
import logging.handlers
import threading
import traceback
import sqlalchemy
import yaml
import signal
from types import SimpleNamespace
from flask import Flask
from concurrent.futures import ThreadPoolExecutor

from pathlib import Path
from neotasker import g

logging.getLogger('requests').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)

_d = SimpleNamespace(db=None, use_insertid=False, pool=None)

config = {}
plugins = {}

product = SimpleNamespace(build=None, version=__version__)
system_name = platform.node()

dir_me = Path(__file__).absolute().parents[1].as_posix()

db_lock = threading.RLock()

logger = logging.getLogger('roboger')

default_timeout = 5

default_db_pool_size = 1

default_thread_pool_size = 10

app = Flask('roboger')


def set_build(build):
    product.build = build


def safe_run_method(o, method, *args, **kwargs):
    try:
        f = getattr(o, method)
    except:
        return
    logger.debug(f'CORE executing {o.__name__}.{method}')
    f(*args, **kwargs)


def debug_on():
    config['debug'] = True
    logging.basicConfig(level=logging.DEBUG)
    logger.setLevel(level=logging.DEBUG)
    logger.info('CORE debug mode ON')


def debug_off():
    config['debug'] = False
    logging.basicConfig(level=logging.INFO)
    logger.setLevel(level=logging.INFO)
    logger.info('CORE debug mode OFF')


def log_traceback():
    if config['debug']: logger.error('CORE ' + traceback.format_exc())


def init_log():
    rl = logging.getLogger()
    for h in rl.handlers:
        rl.removeHandler(h)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(
        logging.Formatter('%(asctime)s ' + system_name + '  %(levelname)s ' +
                          '%(name)s' + ' %(message)s'))
    rl.addHandler(h)


def _dumps(*args, separators=None, **kwargs):
    import rapidjson
    return rapidjson.dumps(*args, **kwargs)


def load(fname=None):
    if not fname:
        fname = f'{dir_me}/etc/roboger.yml'
    if not Path(fname).exists:
        fname = '/usr/local/etc/roboger.yml'
    with open(fname) as fh:
        config.update(yaml.load(fh.read())['roboger'])
    init_log()
    if config.get('debug'): debug_on()
    import flask.json
    try:
        import rapidjson
        flask.json.load = rapidjson.load
        flask.json.loads = rapidjson.loads
        flask.json.dumps = _dumps
        logger.debug('CORE flask JSON module: rapidjson')
    except:
        logger.debug('CORE flask JSON module: standard')
    for plugin in config.get('plugins', []):
        plugin_name = plugin['name']
        try:
            mod = importlib.import_module(
                'roboger.plugins.{}'.format(plugin_name))
        except:
            try:
                mod = importlib.import_module(
                    'roboger-plugin-{}'.format(plugin_name))
            except:
                logger.error(f'CORE unable to load plugin: {plugin_name}')
                log_traceback()
                continue
        try:
            safe_run_method(mod, 'load', plugin.get('config', {}))
        except:
            logger.error(
                f'CORE failed to load plugin configuration for {plugin_name}')
            log_traceback()
        plugins[plugin_name] = mod
    logger.debug('CORE initializing database')
    if config['db'].startswith('sqlite'):
        _d.db = sqlalchemy.create_engine(config['db'])
    else:
        pool_size = config.get('db-pool-size', default_db_pool_size)
        _d.db = sqlalchemy.create_engine(config['db'],
                                         pool_size=pool_size,
                                         max_overflow=pool_size * 2)
    _d.use_insertid = config['db'].startswith(
        'sqlite') or config['db'].startswith('mysql')
    get_db()
    thread_pool_size = config.get('thread-pool-size', default_thread_pool_size)
    logger.debug(
        f'CORE initializing thread pool with max size {thread_pool_size}')
    _d.pool = ThreadPoolExecutor(max_workers=thread_pool_size)
    from . import api
    api.init()


def spawn(*args, **kwargs):
    return _d.pool.submit(*args, **kwargs)


def get_db():
    with db_lock:
        try:
            g.conn.execute('select 1')
            return g.conn
        except:
            g.conn = _d.db.connect()
            return g.conn


def get_timeout():
    timeout = config.get('timeout')
    return timeout if timeout else default_timeout


def get_app():
    return app


def get_plugin(plugin_name):
    return plugins['plugin_name']


def is_use_insertid():
    return _d.use_insertid


def convert_level(level):
    if level in [10, 20, 30, 40, 50]: return level
    elif isinstance(level, str):
        level = level.lower()
        if level.startswith('d'):
            return 10
        elif level.startswith('i'):
            return 20
        elif level.startswith('w'):
            return 30
        elif level.startswith('e'):
            return 40
        elif level.startswith('c'):
            return 50
    return 20


def send(plugin_name, **kwargs):
    try:
        spawn(_safe_send, plugin_name, plugins[plugin_name].send, **kwargs)
    except KeyError:
        logger.warning(f'API no such plugin: {plugin_name}')
    except AttributeError:
        logger.warning(f'API no "send" method in plugin {plugin_name}')


def _safe_send(plugin_name, send_func, event_id, **kwargs):
    try:
        send_func(event_id=event_id, **kwargs)
    except:
        logger.error(
            f'CORE plugin {plugin_name} raised exception, {event_id} not sent')
        log_traceback()
