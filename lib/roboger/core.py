__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2018 Altertech Group"
__license__ = "See https://www.roboger.com/"
__version__ = "1.0.0"

import os
import platform
import signal
import traceback
import configparser
import sys
import logging
import time
import json
import jsonpickle
import requests
import urllib3

from netaddr import IPNetwork, IPAddress

logging.getLogger('requests').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)

dir_roboger_default = '/opt/roboger'

version = __version__

system_name = platform.node()

product_build = None


dir_roboger = os.environ['ROBOGER_DIR'] if 'ROBOGER_DIR' in os.environ \
                            else dir_roboger_default

dir_var = dir_roboger + '/var'
dir_etc = dir_roboger + '/etc'

_stop_func = set()

_sigterm_sent = False


pid_file = None

log_file = None

primary_config = None

logger = None

keep_events = 0

debug = False

development = False

show_traceback = False

smtp_host = '127.0.0.1'
smtp_port = 25

timeout = 5


def set_build(build):
    global product_build
    product_build = build


def sighandler_hup(signum, frame):
    logging.info('got HUP signal, rotating logs')
    try:
        reset_log()
    except:
        log_traceback()


def sighandler_term(signum, frame):
    global _sigterm_sent
    logging.info('got TERM signal, exiting')
    shutdown()
    unlink_pid_file()
    _sigterm_sent = True
    logging.info('Roboger core shut down')
    sys.exit(0)


def init():
    global pid_file, log_file
    signal.signal(signal.SIGHUP, sighandler_hup)
    signal.signal(signal.SIGTERM, sighandler_term)
    pid_file = '%s/%s.pid' % (dir_var, 'roboger')


def write_pid_file():
    try:
        open(pid_file,'w').write(str(os.getpid()))
    except:
        log_traceback()


def unlink_pid_file():
    try:
        os.unlink(pid_file)
    except:
        log_traceback()


def debug_on():
    global debug
    debug = True
    logging.basicConfig(level=logging.DEBUG)
    if logger: logger.setLevel(logging.DEBUG)
    logging.info('Debug mode ON')


def debug_off():
    global debug
    debug = False
    if logger: logger.setLevel(logging.INFO)
    logging.info('Debug mode OFF')


def log_traceback(display = False, notifier = False, force = False):
    if (show_traceback or force) and not display:
        pfx = '.' if notifier else ''
        logging.error(pfx + traceback.format_exc())
    elif display:
        print(traceback.format_exc())


def format_cfg_fname(fname, cfg = None, ext = 'ini', path = None,
        runtime = False):
    if path: _path = path
    else:
        if runtime: _path = dir_runtime
        else: _path = dir_etc
    if not fname:
        if cfg: sfx = '_' + cfg
        else: sfx = ''
        return '%s/%s%s.%s' % (_path, 'roboger', sfx, ext)
    elif fname[0]!='.' and fname[0]!='/': return _path + '/' + fname
    else: return fname


def reset_log(initial = False):
    global logger, log_file_handler
    if logger and not log_file: return
    logger = logging.getLogger()
    try: log_file_handler.stream.close()
    except: pass
    if initial:
        for h in logger.handlers: logger.removeHandler(h)
    else:
        logger.removeHandler(log_file_handler)
    if not development:
        formatter = logging.Formatter('%(asctime)s ' + system_name + \
            '  %(levelname)s ' + 'roboger' + ' %(threadName)s: %(message)s')
    else:
        formatter = logging.Formatter('%(asctime)s ' + system_name + \
            ' %(levelname)s f:%(filename)s mod:%(module)s fn:%(funcName)s ' + \
            'l:%(lineno)d th:%(threadName)s :: %(message)s')
    if log_file: log_file_handler = logging.FileHandler(log_file)
    else: log_file_handler = logging.StreamHandler(sys.stdout)
    log_file_handler.setFormatter(formatter)
    logger.addHandler(log_file_handler)


def load(fname = None, initial = False, init_log = True):
    global log_file, pid_file, debug, development, show_traceback
    global timeout, smtp_host, smtp_port, keep_events
    fname_full = format_cfg_fname(fname)
    cfg = configparser.ConfigParser(inline_comment_prefixes=';')
    try:
        cfg.readfp(open(fname_full))
        if initial:
            try:
                pid_file = cfg.get('server', 'pid_file')
                if pid_file and pid_file[0] != '/':
                    pid_file = dir_roboger + '/' + pid_file
            except:
                pass
            try:
                pid = int(open(pid_file).readline().strip())
                p = psutil.Process(pid)
                print('Can not start Roboger with config %s. ' % \
                        (fname_full), end = '')
                print('Another process is already running')
                return None
            except: log_traceback()
            try: log_file = cfg.get('server', 'log_file')
            except: log_file = None
            if log_file and log_file[0] != '/':
                log_file = dir_roboger + '/' + log_file
            if init_log: reset_log(initial)
            try:
                development = (cfg.get('server','development') == 'yes')
                if development:
                    show_traceback = True
            except:
                development = False
            if development:
                show_traceback = True
                debug_on()
                logging.critical('DEVELOPMENT MODE STARTED')
                debug = True
            else:
                try:
                    show_traceback = (cfg.get('server',
                                        'show_traceback') == 'yes')
                except:
                    show_traceback = False
            if not development and not debug:
                try:
                    debug = (cfg.get('server','debug') == 'yes')
                    if debug: debug_on()
                except:
                    pass
                if not debug:
                        logging.basicConfig(level=logging.INFO)
                        if logger: logger.setLevel(logging.INFO)
            logging.info('Loading server config')
            logging.debug('server.pid_file = %s' % pid_file)
        try: timeout = float(cfg.get('server', 'timeout'))
        except: pass
        logging.debug('server.timeout = %s' % timeout)
        try:
            smtp_host, smtp_port = parse_host_port(
                    cfg.get('server', 'smtp_host'))
            if not smtp_port: smtp_port = 25
        except: pass
        logging.debug('server.smtp_host = %s:%u' % (smtp_host, smtp_port))
        try:
            keep_events = int(cfg.get('server', 'keep_events'))
        except:
            keep_events = 0
        logging.debug('server.keep_events = %s' % keep_events)
        return cfg
    except:
        print('Can not read primary config %s' % fname_full)
        log_traceback(True)
    return False


def parse_host_port(hp):
    if hp.find(':') == -1: return (hp, None)
    try:
        host, port = hp.split(':')
        port = int(port)
    except:
        log_traceback()
        return (None, None)
    return (host, port)


def shutdown():
    for f in _stop_func:
        try:
            f() 
        except:
            log_traceback()


def block():
    while not _sigterm_sent:
        time.sleep(0.2)


def append_stop_func(func):
    _stop_func.add(func)


def remove_stop_func(func):
    try:
        _stop_func.remove(func)
    except:
        log_traceback()

def format_json(obj, minimal = False):
    return json.dumps(json.loads(jsonpickle.encode(obj, unpicklable = False)),
            indent = 4, sort_keys = True) if not minimal else \
                    jsonpickle.encode(obj, unpicklable = False)

def netacl_match(host, acl):
    for a in acl:
        if IPAddress(host) in a: return True
    return False

