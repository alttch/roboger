__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2018 Altertech Group"
__license__ = "See https://www.roboger.com/"
__version__ = "1.0.0"

import uuid
import hashlib
import os
import logging
import threading

import roboger.core
import roboger.endpoints

from roboger import db


def gen_random_hash():
    s = hashlib.sha256()
    s.update(os.urandom(1024))
    s.update(str(uuid.uuid4()).encode())
    s.update(os.urandom(1024))
    return s.hexdigest()


addrs_by_id = {}

addrs_by_a = {}

addrs_lock = threading.Lock()


def lock():
    if not addrs_lock.acquire(timeout=roboger.core.timeout):
        raise Exception('Locking is broken')
    return True


def unlock():
    addrs_lock.release()


def append_addr(u=None, dbconn=None):
    _u = u if u else Addr(autosave=(dbconn is None))
    if dbconn: _u.save(dbconn)
    lock()
    addrs_by_id[_u.addr_id] = _u
    addrs_by_a[_u.a] = _u
    unlock()
    return _u


def load():
    c = db.query('select id, a, active from addr')
    while True:
        row = c.fetchone()
        if row is None: break
        append_addr(Addr(row[0], row[1], row[2]))
    c.close()
    db.free()
    logging.debug('addr: %u address(es) loaded' % len(addrs_by_id))


def get_addr(addr_id=None, a=None):
    lock()
    addr = None
    if addr_id: addr = addrs_by_id.get(addr_id)
    if not addr_id and a: addr = addrs_by_a.get(a)
    unlock()
    if not addr: return None
    return None if addr._destroyed else addr


def change_addr(addr_id=None, a=None, dbconn=None):
    addr = get_addr(addr_id, a)
    if not addr: return None
    lock()
    try:
        del addrs_by_a[addr.a]
    except:
        roboger.core.log_traceback()
    addrs_by_a[addr.set_a(autosave=False)] = addr
    unlock()
    addr.save(dbconn)
    return addr


def destroy_addr(addr_id):
    u = get_addr(addr_id)
    if not u: return False
    u.destroy()
    lock()
    try:
        del addrs_by_id[u.addr_id]
        del addrs_by_a[u.a]
    except:
        roboger.core.log_traceback()
    unlock()
    roboger.endpoints.destroy_endpoints_by_addr(u)
    return True


class Addr:

    def __init__(self, addr_id=None, a=None, active=1, autosave=True):
        self._destroyed = False
        self.active = active
        self.set_a(a, False)
        self.endpoints = []
        self.addr_id = addr_id
        self._lck = threading.Lock()
        if not addr_id:
            try:
                if autosave: self.save()
            except:
                roboger.core.log_traceback()
                self._destroyed = True

    def lock(self):
        if not self._lck.acquire(timeout=roboger.core.timeout):
            raise Exception('Locking is broken')
        return True

    def unlock(self):
        self._lck.release()

    def append_endpoint(self, e):
        self.lock()
        self.endpoints.append(e)
        self.unlock()

    def remove_endpoint(self, e):
        self.lock()
        try:
            self.endpoints.remove(e)
        except:
            roboger.core.log_traceback()
        self.unlock()

    def serialize(self):
        u = {}
        u['id'] = self.addr_id
        u['a'] = self.a
        u['active'] = self.active
        if roboger.core.development: u['destroyed'] = self._destroyed
        return u

    def set_a(self, a=None, autosave=True):
        self.a = a if a else gen_random_hash()
        if autosave: self.save()
        return self.a

    def set_active(self, active=1, dbconn=None):
        self.active = active
        self.save(dbconn)

    def save(self, dbconn=None):
        if self._destroyed: return
        if self.addr_id:
            db.query('update addr set a = %s, active = %s ' + \
                    ' where id = %s',
                    (self.a, self.active, self.addr_id), True, dbconn)
        else:
            self.addr_id = db.query('insert into addr(a, active) values ' + \
                    ' (%s, %s)', (self.a, self.active), True, dbconn)

    def destroy(self, dbconn=None):
        self._destroyed = True
        try:
            if self.addr_id:
                self.lock()
                _e = self.endpoints.copy()
                self.unlock()
                for e in _e:
                    roboger.endpoints.destroy_endpoints_by_addr(self, dbconn)
                db.query('delete from addr where id = %s', (self.addr_id,),
                         True, dbconn)
        except:
            roboger.core.log_traceback()
