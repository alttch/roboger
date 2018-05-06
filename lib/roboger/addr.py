__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2018 Altertech Group"
__license__ = "See https://www.roboger.com/"
__version__ = "0.0.1"

import uuid
import hashlib
import os
import logging

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


def append_addr(u = None, dbconn = None):
    _u = u if u else Addr(autosave = (dbconn is None))
    if dbconn: _u.save(dbconn)
    addrs_by_id[_u.addr_id] = _u
    addrs_by_a[_u.a] = _u
    return _u


def load():
    c = db.query('select id, a, active from addr')
    while True:
        row = c.fetchone()
        if row is None: break
        append_addr(Addr(row[0], row[1], row[2]))
    c.close()
    logging.debug('addr: %u address(es) loaded' % len(addrs_by_id))


def get_addr(addr_id = None, a = None):
    addr = None
    if addr_id: addr = addrs_by_id.get(addr_id)
    if not addr_id and a: addr = addrs_by_a.get(a)
    if not addr: return None
    return None if addr._destroyed else addr


def change_addr(addr_id = None, a = None, dbconn = None):
    addr = get_addr(addr_id, a)
    if not addr: return None
    try:
        del addrs_by_a[addr.a]
    except:
        roboger.core.log_traceback()
    addrs_by_a[addr.set_a(autosave = False)] = addr
    addr.save(dbconn)
    return addr


def destroy_addr(addr_id):
    u = get_addr(addr_id)
    if not u: return False
    u.destroy()
    try:
        del addrs_by_id[u.addr_id]
        del addrs_by_a[u.a]
    except:
        roboger.core.log_traceback()
    roboger.endpoints.destroy_endpoints_by_addr(u)
    return True


class Addr:

    addr_id = None
    a = None
    active = None

    endpoints = []

    _destroyed = False

    def __init__(self, addr_id = None, a = None, active = 1, autosave = True):
        self.active = active
        self.set_a(a, False)
        if addr_id:
            self.addr_id = addr_id
        else:
            try:
                if autosave: self.save()
            except:
                roboger.core.log_traceback()
                self._destroyed = True


    def append_endpoint(self, e):
        self.endpoints.append(e)


    def remove_endpoint(self, e):
        self.endpoints.remove(e)


    def serialize(self):
        u = {}
        u['id'] = self.addr_id
        u['a'] = self.a
        u['active'] = self.active
        if roboger.core.development: u['destroyed'] = self._destroyed
        return u

    def set_a(self, a = None, autosave = True):
        self.a = a if a else gen_random_hash()
        if autosave: self.save()
        return self.a


    def set_active(self, active = 1, dbconn = None):
        self.active = active
        self.save(dbconn)


    def save(self, dbconn = None):
        if self._destroyed: return
        if self.addr_id:
            db.query('update addr set a = %s, active = %s ' + \
                    ' where id = %s',
                    (self.a, self.active, self.addr_id), True, dbconn)
        else:
            self.addr_id = db.query('insert into addr(a, active) values ' + \
                    ' (%s, %s)', (self.a, self.active), True, dbconn)


    def destroy(self, dbconn = None):
        self._destroyed = True
        if self.addr_id:
            for e in self.endpoints.copy():
                roboger.endpoints.destroy_endpoints_by_addr(self, dbconn)
            db.query('delete from addr where id = %s', (self.addr_id, ),
                    True, dbconn)

