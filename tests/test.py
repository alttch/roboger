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

dir_me = Path(__file__).absolute().parents[1]
os.chdir(dir_me)
sys.path.insert(0, dir_me.as_posix())

from roboger.server import product_build
from roboger.server import __version__ as product_version

from roboger.manager import ManagementAPI, Addr

test_server_bind = '127.0.0.1'
test_server_port = random.randint(9900, 9999)

test_app_bind = '127.0.0.1'
test_app_port = random.randint(9800, 9899)

pidfile = '/tmp/roboger-test-{}.pid'.format(os.getpid())
logfile = '/tmp/roboger-test-gunicorn-{}.log'.format(os.getpid())

_test_app = Flask(__name__)

api = ManagementAPI(f'http://{test_server_bind}:{test_server_port}', '123')


@pytest.fixture(scope='session', autouse=True)
def start_servers():
    threading.Thread(target=_test_app.run,
                     kwargs={
                         'host': test_app_bind,
                         'port': test_app_port
                     },
                     daemon=True).start()
    if os.system(f'gunicorn -D -b {test_server_bind}:{test_server_port}'
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


def test001_test_server():
    result = api.test()
    assert result['build'] == product_build
    assert result['version'] == product_version
    result = requests.get(f'http://{test_server_bind}:{test_server_port}/ping')
    assert result.status_code == 204


def test011_addr():
    # create addr
    addr = Addr(api=api)
    addr.create()
    assert addr.active
    x = dict(addr)
    assert x['id']
    assert x['a']
    assert x['active']
    int(addr.lim)
    # get addr
    addr2 = Addr(id=addr.id, api=api)
    addr2.load()
    assert addr2.id == addr.id
    assert addr2.a == addr.a
    assert addr2
    int(addr.lim)
    # get addr by id
    addr2.id = None
    addr2.load()
    assert addr2.id == addr.id
    assert addr2.a == addr.a
    assert addr2
    int(addr.lim)
    # change addr
    addr.change()
    assert addr2.id == addr.id
    assert addr2.a != addr.a
    assert addr2
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


def test999_cleanup():
    os.unlink(logfile)
