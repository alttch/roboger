__author__ = 'Altertech, http://www.altertech.com/'
__copyright__ = 'Copyright (C) 2018-2020 Altertech Group'
__license__ = 'Apache License 2.0'
__version__ = '2.0.45'

import platform
import os
import sys
import importlib
import logging
import threading
import traceback
import sqlalchemy
import signal
import datetime
import time

import pyaltt2.json as json

from types import SimpleNamespace
from flask import Flask, request
from concurrent.futures import ThreadPoolExecutor

from pathlib import Path

from pyaltt2.crypto import gen_random_str
from pyaltt2.network import parse_host_port, generate_netacl
from pyaltt2.config import load_yaml, config_value, choose_file
from pyaltt2.res import ResourceStorage
from pyaltt2.db import Database
from netaddr import IPNetwork
from functools import partial
from hashlib import sha256

rs = ResourceStorage(mod='roboger')
rq = partial(rs.get, resource_subdir='sql', ext='sql')

SERVER_CONFIG_SCHEMA = {
    'type': 'object',
    'properties': {
        'roboger': {
            'type': 'object',
            'properties': {
                'db': {
                    'type': 'string'
                },
                'url': {
                    'type': 'string',
                    'format': 'uri'
                },
                'log-tracebacks': {
                    'type': 'boolean'
                },
                'ip-header': {
                    'type': 'string',
                },
                'api-doc': {
                    'type': ['boolean', 'string'],
                },
                'limits': {
                    'type': 'object',
                    'properties': {
                        'period': {
                            'type': 'string'
                        },
                        'reserve': {
                            'type': 'integer',
                            'minimum': 1
                        },
                        'redis': {
                            'type': 'object',
                            'properties': {
                                'host': {
                                    'type': 'string',
                                },
                                'db': {
                                    'type': 'integer',
                                    'minimum': 0
                                }
                            },
                            'additionalProperties': False,
                        },
                    },
                    'additionalProperties': False,
                },
                'bucket': {
                    'type': 'object',
                    'properties': {
                        'default-expires': {
                            'type': 'integer'
                        }
                    },
                    'additionalProperties': False
                },
                'secure-mode': {
                    'type': 'boolean'
                },
                'db-pool-size': {
                    'type': 'integer',
                    'minimum': 1
                },
                'thread-pool-size': {
                    'type': 'integer',
                    'minimum': 1
                },
                'timeout': {
                    'type': 'number',
                    'minimum': 0.1
                },
                'master': {
                    'type': 'object',
                    'properties': {
                        'key': {
                            'type': 'string'
                        },
                        'allow': {
                            'type': 'array',
                            'items': {
                                'type': 'string'
                            }
                        }
                    },
                    'additionalProperties': False,
                },
                'plugins': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'name': {
                                'type': 'string'
                            },
                            'config': {
                                'type': 'object'
                            }
                        },
                        'additionalProperties': False,
                        'required': ['name']
                    }
                },
                'gunicorn': {
                    'type': 'object'
                }
            },
            'additionalProperties': False,
            'required': ['db']
        }
    },
    'additionalProperties': False,
    'required': ['roboger']
}

logging.getLogger('requests').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)

_d = SimpleNamespace(db=None,
                     pool=None,
                     secure_mode=False,
                     ip_header=None,
                     log_tracebacks=False,
                     limits=None,
                     redis_conn=None)

config = {}
plugins = {}

product = SimpleNamespace(build=None, version=__version__, user_agent='')
system_name = platform.node()

dir_me = Path(__file__).absolute().parents[1].as_posix()

db_lock = threading.RLock()

default_bucket_expires = 86400

logger = logging.getLogger('gunicorn.error')
#logging.getLogger('roboger')

default_timeout = 5

default_db_pool_size = 1

default_thread_pool_size = 10

app = Flask('roboger')

g = threading.local()

emoji_code = {
    20: u'\U00002139',
    30: u'\U000026A0',
    40: u'\U0000203C',
    50: u'\U0001F170'
}


class OverlimitError(Exception):
    pass


def set_build(build):
    product.build = build
    product.user_agent = 'Roboger/{} (v{} build {})'.format(
        product.version[:product.version.rfind('.')], product.version,
        product.build)


def safe_run_method(o, method, *args, **kwargs):
    try:
        f = getattr(o, method)
    except:
        return
    logger.debug(f'CORE executing {o.__name__}.{method}')
    f(*args, **kwargs)


def log_traceback():
    if _d.log_tracebacks: logger.debug('CORE ' + traceback.format_exc())


def load(fname=None):

    def _init_plugin(plugin_name, mod, config):
        try:
            safe_run_method(mod, 'validate_plugin_config',
                            plugin.get('config', {}))
        except:
            logger.error(f'CORE failed to validate '
                         f'plugin configuration for {plugin_name}')
            log_traceback()
            return False
        try:
            safe_run_method(mod, 'load', plugin.get('config', {}))
            return True
        except:
            logger.error(
                f'CORE failed to load plugin configuration for {plugin_name}')
            log_traceback()
            return False
        try:
            getattr(mod, 'send')
            return True
        except:
            logger.info(f'CORE plugin {plugin_name} has no send method, '
                        'don\'t including into endpoint plugins')
            return False

    logger.info(f'CORE Roboger server {__version__} {product.build}')
    if not fname:
        fname = choose_file(
            env='ROBOGER_CONFIG',
            choices=[f'{dir_me}/etc/roboger.yml', '/usr/local/etc/roboger.yml'])
    logger.debug(f'CORE using config file {fname}')
    server_config = load_yaml(fname, schema=SERVER_CONFIG_SCHEMA)
    config.update(server_config['roboger'])
    config_value(config=config,
                 config_path='/bucket/default-expires',
                 in_place=True,
                 default=default_bucket_expires)
    config_value(env='ROBOGER_DB',
                 config=config,
                 config_path='/db',
                 in_place=True)
    _d.secure_mode = config.get('secure-mode')
    _d.log_tracebacks = config.get('log-tracebacks')
    _d.limits = config.get('limits')
    if _d.limits:
        import redis
        rhost, rport = parse_host_port(
            _d.limits.get('redis', {}).get('host', 'localhost'), 6379)
        rdb = _d.limits.get('redis', {}).get('db', 0)
        _d.redis_conn = redis.Redis(host=rhost,
                                    port=rport,
                                    db=rdb,
                                    socket_timeout=get_timeout(),
                                    socket_keepalive=True)
        logger.info(
            f'CORE limits feature activated. Redis: {rhost}:{rport} db: {rdb}')
    config['_acl'] = generate_netacl(config.get('master', {}).get('allow'),
                                     default=None)
    masterkey = os.getenv('ROBOGER_MASTERKEY')
    config_value(env='ROBOGER_MASTERKEY',
                 config=config,
                 config_path='/master/key',
                 to_str=True,
                 in_place=True)
    _d.ip_header = config.get('ip-header')

    logger.debug('CORE initializing database')
    kw = {}
    if not config['db'].startswith('sqlite'):
        kw['pool_size'] = config.get('db-pool-size', default_db_pool_size)
        kw['max_overflow'] = kw['pool_size'] * 2
    _d.db = Database(config['db'], rq_func=rq, **kw)
    logger.debug(f'CORE database {_d.db} ({_d.db.name})')
    _d.db.connect()
    thread_pool_size = config.get('thread-pool-size', default_thread_pool_size)
    logger.debug('CORE initializing thread pool for plugins '
                 f'with max size {thread_pool_size}')
    _d.pool = ThreadPoolExecutor(max_workers=thread_pool_size)
    logger.debug('CORE initializing database')
    init_db()
    from . import api
    logger.debug('CORE initializing API')
    api.init()
    logger.debug('CORE initializing plugins')
    for plugin in config.get('plugins', []):
        plugin_name = plugin['name']
        try:
            mod = importlib.import_module(
                'roboger.plugins.{}'.format(plugin_name))
        except:
            try:
                mod = importlib.import_module(
                    'robogercontrib.{}'.format(plugin_name))
            except:
                logger.error(f'CORE unable to load plugin: {plugin_name}')
                log_traceback()
                continue
        if _init_plugin(plugin_name, mod, plugin.get('config', {})):
            plugins[plugin_name] = mod
            logger.info(f'CORE added plugin {plugin_name}')

    logger.debug('CORE initialzation completed')


def spawn(*args, **kwargs):
    return _d.pool.submit(*args, **kwargs)


def init_db():
    from sqlalchemy import (Table, Column, BigInteger, Integer, Numeric, CHAR,
                            VARCHAR, MetaData, Float, ForeignKey, Index, JSON,
                            Enum, DateTime, Interval, Boolean, LargeBinary)
    import enum

    class LevelMatch(enum.Enum):
        l = 'l'
        g = 'g'
        le = 'le'
        ge = 'ge'
        e = 'e'

    if 'mysql' in _d.db.name:
        from sqlalchemy.dialects.mysql import DATETIME, LONGBLOB
        DateTime = partial(DATETIME, fsp=6)
        LargeBinary = LONGBLOB
    meta = MetaData()
    addr = Table('addr',
                 meta,
                 Column('id',
                        BigInteger().with_variant(Integer, 'sqlite'),
                        primary_key=True,
                        autoincrement=True),
                 Column('a', CHAR(64), nullable=False, unique=True),
                 Index('addr_a', 'a'),
                 Column('active',
                        Numeric(1, 0),
                        nullable=False,
                        server_default='1'),
                 Column('lim_c',
                        Numeric(8, 0),
                        nullable=False,
                        server_default='100'),
                 Column('lim_s',
                        Numeric(12, 0),
                        nullable=False,
                        server_default='10000000'),
                 mysql_engine='InnoDB',
                 mysql_charset='latin1')
    endpoint = Table('endpoint',
                     meta,
                     Column('id',
                            BigInteger().with_variant(Integer, 'sqlite'),
                            primary_key=True,
                            autoincrement=True),
                     Column('addr_id',
                            BigInteger().with_variant(Integer, 'sqlite'),
                            ForeignKey('addr.id', ondelete='CASCADE')),
                     Index('endpoint_addr_id', 'addr_id'),
                     Column('plugin_name', VARCHAR(40), nullable=False),
                     Column('config', JSON, nullable=False),
                     Column('active',
                            Numeric(1, 0),
                            nullable=False,
                            server_default='1'),
                     Column('description', VARCHAR(255), nullable=True),
                     mysql_engine='InnoDB',
                     mysql_charset='utf8mb4')
    subscription = Table('subscription',
                         meta,
                         Column('id',
                                BigInteger().with_variant(Integer, 'sqlite'),
                                primary_key=True,
                                autoincrement=True),
                         Column('endpoint_id',
                                BigInteger().with_variant(Integer, 'sqlite'),
                                ForeignKey('endpoint.id', ondelete='CASCADE')),
                         Index('subscription_endpoint_id', 'endpoint_id'),
                         Column('active',
                                Numeric(1, 0),
                                nullable=False,
                                server_default='1'),
                         Column('location', VARCHAR(255), nullable=True),
                         Column('tag', VARCHAR(255), nullable=True),
                         Column('sender', VARCHAR(255), nullable=True),
                         Column('level',
                                Numeric(2, 0),
                                nullable=False,
                                server_default='20'),
                         Column('level_match',
                                Enum(LevelMatch),
                                nullable=False,
                                server_default='ge'),
                         mysql_engine='InnoDB',
                         mysql_charset='utf8mb4')
    bucket = Table('bucket',
                   meta,
                   Column('id', CHAR(64), nullable=False, primary_key=True),
                   Column('creator', VARCHAR(64), nullable=False),
                   Column('addr_id',
                          BigInteger().with_variant(Integer, 'sqlite'),
                          ForeignKey('addr.id', ondelete='CASCADE')),
                   Column('mimetype', VARCHAR(256), nullable=False),
                   Column('fname', VARCHAR(256), nullable=True),
                   Column('size',
                          BigInteger().with_variant(Integer, 'sqlite'),
                          nullable=False),
                   Column('public', Boolean, nullable=False,
                          server_default='0'),
                   Column('metadata', JSON, nullable=True),
                   Column('d', DateTime(timezone=True), nullable=False),
                   Column('da', DateTime(timezone=True), nullable=True),
                   Column('expires',
                          Integer if _d.db.name in ('sqlite',
                                                    'mysql') else Interval,
                          nullable=True),
                   Column('content', LargeBinary, nullable=False),
                   mysql_engine='InnoDB',
                   mysql_charset='utf8mb4')
    meta.create_all(_d.db.connect())


def get_db():
    return _d.db


def get_timeout():
    timeout = config.get('timeout')
    return timeout if timeout else default_timeout


def get_app():
    return app


def get_real_ip():
    return request.headers.get(_d.ip_header, request.remote_addr) if \
            _d.ip_header else request.remote_addr


def get_plugin(plugin_name):
    return plugins[plugin_name]


def is_use_lastrowid():
    return _d.db.use_lastrowid


def is_use_interval():
    return _d.db.use_interval


def is_parse_db_json():
    return _d.db.parse_db_json


def is_secure_mode():
    return _d.secure_mode


def is_use_limits():
    return _d.limits is not None


def convert_level(level):
    try:
        level = int(level)
    except:
        pass
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
        else:
            return 20
    else:
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
        logger.debug(f'CORE {event_id} sending via {plugin_name}')
        send_func(event_id=event_id, **kwargs)
    except:
        logger.error(
            f'CORE plugin {plugin_name} raised exception, {event_id} not sent')
        log_traceback()


def check_addr_limit(addr, level, size):
    a = addr['id']
    lim_c = addr['lim_c']
    lim_s = addr['lim_s']
    key_c = f'{a}.lim_c'
    key_s = f'{a}.lim_s'
    try:
        try:
            current_c = int(_d.redis_conn.get(key_c))
        except TypeError:
            current_c = 0
        try:
            current_s = int(_d.redis_conn.get(key_s))
        except TypeError:
            current_s = 0
    except Exception as e:
        logger.error(f'CORE Redis error: {e}')
        return
    logger.debug(f'checking limits for addr.id={a}, current: '
                 f'{current_c}, size: {current_s}, current msg level: {level}')
    try:
        if current_c >= lim_c:
            logger.info(
                f'CORE address count overlimit addr.id={a} for all priorities')
            raise OverlimitError(
                f'Messages to {addr["a"]} are limited by {lim_c} per '
                f'{_d.limits["period"]}. Limit has been reached')
        elif current_c >= lim_c - (lim_c / 100 *
                                   _d.limits['reserve']) and level < 30:
            logger.info(
                f'CORE address count overlimit addr.id={a} for low-priority')
            raise OverlimitError(
                f'Messages to {addr["a"]} are limited by {lim_c} per '
                f'{_d.limits["period"]}, '
                f'{_d.limits["reserve"]}% are reserved for '
                'WARNING and higher levels')
        if current_s >= lim_s + size:
            logger.info(
                f'CORE address size overlimit addr.id={a} for all priorities')
            raise OverlimitError(
                f'Messages to {addr["a"]} are limited by {lim_s} bytes per '
                f'{_d.limits["period"]}. Limit has been reached')
        elif current_s >= lim_s - (lim_s / 100 *
                                   _d.limits['reserve']) and level < 30:
            logger.info(
                f'CORE address size overlimit addr.id={a} for low-priority')
            raise OverlimitError(
                f'Messages to {addr["a"]} are limited by {lim_s} bytes per '
                f'{_d.limits["period"]}, '
                f'{_d.limits["reserve"]}% are reserved for '
                'WARNING and higher levels')
        _d.redis_conn.incr(key_c)
        _d.redis_conn.incr(key_s, size)
    except OverlimitError:
        raise
    except Exception as e:
        logger.error(f'CORE check limit error: {e}')
        log_traceback()


def reset_addr_limits():
    _d.redis_conn.flushdb()
    logger.info('CORE address limits reset')


def cleanup():
    logger.debug('CORE cleanup')
    bucket_cleanup()
    for k, v in plugins.items():
        safe_run_method(v, 'cleanup')


def plugin_list():
    return plugins


# object functions


def delete_everything():
    _d.db.query('del')


def addr_get(addr_id=None, addr=None):
    return _d.db.qlookup('addr.get',
                         qargs=[',lim_c,lim_s'] if _d.limits else [''],
                         id=addr_id,
                         a=addr)


def addr_list():
    return _d.db.qlist('addr.list',
                       qargs=[',lim_c, lim_s'] if _d.limits else [])


def addr_create():
    addr = gen_random_str(64)
    i = _d.db.qcreate('addr.create', a=addr)
    logger.debug(f'CORE created address {i} ({addr})')
    return i


def addr_change(addr_id=None, addr=None, to=None):
    if to is None:
        to = gen_random_str(64)
    try:
        _d.db.query('addr.update.a', _cr=True, new_a=to, id=addr_id, a=addr)
        return to
    except sqlalchemy.exc.IntegrityError:
        raise ValueError


def addr_set_active(addr_id=None, addr=None, active=1):
    _d.db.query('addr.update.active',
                _cr=True,
                active=active,
                id=addr_id,
                a=addr)
    return addr_get(addr_id=addr_id, addr=addr)


def addr_set_limit(addr_id=None, addr=None, lim_c=None, lim_s=None):
    if lim_c is not None:
        _d.db.query('addr.update.lim_c',
                    _cr=True,
                    lim_c=lim_c,
                    id=addr_id,
                    a=addr)
    if lim_s is not None:
        _d.db.query('addr.update.lim_s',
                    _cr=True,
                    lim_s=lim_s,
                    id=addr_id,
                    a=addr)
    return addr_get(addr_id=addr_id, addr=addr)


def addr_delete(addr_id=None, addr=None):
    _d.db.query('addr.delete', _cr=True, id=addr_id, a=addr)
    logger.debug(f'CORE deleted address {addr_id}')


def endpoint_get(endpoint_id):
    return _d.db.qlookup('endpoint.get',
                         _cr=True,
                         json_fields=['config'],
                         id=endpoint_id)


def endpoint_list(addr_id=None, addr=None):
    return _d.db.qlist('endpoint.list',
                       json_fields=['config'],
                       addr_id=addr_id,
                       addr=addr)


def endpoint_create(plugin_name,
                    addr_id=None,
                    addr=None,
                    config=None,
                    description=None,
                    validate_config=False):
    if plugin_name not in plugins:
        raise LookupError(f'No such plugin: {plugin_name}')
    if config is None: config = {}
    else:
        try:
            safe_run_method(plugins[plugin_name], 'validate_config', config)
        except Exception as e:
            raise ValueError(e)
    i = _d.db.qcreate('endpoint.create',
                      addr_id=addr_id,
                      addr=addr,
                      plugin=plugin_name,
                      config=json.dumps(config),
                      description=description)
    logger.debug(f'CORE created endpoint {i} (plugin: {plugin_name})')
    return i


def endpoint_update(endpoint_id, data, validate_config=False, plugin_name=None):
    conn = _d.db.connect()
    dbt = conn.begin()
    try:
        if 'config' in data:
            try:
                if plugin_name is None:
                    plugin_name = endpoint_get(endpoint_id)['plugin_name']
                plugin = plugins[plugin_name]
            except KeyError:
                raise ValueError(f'plugin {plugin_name} not found')
            try:
                safe_run_method(plugin, 'validate_config', data['config'])
            except Exception as e:
                raise ValueError(e)
        for k, v in data.items():
            if k == 'active':
                v = int(v)
            _d.db.query('endpoint.update',
                        qargs=[k],
                        _cr=True,
                        id=endpoint_id,
                        v=json.dumps(v) if isinstance(v, dict) else v)
        dbt.commit()
    except:
        dbt.rollback()
        raise


def endpoint_delete(endpoint_id):
    _d.db.query('endpoint.delete', _cr=True, id=endpoint_id)
    logger.debug(f'CORE deleted endpoint {endpoint_id}')


def endpoint_delete_subscriptions(endpoint_id):
    return _d.db.query(
        'endpoint.deletesub',
        id=endpoint_id,
    ).rowcount


def subscription_get(subscription_id, endpoint_id=None):
    xkw = {'subscription_id': subscription_id}
    if endpoint_id is not None:
        xkw['endpoint_id'] = endpoint_id
    return _d.db.qlookup('subscription.get',
                         qargs=['AND endpoint_id=:endpoint_id']
                         if endpoint_id is not None else [''],
                         _cr=True,
                         **xkw)


def subscription_list(endpoint_id, addr_id=None):
    xkw = {'endpoint_id': endpoint_id}
    if addr_id is not None:
        xkw['addr_id'] = addr_id
    return _d.db.qlist(
        'subscription.list',
        qargs=['AND addr.id=:addr_id'] if addr_id is not None else [''],
        **xkw)


def subscription_create(endpoint_id,
                        location=None,
                        tag=None,
                        sender=None,
                        level=20,
                        level_match='ge'):
    if location == '': location = None
    if tag == '': tag = None
    if sender == '': sender = None
    if level is None: level = 20
    if level_match is None: level_match = 'ge'
    i = _d.db.qcreate('subscription.create',
                      endpoint_id=endpoint_id,
                      location=location,
                      tag=tag,
                      sender=sender,
                      level=level,
                      level_match=level_match)
    logger.debug(f'CORE created subscription {i} for endpoint {endpoint_id}')
    return i


def subscription_update(subscription_id, data):
    conn = _d.db.connect()
    dbt = conn.begin()
    try:
        for k, v in data.items():
            if v == '' and k in ['location', 'tag', 'sender']:
                v = None
            elif k == 'level_match':
                if not v:
                    v = 'ge'
                elif v.endswith('t'):
                    v = v[0]
            elif k == 'active':
                v = int(v)
            _d.db.query('subscription.update',
                        _cr=True,
                        qargs=[k],
                        id=subscription_id,
                        v=json.dumps(v) if isinstance(v, dict) else v)
        dbt.commit()
    except:
        dbt.rollback()
        raise


def subscription_delete(subscription_id):
    _d.db.query('subscription.delete', _cr=True, id=subscription_id)
    logger.debug(f'CORE deleted subscription {subscription_id}')


def bucket_get(object_id, public=None):
    """
    Get bucket object

    Args:
        object_id: object ID
        public: filter by "public" attr (None - don't filter)
    Raises:
        LookupError: if object is not found
    """
    if public is None:
        xargs = {}
        cond = ''
    else:
        xargs = {'public': public}
        cond = """ AND public = :public"""
    if _d.db.name == 'mysql':
        d = time.time()
        q = 'bucket.get:mysql'
    else:
        d = datetime.datetime.now()
        q = 'bucket.get:sqlite' if _d.db.name == 'sqlite' else 'bucket.get'
    return _d.db.qlookup(q,
                         json_fields=['metadata'],
                         qargs=[cond],
                         object_id=object_id,
                         d=d,
                         **xargs)


def bucket_put(content,
               creator,
               addr_id,
               mimetype=None,
               fname=None,
               public=False,
               metadata={},
               expires=None):
    """
    Args:
        content: file content (binary/text, required)
        creator: object creator
        addr_id: object addr id
        mimetype: optional object mime type (auto-detected if not provided)
        fname: optional object file name (served in "roboger-file-name" header)
        public: if True, file is accessible with public HTTP API as
            /file/{object_id}
        metadata: elements, provided in this dict, are served in headers as
            "x-roboger-{key}: {vaue}"
        expires: object expiration (in seconds), if not provided, default
            server expiration (by default: 86400 seconds) is set
    Returns:
        bucket object ID
    """
    if not isinstance(content, bytes) and not isinstance(content.bytearray):
        content = str(content).encode()
    h = sha256(content[:1024])
    h.update(str(datetime.datetime.now()).encode())
    h.update(str(time.perf_counter()).encode())
    h.update(creator.encode())
    h.update(str(addr_id).encode())
    object_id = h.hexdigest()
    if not mimetype:
        import magic
        mime = magic.Magic(mime=True)
        mimetype = mime.from_buffer(content)
        if not mimetype: mimetype = 'application/octet-stream'
    if metadata is None:
        metadata = {}
    if is_use_interval():
        expires = datetime.timedelta(
            seconds=(expires if expires is not None else config['bucket']
                     ['default-expires']))
    else:
        if expires is None:
            expires = config['bucket']['default-expires']
    _d.db.query('bucket.create',
                object_id=object_id,
                creator=creator,
                addr_id=addr_id,
                mimetype=mimetype,
                fname=fname,
                size=len(content),
                public=public,
                metadata=json.dumps(metadata),
                d=datetime.datetime.now(),
                expires=expires,
                content=content)
    logger.debug(
        f'CORE new bucket object {object_id} {mimetype} from {creator}')
    return object_id


def bucket_touch(object_id):
    """
    Mark object accessed (set access time)

    Raises:
        LookupError: if object is not found
    """
    _d.db.query('bucket.touch',
                _cr=True,
                da=datetime.datetime.now(),
                object_id=object_id)


def bucket_delete(object_id):
    """
    Delete object

    Expired objects are also deleted automatically, when core cleaup is called.

    Raises:
        LookupError: if object is not found
    """
    _d.db.query('bucket.delete', _cr=True, object_id=object_id)
    logger.debug(f'CORE deleted bucket object {object_id}')


def bucket_cleanup():
    if _d.db.name == 'mysql':
        q = 'bucket.cleanup:mysql'
        d = time.time()
    else:
        d = datetime.datetime.now()
        q = 'bucket.cleanup:sqlite' if _d.db.name == 'sqlite' else \
                'bucket.cleanup'
    _d.db.query(q, d=d)
