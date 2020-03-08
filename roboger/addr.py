__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2018-2019 Altertech Group"
__license__ = "Apache License 2.0"
__version__ = "1.0.2"

import uuid
import hashlib
import random
import string
import logging
import threading

import roboger.core
import roboger.endpoints

from roboger.core import db

from sqlalchemy import text as sql


def gen_random_str(length=64):
    symbols = string.ascii_letters + '0123456789'
    return ''.join(random.choice(symbols) for i in range(length))


addrs_by_id = {}

addrs_by_a = {}

addrs_lock = threading.RLock()


def append_addr(u=None, save=True):
    _u = u if u else Addr(autosave=save)
    if save: _u.save()
    with addrs_lock:
        addrs_by_id[_u.addr_id] = _u
        addrs_by_a[_u.a] = _u
    return _u


def load():
    c = db().execute(sql('select id, a, active from addr'))
    while True:
        r = c.fetchone()
        if r is None: break
        append_addr(Addr(addr_id=r.id, a=r.a, active=r.active), save=False)
    logging.debug('addr: %u address(es) loaded' % len(addrs_by_id))


def get_addr(addr_id=None, a=None):
    with addrs_lock:
        addr = None
        if addr_id: addr = addrs_by_id.get(addr_id)
        if not addr_id and a: addr = addrs_by_a.get(a)
    return addr if addr and not addr._destroyed else None


def change_addr(addr_id=None, a=None):
    with addrs_lock:
        addr = get_addr(addr_id, a)
        if not addr: return None
        try:
            del addrs_by_a[addr.a]
        except:
            roboger.core.log_traceback()
        addrs_by_a[addr.set_a(autosave=False)] = addr
    addr.save()
    return addr


def destroy_addr(addr_id):
    u = get_addr(addr_id)
    if not u: return False
    u.destroy()
    with addrs_lock:
        try:
            del addrs_by_id[u.addr_id]
            del addrs_by_a[u.a]
        except:
            roboger.core.log_traceback()
        roboger.endpoints.destroy_endpoints_by_addr(u)
    return True


class Addr:

    def __init__(self, addr_id=None, a=None, active=1, autosave=True):
        self._destroyed = False
        self.active = active
        self.set_a(a, False)
        self.endpoints = []
        self.addr_id = addr_id
        self.lock = threading.RLock()
        if not addr_id:
            try:
                if autosave: self.save()
            except:
                roboger.core.log_traceback()
                self._destroyed = True

    def append_endpoint(self, e):
        with self.lock:
            self.endpoints.append(e)

    def remove_endpoint(self, e):
        with self.lock:
            try:
                self.endpoints.remove(e)
            except:
                roboger.core.log_traceback()

    def serialize(self):
        u = {}
        u['id'] = self.addr_id
        u['a'] = self.a
        u['active'] = self.active
        if roboger.core.is_development(): u['destroyed'] = self._destroyed
        return u

    def set_a(self, a=None, autosave=True):
        self.a = a if a else gen_random_str()
        if autosave: self.save()
        return self.a

    def set_active(self, active=1):
        self.active = active
        self.save()

    def save(self):
        if self._destroyed: return
        if self.addr_id:
            db().execute(
                sql('update addr set a = :a, active = :active where id = :id'),
                a=self.a,
                active=self.active,
                id=self.addr_id)
        else:
            self.addr_id = db().execute(
                sql('insert into addr(a, active) values (:a, :active)'),
                a=self.a,
                active=self.active).lastrowid

    def destroy(self):
        self._destroyed = True
        try:
            if self.addr_id:
                with self.lock:
                    _e = self.endpoints.copy()
                for e in _e:
                    roboger.endpoints.destroy_endpoints_by_addr(self)
                db().execute(
                    sql('delete from addr where id = :id'), id=self.addr_id)
        except:
            roboger.core.log_traceback()
