__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2018 Altertech Group"
__license__ = "See https://www.roboger.com/"
__version__ = "1.0.0"

import datetime
import base64
import logging
import uuid
import time

import threading
import hashlib

from queue import Queue

import roboger.core
import roboger.addr
from roboger import db

level_names = {
    10: 'DEBUG',
    20: 'INFO',
    30: 'WARNING',
    40: 'ERROR',
    50: 'CRITICAL'
}

level_codes = {'d': 10, 'i': 20, 'w': 30, 'e': 40, 'c': 50}

q = Queue()

subscriptions_by_id = {}
subscriptions_by_addr_id = {}
subscriptions_by_endpoint_id = {}

queue_processor_active = False
queue_processor = None

event_cleaner_active = False
event_cleaner = None


def push_event(a,
               level,
               sender='',
               location='',
               keywords='',
               subject='',
               expires='',
               msg='',
               media=None,
               dbconn=None):
    addr = roboger.addr.get_addr(a=a)
    if not addr:
        logging.info('push: no such address %s' % a)
        return None
    if addr.active != 1:
        logging.info('push: skipping event for address %s, status' % \
                (a, addr.active))
        return addr.active
    logging.info('push: new event for address %s' % a)
    try:
        e = Event(
            addr,
            level_id=level,
            location=location,
            keywords=keywords,
            sender=sender,
            subject=subject,
            msg=msg,
            media=media,
            expires=expires,
            autosave=False)
        e.save(dbconn=dbconn)
        queue_event(e, dbconn)
        return True
    except:
        roboger.core.log_traceback()
        return False


def _t_queue_processor():
    global queue_processor_active
    if roboger.core.keep_events:
        dbconn = db.connect()
    else:
        dbconn = None
    queue_processor_active = True
    while queue_processor_active or not roboger.core.keep_events:
        eq = q.get()
        if dbconn and not db.check(dbconn):
            dbconn = db.connect()
        if not eq or \
                (roboger.core.keep_events and not queue_processor_active):
            break
        if eq.subscription._destroyed: continue
        logging.info('Sending queued event id: %s' % eq.event.event_id + \
                ', endpoint id: %s' % eq.subscription.endpoint.endpoint_id + \
                ', subscription id: %s' % eq.subscription.subscription_id + \
                ', addr id: %s, addr: %s' % (eq.event.addr.addr_id,
                                    eq.event.addr.a)
                                    )
        t = threading.Thread(target=eq.send)
        t.start()
        eq.mark_delivered(dbconn=dbconn)
    if dbconn:
        dbconn.close()


def _t_event_cleaner():
    global event_cleaner_active
    clean_interval = 60
    dbconn = db.connect()
    event_cleaner_active = True
    c = clean_interval
    while event_cleaner_active:
        c += 1
        if c > clean_interval:
            logging.debug('cleaning old events')
            try:
                if dbconn and not db.check(dbconn):
                    dbconn = db.connect()
                # move this logic out
                if db.db_engine == 'sqlite':
                    q = 'delete from event where d < ' + \
                            'datetime(current_timestamp, "-%s second")' % \
                            roboger.core.keep_events
                elif db.db_engine == 'mysql':
                    q = 'delete from event where d<NOW() ' + \
                            ' - INTERVAL %s SECOND' % roboger.core.keep_events
                else:
                    q = None
                if q:
                    db.query(
                        q,
                        (),
                        True,
                        dbconn=dbconn)
            except:
                roboger.core.log_traceback()
            c = 0
        time.sleep(1)


def stop():
    global queue_processor_active
    global event_cleaner_active
    if queue_processor_active and \
            queue_processor and queue_processor.isAlive():
        queue_processor_active = False
        q.put(None)
        queue_processor.join()
    if event_cleaner_active and \
            event_cleaner and event_cleaner.isAlive():
        event_cleaner_active = False
        event_cleaner.join()
    return


def start():
    global queue_processor, event_cleaner
    roboger.core.append_stop_func(stop)
    if not ( queue_processor_active and \
            queue_processor and queue_processor.isAlive() ):
        queue_processor = threading.Thread(
            target=_t_queue_processor, name="_t_queue_processor")
        queue_processor.start()
    if roboger.core.keep_events:
        if not ( event_cleaner_active and \
                event_cleaner and event_cleaner.isAlive() ):
            event_cleaner = threading.Thread(
                target=_t_event_cleaner, name="_t_event_cleaner")
            event_cleaner.start()


def location_match(lmask, location):
    if not lmask or lmask == '#' or lmask == location: return True
    p = lmask.find('#')
    if p > -1 and lmask[:p] == location[:p]: return True
    if lmask.find('+') > -1:
        g1 = lmask.split('/')
        g2 = location.split('/')
        if len(g1) == len(g2):
            match = True
            for i in range(0, len(g1)):
                if g1[i] != '+' and g1[i] != g2[i]:
                    match = False
                    break
            if match: return True
    return False


def keyword_match(kws, kwc):
    if not kws: return True
    for k in kwc:
        if k in kws: return True
    return False


def level_match(l, lc, cond):
    if not lc: return True
    if cond == 'e':
        return lc == l
    if cond == 'l':
        return lc < l
    if cond == 'le':
        return lc <= l
    if cond == 'g':
        return lc > l
    if cond == 'ge':
        return lc >= l
    return False


def get_subscription(s_id):
    return subscriptions_by_id.get(s_id)


def queue_event(event, dbconn=None):
    endp = []
    if event.addr.addr_id not in subscriptions_by_addr_id:
        return
    for i, s in subscriptions_by_addr_id[event.addr.addr_id].copy().items():
        if event.addr.active == 1 and s.active == 1 and \
                s.endpoint.active == 1 and \
                s.endpoint.endpoint_id not in endp and \
                location_match(s.location, event.location) and \
                keyword_match(s.keywords, event.keywords) and \
                (not s.senders or s.senders == [ '*' ] or \
                    event.sender in s.senders) and \
                level_match(s.level_id, event.level_id, s.level_match):
            endp.append(s.endpoint.endpoint_id)
            eq = EventQueueItem(event, s, initial=True, autosave=False)
            eq.save(initial=True, dbconn=dbconn)
            event.scheduled += 1
            event.save(dbconn)
            q.put(eq)


def destroy_subscription(s, dbconn):
    if isinstance(s, int):
        _s = get_subscription(s)
    else:
        _s = s
    _s.destroy(dbconn)
    try:
        del subscriptions_by_id[_s.subscription_id]
        del subscriptions_by_addr_id[_s.addr.addr_id][_s.subscription_id]
        del subscriptions_by_endpoint_id[_s.endpoint.endpoint_id][
            _s.subscription_id]
    except:
        roboger.core.log_traceback()


def get_event_level_name(level_id):
    return level_names.get(level_id)


def append_subscription(s):
    e = s.endpoint
    u = s.addr
    e.append_subscription(s)
    subscriptions_by_id[s.subscription_id] = s
    if u.addr_id not in subscriptions_by_addr_id:
        subscriptions_by_addr_id[u.addr_id] = {}
    if e.endpoint_id not in subscriptions_by_endpoint_id:
        subscriptions_by_endpoint_id[e.endpoint_id] = {}
    subscriptions_by_addr_id[u.addr_id][s.subscription_id] = s
    subscriptions_by_endpoint_id[e.endpoint_id][s.subscription_id] = s


def load_subscriptions():
    c = db.query('select id, addr_id, endpoint_id, active,' + \
            'location, keywords, senders, level_id, level_match ' + \
            ' from subscription')
    while True:
        row = c.fetchone()
        if row is None: break
        u = roboger.addr.get_addr(addr_id=row[1])
        e = roboger.endpoints.get_endpoint(endpoint_id=row[2])
        if not u:
            logging.error('Addr %u not found but subscriptions exist!' % \
                    row[1])
            continue
        if not e:
            logging.error('Endpoint %u not found but subscriptions exist!' % \
                    row[2])
            continue
        s = EventSubscription(u, e, row[0], row[3], row[4], row[5], row[6], \
                row[7], row[8])
        append_subscription(s)
    logging.debug('endpoint subscriptions: %u subscription(s) loaded' % \
            len(subscriptions_by_id))
    c.close()
    db.free()
    return True


def load_queued_events():
    c = db.query('select event_id, subscription_id, addr_id, d, scheduled,' + \
            ' delivered, location, keywords, sender, level_id, expires,' + \
            'subject, msg, media from event_queue join event' + \
            ' on event.id = event_queue.event_id where status < 1')
    cqe = 0
    while True:
        row = c.fetchone()
        if row is None: break
        u = roboger.addr.get_addr(row[2])
        if not u:
            logging.error('Addr %u not found but queued events exist!' % row[2])
            continue
        s = get_subscription(row[1])
        if not s:
            logging.error(
                'Subscription %u not found but queued events exist!' % row[2])
            continue
        e = Event(u, row[0], row[3], row[4], row[5], row[6], row[7], row[8],
                  row[9], row[10], row[11], row[12], row[13])
        eq = EventQueueItem(e, s)
        cqe += 1
        q.put(eq)
    logging.debug('events: %u queued event(s) loaded' % cqe)
    c.close()
    db.free()


class EventQueueItem(object):

    def __init__(self,
                 event,
                 subscription,
                 status=0,
                 dd=None,
                 initial=False,
                 autosave=True):
        self._destroyed = False
        self.event = event
        self.subscription = subscription
        self.status = status
        self.dd = dd if dd else \
                datetime.datetime.now()
        if initial and autosave: self.save(initial=initial)

    def send(self):
        try:
            self.subscription.endpoint.send(self.event)
        except:
            roboger.core.log_traceback()

    def save(self, initial=False, dbconn=None):
        if self._destroyed or not roboger.core.keep_events: return True
        if initial:
            db.query('insert into event_queue ' + \
                    '(event_id, subscription_id, status, dd)' + \
                    ' values (%s,%s,%s,%s)',
                    (self.event.event_id, self.subscription.subscription_id,
                        self.status, self.dd), True, dbconn)
        else:
            db.query('update event_queue set status=%s, dd=%s ' + \
                    'where event_id=%s and subscription_id=%s',
                    (self.status, self.dd, self.event.event_id,
                        self.subscription.subscription_id), True, dbconn)
        return True

    def mark_delivered(self, dbconn=None):
        self.dd = datetime.datetime.now()
        self.status = 1
        self.save(dbconn=dbconn)
        self.event.delivered += 1
        self.event.save(dbconn=dbconn)

    def destroy(dbconn=None):
        self._destroyed = True
        db.query('delete from event_queue where event_id=%s and ' + \
                'subscription_id=%s',
                (self.event.event_id, self.subscription.subscription_id),
                True, dbconn)


class EventSubscription(object):

    def __init__(self,
                 addr,
                 endpoint,
                 subscription_id=None,
                 active=1,
                 location='',
                 keywords='',
                 senders='',
                 level_id=20,
                 level_match='ge',
                 autosave=True):
        self._destroyed = False
        self.addr = addr
        self.endpoint = endpoint
        self.active = active
        self.location = location if location else ''
        if isinstance(keywords, list):
            self.keywords = keywords
        elif isinstance(keywords, str):
            self.keywords = list(
                filter(None, [x.strip() for x in keywords.split(',')]))
        else:
            self.keywords = []
        if isinstance(senders, list):
            self.senders = senders
        elif isinstance(senders, str):
            self.senders = list(
                filter(None, [x.strip() for x in senders.split(',')]))
        else:
            self.senders = []
        self.level_id = level_id if level_id else 20
        self.level_match = level_match if level_match else 'ge'
        self.subscription_id = subscription_id
        if not subscription_id:
            try:
                if autosave: self.save()
            except:
                roboger.core.log_traceback()
                self._destroyed = True

    def set_location(self, location='', dbconn=None):
        self.location = location if location else ''
        self.save(dbconn=dbconn)

    def set_keywords(self, keywords='', dbconn=None):
        if not keywords:
            self.keywords = []
        elif isinstance(keywords, list):
            self.keywords = keywords
        elif isinstance(keywords, str):
            self.keywords = list(
                filter(None, [x.strip() for x in keywords.split(',')]))
        else:
            self.keywords = []
        self.save(dbconn=dbconn)

    def set_senders(self, senders='', dbconn=None):
        if isinstance(senders, list):
            self.senders = senders
        elif isinstance(senders, str):
            self.senders = list(
                filter(None, [x.strip() for x in senders.split(',')]))
        else:
            self.senders = []
        self.save(dbconn=dbconn)

    def set_level(self, level_id=20, level_match='ge', dbconn=None):
        self.level_id = level_id if level_id else 20
        self.level_match = level_match if level_match else 'ge'
        self.save(dbconn=dbconn)

    def serialize(self, for_endpoint=False):
        u = {}
        u['id'] = self.subscription_id
        u['addr_id'] = self.addr.addr_id
        u['endpoint_id'] = self.endpoint.endpoint_id
        u['active'] = self.active
        u['location'] = self.location
        u['keywords'] = self.keywords
        u['senders'] = self.senders
        u['level_id'] = self.level_id
        u['level'] = get_event_level_name(self.level_id)
        u['level_match'] = self.level_match
        if roboger.core.development: u['destroyed'] = self._destroyed
        return u

    def set_active(self, active=1, dbconn=None):
        self.active = active
        self.save(dbconn=dbconn)

    def save(self, dbconn=None):
        if self._destroyed: return
        if self.subscription_id:
            db.query('update subscription set active = %s, ' + \
                    'location = %s, keywords = %s, senders = %s,' + \
                    'level_id = %s, level_match = %s where id=%s',
                    (self.active, self.location, ','.join(self.keywords),
                        ','.join(self.senders),
                        self.level_id, self.level_match,
                        self.subscription_id) , True, dbconn)
        else:
            self.subscription_id = db.query('insert into subscription ' + \
                    '(addr_id, endpoint_id, active, location, keywords, ' + \
                    'senders, level_id, level_match) values (' + \
                    '%s, %s, %s, %s, %s, %s, %s, %s)',
                    (self.addr.addr_id, self.endpoint.endpoint_id,
                        self.active, self.location, ','.join(self.keywords),
                        ','.join(self.senders),
                        self.level_id, self.level_match) , True, dbconn)

    def destroy(self, dbconn=None):
        self._destroyed = True
        self.active = 0
        self.endpoint.remove_subscription(self)
        if self.subscription_id:
            db.query('delete from event_queue where subscription_id = %s',
                     (self.subscription_id,), True, dbconn)
            db.query('delete from subscription where id = %s',
                     (self.subscription_id,), True, dbconn)


class Event(object):

    def __init__(self,
                 addr,
                 event_id=None,
                 d=None,
                 scheduled=0,
                 delivered=0,
                 location='',
                 keywords='',
                 sender='',
                 level_id=20,
                 expires=86400,
                 subject='',
                 msg='',
                 media=None,
                 autosave=True):
        self._destroyed = False
        self.addr = addr
        self.d = d if d else \
                datetime.datetime.now()
        self.dd = None
        self.scheduled = scheduled
        self.delivered = delivered
        self.location = location if location else ''
        self.subject = subject if subject else ''
        self._destroyed = False
        if not keywords:
            self.keywords = []
        elif isinstance(keywords, list):
            self.keywords = keywords
        elif isinstance(keywords, str):
            self.keywords = list(
                filter(None, [x.strip() for x in keywords.split(',')]))
        else:
            self.keywords = []
        self.sender = sender if sender else ''
        self.level_id = level_id
        if expires: self.expires = expires
        self.msg = msg
        self.media = media
        self.formatted_subject = ''
        level_name = get_event_level_name(self.level_id)
        if level_name:
            self.formatted_subject = level_name
            if self.location:
                self.formatted_subject += ' @' + self.location
        else:
            if self.location:
                self.formatted_subject = self.location
        if self.subject: self.formatted_subject += ': ' + self.subject
        self.event_id = event_id
        if not event_id:
            try:
                if autosave: self.save()
            except:
                roboger.core.log_traceback()
                self._destroyed = True

    def get_hash(self):
        h = hashlib.sha256()
        h.update(self.location.encode())
        h.update('\x00'.encode())
        h.update((','.join(self.keywords)).encode())
        h.update('\x00'.encode())
        h.update(self.sender.encode())
        h.update('\x00'.encode())
        h.update(str(self.level_id).encode())
        h.update('\x00'.encode())
        h.update(self.subject.encode())
        h.update('\x00'.encode())
        h.update(self.msg.encode())
        h.update('\x00'.encode())
        if self.media: h.update(self.media)
        return h.hexdigest()

    def serialize(self, for_endpoint=False):
        u = {}
        u['id'] = self.event_id
        if not for_endpoint:
            u['addr_id'] = self.addr.addr_id
            u['scheduled'] = self.scheduled
            u['delivered'] = self.delivered
        u['d'] = self.d
        u['location'] = self.location
        u['keywords'] = self.keywords
        u['sender'] = self.sender
        u['level_id'] = self.level_id
        u['level'] = get_event_level_name(self.level_id)
        u['expires'] = self.expires
        u['subject'] = self.subject
        u['msg'] = self.msg
        u['media'] = base64.b64encode(self.media).decode() if self.media else ''
        if roboger.core.development: u['destroyed'] = self._destroyed
        return u

    def save(self, dbconn=None):
        if self._destroyed: return
        if self.event_id:
            if self.scheduled == self.delivered and not self.dd:
                self.dd = datetime.datetime.now()
            if roboger.core.keep_events:
                db.query('update event set scheduled=%s, delivered=%s, ' + \
                        'dd=%s where id=%s',
                        (self.scheduled, self.delivered,
                        self.dd, self.event_id),
                        True, dbconn)
        elif roboger.core.keep_events:
            # move logic out
            if db.db_engine == 'sqlite':
                binary_w = ''
                import sqlite3
                media = sqlite3.Binary(self.media.encode())
            else:
                binary_w = '_binary'
                media = self.media
            self.event_id = db.query('insert into event ' + \
                    '(addr_id, d, dd, scheduled, delivered, location,' + \
                    ' keywords, sender, ' + \
                    'level_id, expires, subject, msg, media) values ' + \
                    '(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,' + \
                    ' ' + binary_w + ' %s)',
                    (self.addr.addr_id, self.d, self.dd, self.scheduled,
                        self.delivered, self.location, ','.join(self.keywords),
                        self.sender, self.level_id, self.expires, self.subject,
                        self.msg, media), True, dbconn)
        else:
            self.event_id = str(uuid.uuid4())

    def destroy(self, dbconn=None):
        self._destroyed = True
        if self.event_id and roboger.core.keep_events:
            db.query('delete from event where id = %s', (self.event_id,), True,
                     dbconn)
