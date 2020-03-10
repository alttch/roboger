from pathlib import Path
import os
import sys
import signal
import time
import requests
import random
import pytest
import threading
from functools import partial
from types import SimpleNamespace
from flask import Flask

test_data = SimpleNamespace()

dir_me = Path(__file__).absolute().parents[1]
os.chdir(dir_me)
sys.path.insert(0, dir_me.as_posix())

from roboger.server import product_build
from roboger.server import __version__ as product_version

test_server_bind = '127.0.0.1'
test_server_port = random.randint(9900, 9999)

test_app_bind = '127.0.0.1'
test_app_port = random.randint(9800, 9899)

pidfile = '/tmp/roboger-test-{}.pid'.format(os.getpid())
logfile = '/tmp/roboger-test-gunicorn.log'

headers = {'X-Auth-Key': '123', 'Accept': '*/*'}

_test_app = Flask(__name__)


@pytest.fixture(scope='session', autouse=True)
def start_servers():
    threading.Thread(target=_test_app.run,
                     kwargs={
                         'host': test_app_bind,
                         'port': test_app_port
                     },
                     daemon=True).start()
    if os.system(f'gunicorn3 -D -b {test_server_bind}:{test_server_port}'
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


@pytest.mark.skip
def mapi2(uri, method='GET', err=None, timeout=2, **kwargs):
    callfunc = getattr(requests, method.lower())
    result = callfunc(
        f'http://{test_server_bind}:{test_server_port}/manage/v2{uri}',
        **kwargs,
        headers=headers,
        timeout=timeout)
    if not result.ok:
        if not err:
            raise RuntimeError(f'Request status code: {result.status_code}, '
                               f'text:\n{result.text}')
        elif err != 'get' and err != result.status_code:
            raise RuntimeError(
                f'Request status code: {result.status_code}, expected: {err}, '
                f'text:\n{result.text}')
    return result


def test001_test_server():
    result = mapi2('/core').json()
    assert result['ok'] is True
    assert result['build'] == product_build
    assert result['version'] == product_version
    result = requests.get(
        f'http://{test_server_bind}:{test_server_port}/ping')
    assert result.status_code == 204


def test011_create_addr():
    result = mapi2('/addr', 'POST').json()
    test_data.addr_id = result['id']
    test_data.addr = result['a']
    assert result['active'] == 1
    int(result['lim'])


def test012_get_addr():
    result = mapi2(f'/addr/{test_data.addr}').json()
    assert test_data.addr_id == result['id']
    assert test_data.addr == result['a']
    assert result['active'] == 1
    int(result['lim'])
    result = mapi2(f'/addr/{test_data.addr_id}').json()
    assert test_data.addr_id == result['id']
    assert test_data.addr == result['a']
    assert result['active'] == 1
    int(result['lim'])


def test013_change_addr():
    result = mapi2(f'/addr/{test_data.addr}', 'POST', json={
        'cmd': 'change'
    }).json()
    assert test_data.addr_id == result['id']
    assert test_data.addr != result['a']
    assert result['active'] == 1
    test_data.addr = result['a']
    int(result['lim'])


def test014_disable_addr():
    result = mapi2(f'/addr/{test_data.addr}', 'PATCH', json={
        'active': 0
    }).json()
    assert test_data.addr_id == result['id']
    assert test_data.addr == result['a']
    assert result['active'] == 0


def test015_enable_addr():
    result = mapi2(f'/addr/{test_data.addr}', 'PATCH', json={
        'active': 1
    }).json()
    assert test_data.addr_id == result['id']
    assert test_data.addr == result['a']
    assert result['active'] == 1


def test998_delete_addr():
    assert mapi2(f'/addr/{test_data.addr}', 'DELETE').status_code == 204
    mapi2(f'/addr/{test_data.addr}', 'DELETE', err=404)


def test999_cleanup():
    os.unlink(logfile)
