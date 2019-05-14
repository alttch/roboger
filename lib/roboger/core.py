__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2018-2019 Altertech Group"
__license__ = "Apache License 2.0"
__version__ = "1.0.2"

import os
import platform
import signal
import traceback
import configparser
import sys
import logging
import time
import threading
import json
import sqlalchemy
import requests
import urllib3
from netaddr import IPNetwork, IPAddress
from types import SimpleNamespace
from pyaltt import FunctionCollecton
from pyaltt import g


def set_build(build):
    product.build = build


def sighandler_hup(signum, frame):
    logging.info('got HUP signal, rotating logs')
    try:
        reset_log()
    except:
        log_traceback()


def sighandler_term(signum, frame):
    logging.info('got TERM signal, exiting')
    shutdown.run()
    unlink_pid_file()
    __core_data.term_sent = True
    logging.info('Roboger core shut down')
    sys.exit(0)


def init():
    signal.signal(signal.SIGHUP, sighandler_hup)
    signal.signal(signal.SIGTERM, sighandler_term)
    __core_data.pid_file = '%s/%s.pid' % (dir_var, 'roboger')


def write_pid_file():
    try:
        open(__core_data.pid_file, 'w').write(str(os.getpid()))
    except:
        log_traceback()


def unlink_pid_file():
    try:
        os.unlink(__core_data.pid_file)
    except:
        log_traceback()


def debug_on():
    config.debug = True
    logging.basicConfig(level=logging.DEBUG)
    if __core_data.logger: __core_data.logger.setLevel(logging.DEBUG)
    logging.info('Debug mode ON')


def debug_off():
    config.debug = False
    if __core_data.logger: __core_data.logger.setLevel(logging.INFO)
    logging.info('Debug mode OFF')


def log_traceback(display=False, notifier=False, force=False, e=None):
    if (config.show_traceback or force) and not display:
        pfx = '.' if notifier else ''
        logging.error(pfx + traceback.format_exc())
    elif display:
        print(traceback.format_exc())


def format_cfg_fname(fname, cfg=None, ext='ini', path=None, runtime=False):
    if path: _path = path
    else:
        if runtime: _path = dir_runtime
        else: _path = dir_etc
    if not fname:
        if cfg: sfx = '_' + cfg
        else: sfx = ''
        return '%s/%s%s.%s' % (_path, 'roboger', sfx, ext)
    elif fname[0] != '.' and fname[0] != '/':
        return _path + '/' + fname
    else:
        return fname


def reset_log(initial=False):
    if __core_data.logger and not __core_data.log_file: return
    __core_data.logger = logging.getLogger()
    try:
        __core_data.log_file_handler.stream.close()
    except:
        pass
    if initial:
        for h in __core_data.logger.handlers:
            __core_data.logger.removeHandler(h)
    else:
        __core_data.logger.removeHandler(__core_data.log_file_handler)
    if not config.development:
        formatter = logging.Formatter('%(asctime)s ' + system_name +
                                      '  %(levelname)s ' + 'roboger' +
                                      ' %(threadName)s: %(message)s')
    else:
        formatter = logging.Formatter(
            '%(asctime)s ' + system_name +
            ' %(levelname)s f:%(filename)s mod:%(module)s fn:%(funcName)s ' +
            'l:%(lineno)d th:%(threadName)s :: %(message)s')
    if __core_data.log_file:
        __core_data.log_file_handler = logging.FileHandler(__core_data.log_file)
    else:
        __core_data.log_file_handler = logging.StreamHandler(sys.stdout)
    __core_data.log_file_handler.setFormatter(formatter)
    __core_data.logger.addHandler(__core_data.log_file_handler)


def load(fname=None, initial=False, init_log=True):
    fname_full = format_cfg_fname(fname)
    cfg = configparser.ConfigParser(inline_comment_prefixes=';')
    try:
        cfg.read(fname_full)
        if initial:
            try:
                __core_data.pid_file = cfg.get('server', '__core_data.pid_file')
                if __core_data.pid_file and __core_data.pid_file[0] != '/':
                    __core_data.pid_file = (
                        dir_roboger + '/' + _core_data.pid_file)
            except:
                pass
            try:
                pid = int(open(__core_data.pid_file).readline().strip())
                p = psutil.Process(pid)
                print(
                    'Can not start Roboger with config %s. ' % (fname_full),
                    end='')
                print('Another process is already running')
                return None
            except:
                log_traceback()
            if not os.environ.get('ROBOGER_CORE_LOG_STDOUT'):
                try:
                    __core_data.log_file = cfg.get('server',
                                                   '__core_data.log_file')
                except:
                    __core_data.log_file = None
            if __core_data.log_file and __core_data.log_file[0] != '/':
                __core_data.log_file = dir_roboger + '/' + __core_data.log_file
            if init_log: reset_log(initial)
            try:
                config.development = (cfg.get('server', 'development') == 'yes')
                if config.development:
                    config.show_traceback = True
            except:
                config.development = False
            if config.development:
                config.show_traceback = True
                debug_on()
                logging.critical('DEVELOPMENT MODE STARTED')
            else:
                try:
                    config.show_traceback = (cfg.get('server',
                                                     'show_traceback') == 'yes')
                except:
                    config.show_traceback = False
            if not config.development and not config.debug:
                try:
                    debug = (cfg.get('server', 'debug') == 'yes')
                    if debug: debug_on()
                except:
                    pass
                if not config.debug:
                    logging.basicConfig(level=logging.INFO)
                    if __core_data.logger:
                        __core_data.logger.setLevel(logging.INFO)
            logging.info('Loading server config')
            try:
                config.database = cfg.get('server', 'database')
            except:
                print('database is not defined in roboger.ini [server] section')
                return None
            logging.debug('server.database = %s' % config.database)
            logging.debug(
                'server.__core_data.pid_file = %s' % __core_data.pid_file)
        try:
            config.timeout = float(cfg.get('server', 'timeout'))
        except:
            pass
        logging.debug('server.config.timeout = %s' % config.timeout)
        try:
            config.smtp_host, config.smtp_port = parse_host_port(
                cfg.get('server', 'smtp_host'))
            if not config.smtp_port: config.smtp_port = 25
        except:
            pass
        logging.debug('server.config.smtp_host = %s:%u' % (config.smtp_host,
                                                           config.smtp_port))
        try:
            config.keep_events = int(cfg.get('server', 'keep_events'))
        except:
            config.keep_events = 0
        logging.debug('server.config.keep_events = %s' % config.keep_events)
        return cfg
    except:
        print('Can not read primary config %s' % fname_full)
        log_traceback(True)
    return False


def start():
    if config.database.startswith('sqlite:///'):
        __core_data.db = sqlalchemy.create_engine(config.database)
    else:
        __core_data.db = sqlalchemy.create_engine(
            config.database,
            pool_size=config.db_pool_size,
            max_overflow=config.db_pool_size * 2)
    write_pid_file()


def parse_host_port(hp):
    if hp.find(':') == -1: return (hp, None)
    try:
        host, port = hp.split(':')
        port = int(port)
    except:
        log_traceback()
        return (None, None)
    return (host, port)


def block():
    while not __core_data.term_sent:
        time.sleep(0.2)


def format_json(obj, minimal=False):
    return json.dumps(
        obj, indent=4, sort_keys=True) if not minimal else json.dumps(obj)


def netacl_match(host, acl):
    for a in acl:
        if IPAddress(host) in a: return True
    return False


def db():

    def _make_new_connection():
        return __core_data.db.connect()

    with db_lock:
        if not g.has('dbconn'):
            g.dbconn = _make_new_connection()
        else:
            try:
                g.dbconn.execute('select 1')
            except:
                try:
                    g.dbconn.close()
                except:
                    pass
                g.dbconn = _make_new_connection()
        return g.dbconn


def db_type():
    return __core_data.db.name


def is_development():
    return config.development


def timeout():
    return config.timeout


def smtp_config():
    return config.smtp_host, config.smtp_port


def get_keep_events():
    return config.keep_events


logging.getLogger('requests').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)

dir_roboger_default = '/opt/roboger'

system_name = platform.node()

product = SimpleNamespace(build=None, version=__version__)


dir_roboger = os.environ['ROBOGER_DIR'] if 'ROBOGER_DIR' in os.environ \
                            else dir_roboger_default
os.chdir(dir_roboger)

dir_var = dir_roboger + '/var'
dir_etc = dir_roboger + '/etc'

db_lock = threading.RLock()

__core_data = SimpleNamespace(
    term_sent=False, pid_file=None, log_file=None, logger=None, db=None)

config = SimpleNamespace(
    database=None,
    keep_events=0,
    debug=False,
    development=False,
    show_traceback=False,
    smtp_host='127.0.0.1',
    smtp_port=25,
    db_pool_size=15,
    timeout=5)

shutdown = FunctionCollecton(on_error=log_traceback)
