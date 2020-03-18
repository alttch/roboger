from pathlib import Path
import os
import sys
import signal
import sqlalchemy
import time
import requests
import random
import pytest
import threading
from functools import partial
from types import SimpleNamespace
from flask import Flask, request, Response
from textwrap import dedent

dir_me = Path(__file__).absolute().parents[1]
os.chdir(dir_me)
sys.path.insert(0, dir_me.as_posix())

import roboger
from roboger_manager import (ManagementAPI, Addr, Endpoint, Subscription)

test_server_bind = '127.0.0.1'
test_server_port = random.randint(9900, 9999)

test_app_bind = '127.0.0.1'
test_app_port = random.randint(9800, 9899)

pidfile = '/tmp/roboger-test-{}.pid'.format(os.getpid())
logfile = '/tmp/roboger-test-gunicorn-{}.log'.format(os.getpid())
configfile = '/tmp/roboger-test-{}.yml'.format(os.getpid())

gunicorn = os.getenv('GUNICORN', 'gunicorn')

dbconn = os.environ['DBCONN']
engine = sqlalchemy.create_engine(dbconn)
c = engine.connect()
for tbl in ['subscription', 'endpoint', 'addr']:
    try:
        c.execute(f'drop table {tbl}')
    except (sqlalchemy.exc.ProgrammingError, sqlalchemy.exc.OperationalError):
        pass
c.close()

limits = os.environ.get('LIMITS')
if limits:
    limits_config = """
        limits:
            period: hour
            reserve: 10
            redis:
                host: localhost:6379
                db: 3
    """
else:
    limits_config = ''

with open(configfile, 'w') as fh:
    fh.write(
        dedent(f"""
    roboger:
        db: {dbconn}
        log-tracebacks: true
        {limits_config}
        secure-mode: true
        db-pool-size: 2
        thread-pool-size: 20
        timeout: 5
        plugins:
            - name: webhook
            - name: email
              config:
                  smtp-server: 127.0.0.1
            - name: slack
        gunicorn:
            listen: {test_server_bind}:{test_server_port}
            path: {gunicorn}
            start-failed-after: 5
            force-stop-after: 10
            launch-debug: true
            extra-options: -w 1 --log-level INFO -u nobody
    """))

test_data = SimpleNamespace()

_test_app = Flask(__name__)

import roboger_manager

if limits:
    roboger_manager.use_limits = True


@_test_app.route('/webhook_test', methods=['POST'])
def _some_test_webhook():
    test_data.webhook_payload = request.json
    return Response(status=204)


api = ManagementAPI(f'http://{test_server_bind}:{test_server_port}', '123')


@pytest.fixture(scope='session', autouse=True)
def start_servers():
    threading.Thread(target=_test_app.run,
                     kwargs={
                         'host': test_app_bind,
                         'port': test_app_port
                     },
                     daemon=True).start()
    if os.system(f'ROBOGER_CONFIG={configfile} ROBOGER_MASTERKEY=123 '
                 f'{gunicorn} -D -b {test_server_bind}:{test_server_port}'
                 f' --log-file {logfile} --log-level DEBUG'
                 f' --pid {pidfile} roboger.server:app'):
        raise RuntimeError('Failed to start gunicorn')
    c = 0
    while not os.path.isfile(pidfile):
        c += 1
        time.sleep(0.1)
        if c > 50:
            raise TimeoutError
    yield
    with open(pidfile) as fh:
        pid = int(fh.read().strip())
    os.kill(pid, signal.SIGKILL)
    try:
        os.unlink(pidfile)
    except:
        pass
    if os.getenv('CLEANUP'):
        os.unlink(configfile)
        os.unlink(logfile)


def test001_test_server():
    result = api.test()
    assert result['build']
    assert result['version']
    result = requests.get(f'http://{test_server_bind}:{test_server_port}/ping')
    assert result.status_code == 204
    api.core_cleanup()
    plugins = roboger_manager.list_plugins(api=api)
    assert len(plugins) == 3
    for p in plugins:
        assert p['plugin_name'] in ['webhook', 'email', 'slack']


def test011_addr():
    # create addr
    addr = Addr(api=api)
    addr.create()
    assert addr.active
    x = dict(addr)
    assert x['id']
    assert x['a']
    assert x['active']
    if roboger_manager.use_limits:
        int(addr.lim_c)
        int(addr.lim_s)
    # get addr
    addr2 = Addr(id=addr.id, api=api)
    addr2.load()
    assert addr2.id == addr.id
    assert addr2.a == addr.a
    assert addr2
    if roboger_manager.use_limits:
        int(addr.lim_c)
        int(addr.lim_s)
    # get addr by id
    addr2.id = None
    addr2.load()
    assert addr2.id == addr.id
    assert addr2.a == addr.a
    assert addr2
    if roboger_manager.use_limits:
        int(addr.lim_c)
        int(addr.lim_s)
    # change addr
    addr.change()
    assert addr2.id == addr.id
    assert addr2.a != addr.a
    assert addr2
    # change addr to specified value
    addr.change(
        to='gNYt41IPfm3tMuSOzv0ybVpTDu3buLX8jyrNejO2kaFoKlTF7mBVGDZy5DVpV1Ns')
    addr.load()
    assert addr.a == ('gNYt41IPfm3tMuSOzv0ybVpTDu3buLX8'
                      'jyrNejO2kaFoKlTF7mBVGDZy5DVpV1Ns')
    # disable addr
    addr.disable()
    addr2.load()
    assert not addr.active
    assert not addr2.active
    # enable addr
    addr.enable()
    assert addr
    addr2.load()
    assert addr2
    addr.delete()
    with pytest.raises(LookupError, match=r'addr .* not found'):
        addr2.delete()


def test012_endpoint():
    addr = Addr(api=api)
    addr.create()
    assert len(addr.list_endpoints()) == 0
    with pytest.raises(ValueError):
        addr.create_endpoint('email', dict(xxx='zzz'))
    ep = addr.create_endpoint('email', dict(rcpt='some@domain'))
    assert len(addr.list_endpoints()) == 1
    assert ep.active
    x = dict(ep)
    assert x['id']
    assert x['addr_id'] == addr.id
    assert x['active']
    assert x['plugin_name'] == 'email'
    assert not x['description']
    ep2 = Endpoint(id=ep.id, addr_id=addr.id, api=api)
    ep2.load()
    assert ep2.id == ep.id
    assert ep2.addr_id == ep.addr_id
    assert ep2.plugin_name == ep.plugin_name
    ep2.description = 'some test'
    ep2.config = {'rcp': 'xxx@xxx'}
    with pytest.raises(ValueError):
        ep2.save()
    ep2.config = {'rcpt': 'xxx@xxx'}
    ep2.save()
    ep2.disable()
    ep.load()
    assert ep.config['rcpt'] == 'xxx@xxx'
    assert not ep.active
    assert ep.description == 'some test'
    ep.enable()
    ep2.load()
    assert ep.active
    assert ep2.active
    ep.delete()
    with pytest.raises(LookupError, match=r'endpoint .* not found'):
        ep2.delete()
    addr.delete()
    addr.create()
    ep = addr.create_endpoint('email', dict(rcpt='xxx@xxx'))
    addr.delete()
    with pytest.raises(LookupError, match=r'endpoint .* not found'):
        ep.delete()


def test013_subscription():
    addr = Addr(api=api)
    addr.create()
    ep = addr.create_endpoint('email', dict(rcpt='x@x'))
    with pytest.raises(Exception):
        s = ep.create_subscription(level=30, level_match='x')
    s = ep.create_subscription(level=30, level_match='e')
    s2 = ep.create_subscription()
    assert s.level == roboger.WARNING
    assert s.level_match == 'e'
    assert s2.level == roboger.INFO
    assert s2.level_match == 'ge'
    assert s.active
    assert s2.active
    assert not s2.sender
    assert not s2.location
    assert not s2.tag
    s2.delete()
    s2 = Subscription(id=s.id,
                      addr_id=s.addr_id,
                      endpoint_id=s.endpoint_id,
                      api=api)
    s.disable()
    assert not s.active
    s2.load()
    assert s.id == s2.id
    assert not s2.active
    s2.location = 'lab'
    s2.sender = 'bot'
    s2.tag = 'fault'
    s2.level = roboger.ERROR
    s2.level_match = 'ge'
    s2.enable()
    s2.save()
    s.load()
    assert s.active
    assert s.location == 'lab'
    assert s.sender == 'bot'
    assert s.tag == 'fault'
    assert s.level == roboger.ERROR
    assert s.level_match == 'ge'
    s.delete()
    addr.delete()
    with pytest.raises(LookupError, match=r'subscription .* not found'):
        s2.delete()


def test014_endpoint_copysub():
    addr = Addr(api=api)
    addr.create()
    ep = addr.create_endpoint('email', dict(rcpt='x@x'))
    ep2 = addr.create_endpoint('email', dict(rcpt='x@x2'))
    ep.create_subscription(level=roboger.DEBUG)
    ep.create_subscription(level=roboger.DEBUG)
    ep.create_subscription(level=roboger.DEBUG)
    assert len(ep.list_subscriptions()) == 3
    assert len(ep2.list_subscriptions()) == 0
    ep.copysub(target=ep2)
    assert len(ep2.list_subscriptions()) == 3
    ep.copysub(target=ep2)
    assert len(ep2.list_subscriptions()) == 6
    for s in ep2.list_subscriptions():
        assert s.level == roboger.DEBUG
    ep.copysub(target=ep2, replace=True)
    assert len(ep2.list_subscriptions()) == 3
    addr.delete()


def test020_push():
    if limits:
        roboger_manager.reset_addr_limits(api=api)
    test_data.webhook_payload = None
    addr = Addr(api=api)
    addr.create()
    ep = addr.create_endpoint(
        'webhook',
        dict(url=f'http://{test_app_bind}:{test_app_port}/webhook_test',
             template="""
             {
                 "event_id": $event_id,
                 "addr": $addr,
                 "msg": $msg,
                 "subject": $subject,
                 "formatted_subject": $formatted_subject,
                 "level": $level,
                 "level_name": $level_name,
                 "location": $location,
                 "tag": $tag,
                 "sender": $sender
             }
        """))
    s = ep.create_subscription(level=roboger.CRITICAL)
    push = partial(requests.post,
                   f'http://{test_server_bind}:{test_server_port}/push')
    payload = dict(addr=addr.a,
                   msg='test message\ntest test',
                   subject='test',
                   level=roboger.WARNING,
                   location='lab',
                   tag='fault',
                   sender='bot')
    push(json=payload)
    time.sleep(0.2)
    assert not test_data.webhook_payload
    s.level = roboger.INFO
    s.save()
    push(json=payload)
    time.sleep(0.2)
    assert test_data.webhook_payload['event_id']
    assert test_data.webhook_payload['addr'] == addr.a
    assert test_data.webhook_payload['msg'] == 'test message\ntest test'
    for k, v in payload.items():
        if k != 'addr':
            assert v == test_data.webhook_payload[k]
    test_data.webhook_payload = None
    s.location = 'home'
    s.save()
    push(json=payload)
    time.sleep(0.2)
    assert not test_data.webhook_payload
    payload['location'] = 'home'
    push(json=payload)
    time.sleep(0.2)
    assert test_data.webhook_payload['location'] == 'home'
    assert test_data.webhook_payload['addr'] == addr.a
    s.level_match = 'e'
    s.save()
    test_data.webhook_payload = None
    push(json=payload)
    time.sleep(0.2)
    assert not test_data.webhook_payload
    s.level = roboger.WARNING
    s.save()
    del payload['sender']
    del payload['tag']
    push(json=payload)
    time.sleep(0.2)
    assert test_data.webhook_payload['event_id']
    assert test_data.webhook_payload['sender'] is None
    assert test_data.webhook_payload['tag'] is None
    assert test_data.webhook_payload['location'] == 'home'
    assert test_data.webhook_payload['addr'] == addr.a
    addr.delete()


def test999_cleanup():
    addr = roboger_manager.create_addr(api=api)
    addr2 = roboger_manager.create_addr(api=api)
    roboger_manager.delete_everything(api=api, confirm='YES')
    with pytest.raises(LookupError, match=r'addr .* not found'):
        addr.delete()
    with pytest.raises(LookupError, match=r'addr .* not found'):
        addr2.delete()
