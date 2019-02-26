__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2018-2019 Altertech Group"
__license__ = "Apache License 2.0"
__version__ = "1.0.1"

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
from roboger.core import db
from roboger.threads import BackgroundWorker

from sqlalchemy import text as sql

level_names = {
    10: 'DEBUG',
    20: 'INFO',
    30: 'WARNING',
    40: 'ERROR',
    50: 'CRITICAL'
}

level_codes = {'d': 10, 'i': 20, 'w': 30, 'e': 40, 'c': 50}

event_clean_interval = 60


class QueueProcessor(BackgroundWorker):

    def __init__(self):
        super().__init__(name='_t_queue_processor')

    def run(self):
        while self.is_active() or not roboger.core.get_keep_events():
            eq = q.get()
            if not eq or \
                    (roboger.core.get_keep_events() and not self.is_active()):
                break
            if eq.subscription._destroyed: continue
            logging.info(
                'Sending queued event id: %s' % eq.event.event_id +
                ', endpoint id: %s' % eq.subscription.endpoint.endpoint_id +
                ', subscription id: %s' % eq.subscription.subscription_id +
                ', addr id: %s, addr: %s' %
                (eq.event.addr.addr_id, eq.event.addr.a))
            t = threading.Thread(target=eq.send)
            t.start()
            eq.mark_delivered()

    def after_stop(self):
        q.put(None)


class EventCleaner(BackgroundWorker):

    def __init__(self):
        super().__init__(name='_t_event_cleaner')

    def run(self):
        clean_interval = event_clean_interval
        c = clean_interval
        while self.is_active():
            c += 1
            if c > clean_interval:
                logging.debug('cleaning old events')
                try:
                    # move this logic out
                    if roboger.core.db_type() == 'sqlite':
                        q = ('delete from event where d < ' +
                             'datetime(current_timestamp, ' +
                             '"localtime", "-%s second")' %
                             roboger.core.get_keep_events())
                    elif roboger.core.db_type() == 'mysql':
                        q = ('delete from event where d<NOW() ' +
                             ' - INTERVAL %s SECOND' %
                             roboger.core.get_keep_events())
                    else:
                        q = None
                    if q:
                        db().execute(sql(q))
                except:
                    roboger.core.log_traceback()
                c = 0
            time.sleep(1)


def push_event(a,
               level,
               sender='',
               location='',
               keywords='',
               subject='',
               expires='',
               msg='',
               media=None):
    addr = roboger.addr.get_addr(a=a)
    if not addr:
        logging.info('push: no such address %s' % a)
        return None
    if addr.active != 1:
        logging.info(
            'push: skipping event for address %s, status %s' % (a, addr.active))
        return addr.active
    logging.info('push: new event for address %s' % a)
    try:
        e = Event(
            addr=addr,
            level_id=level,
            location=location,
            keywords=keywords,
            sender=sender,
            subject=subject,
            msg=msg,
            media=media,
            expires=expires,
            autosave=False)
        e.save()
        queue_event(e)
        return True
    except:
        roboger.core.log_traceback()
        return False


@roboger.core.shutdown
def stop():
    queue_processor.stop()
    event_cleaner.stop()
    return


def start():
    queue_processor.start()
    if roboger.core.get_keep_events():
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
    with subscriptions_lock:
        s = subscriptions_by_id.get(s_id)
    return s if s and not s._destroyed else None


def queue_event(event):
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
            eq.save(initial=True)
            event.scheduled += 1
            event.save()
            q.put(eq)


def destroy_subscription(s):
    if isinstance(s, int):
        _s = get_subscription(s)
    else:
        _s = s
    _s.destroy()
    with subscriptions_lock:
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
    with subscriptions_lock:
        try:
            subscriptions_by_id[s.subscription_id] = s
            if u.addr_id not in subscriptions_by_addr_id:
                subscriptions_by_addr_id[u.addr_id] = {}
            if e.endpoint_id not in subscriptions_by_endpoint_id:
                subscriptions_by_endpoint_id[e.endpoint_id] = {}
            subscriptions_by_addr_id[u.addr_id][s.subscription_id] = s
            subscriptions_by_endpoint_id[e.endpoint_id][s.subscription_id] = s
        except:
            roboger.core.log_traceback()


def load_subscriptions():
    c = db().execute(
        sql('select id, addr_id, endpoint_id, active, location, keywords, ' +
            'senders, level_id, level_match from subscription'))
    while True:
        r = c.fetchone()
        if r is None: break
        u = roboger.addr.get_addr(addr_id=r.addr_id)
        e = roboger.endpoints.get_endpoint(endpoint_id=r.endpoint_id)
        if not u:
            logging.error(
                'Addr %u not found but subscriptions exist!' % r.addr_id)
            continue
        if not e:
            logging.error('Endpoint %u not found but subscriptions exist!' %
                          r.endpoint_id)
            continue
        s = EventSubscription(
            addr=u,
            endpoint=e,
            subscription_id=r.id,
            active=r.active,
            location=r.location,
            keywords=r.keywords,
            senders=r.senders,
            level_id=r.level_id,
            level_match=r.level_match)
        append_subscription(s)
    logging.debug('endpoint subscriptions: %u subscription(s) loaded' %
                  len(subscriptions_by_id))
    return True


def load_queued_events():
    c = db().execute(
        sql('select event_id, subscription_id, addr_id, d,' +
            ' scheduled, delivered, location, keywords, sender, level_id, ' +
            'expires, subject, msg, media from event_queue join event' +
            ' on event.id = event_queue.event_id where status < 1'))
    cqe = 0
    while True:
        r = c.fetchone()
        if r is None: break
        u = roboger.addr.get_addr(r.addr_id)
        if not u:
            logging.error(
                'Addr %u not found but queued events exist!' % r.addr_id)
            continue
        s = get_subscription(r.subscription_id)
        if not s:
            logging.error('Subscription %u not found but queued events exist!' %
                          r.subscription_id)
            continue
        e = Event(
            addr=u,
            event_id=r.event_id,
            d=r.d,
            scheduled=r.scheduled,
            delivered=r.delivered,
            location=r.location,
            keywords=r.keywords,
            sender=r.sender,
            level_id=r.level_id,
            expires=r.expires,
            subject=r.subject,
            msg=r.msg,
            media=r.media,
            autosave=r.autosave)
        eq = EventQueueItem(e, s)
        cqe += 1
        q.put(eq)
    logging.debug('events: %u queued event(s) loaded' % cqe)


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

    def save(self, initial=False):
        if self._destroyed or not roboger.core.get_keep_events(): return True
        if initial:
            db().execute(
                sql('insert into event_queue (event_id, subscription_id, ' +
                    'status, dd) values (:event_id, :subscription_id, ' +
                    ' :status, :dd)'),
                event_id=self.event.event_id,
                subscription_id=self.subscription.subscription_id,
                status=self.status,
                dd=self.dd)
        else:
            db().execute(
                sql('update event_queue set status=:status, dd=:dd ' +
                    'where event_id=event_id and ' +
                    'subscription_id=:subscription_id'),
                status=self.status,
                dd=self.dd,
                event_id=self.event.event_id,
                subscription_id=self.subscription.subscription_id)
        return True

    def mark_delivered(self):
        self.dd = datetime.datetime.now()
        self.status = 1
        self.save()
        self.event.delivered += 1
        self.event.save()

    def destroy():
        self._destroyed = True
        db().execute(
            sql('delete from event_queue where event_id=:event_id and ' +
                'subscription_id=:subscription_id'),
            event_id=self.event.event_id,
            subscription_id=self.subscription.subscription_id)


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

    def set_location(self, location=''):
        self.location = location if location else ''
        self.save()

    def set_keywords(self, keywords=''):
        if not keywords:
            self.keywords = []
        elif isinstance(keywords, list):
            self.keywords = keywords
        elif isinstance(keywords, str):
            self.keywords = list(
                filter(None, [x.strip() for x in keywords.split(',')]))
        else:
            self.keywords = []
        self.save()

    def set_senders(self, senders=''):
        if isinstance(senders, list):
            self.senders = senders
        elif isinstance(senders, str):
            self.senders = list(
                filter(None, [x.strip() for x in senders.split(',')]))
        else:
            self.senders = []
        self.save()

    def set_level(self, level_id=20, level_match='ge'):
        self.level_id = level_id if level_id else 20
        self.level_match = level_match if level_match else 'ge'
        self.save()

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
        if roboger.core.is_development(): u['destroyed'] = self._destroyed
        return u

    def set_active(self, active=1):
        self.active = active
        self.save()

    def save(self):
        if self._destroyed: return
        if self.subscription_id:
            db().execute(
                sql('update subscription set active = :active, ' +
                    'location = :location, keywords = :keywords, ' +
                    'senders = :senders, level_id = :level_id, ' +
                    'level_match = :level_match where id=:id'),
                active=self.active,
                location=self.location,
                keywords=','.join(self.keywords),
                senders=','.join(self.senders),
                level_id=self.level_id,
                level_match=self.level_match,
                id=self.subscription_id)
        else:
            self.subscription_id = db().execute(
                sql('insert into subscription (addr_id, endpoint_id, ' +
                    'active, location, keywords, senders, level_id, ' +
                    'level_match) values (:addr_id, :endpoint_id, ' +
                    ':active, :location, :keywords, :senders, :level_id,' +
                    ':level_match)'),
                addr_id=self.addr.addr_id,
                endpoint_id=self.endpoint.endpoint_id,
                active=self.active,
                location=self.location,
                keywords=','.join(self.keywords),
                senders=','.join(self.senders),
                level_id=self.level_id,
                level_match=self.level_match).lastrowid

    def destroy(self):
        self._destroyed = True
        self.active = 0
        self.endpoint.remove_subscription(self)
        if self.subscription_id:
            db().execute(
                sql('delete from event_queue where subscription_id = :id'),
                id=self.subscription_id)
            db().execute(
                sql('delete from subscription where id = :id'),
                id=self.subscription_id)


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
        if roboger.core.is_development(): u['destroyed'] = self._destroyed
        return u

    def save(self):
        if self._destroyed: return
        if self.event_id:
            if self.scheduled == self.delivered and not self.dd:
                self.dd = datetime.datetime.now()
            if roboger.core.get_keep_events():
                db().execute(
                    sql('update event set scheduled=:scheduled, ' +
                        'delivered=:delivered, dd=:dd where id=:id'),
                    scheduled=self.scheduled,
                    delivered=self.delivered,
                    dd=self.dd,
                    id=self.event_id)
        elif roboger.core.get_keep_events():
            # move logic out
            # if db.database.engine == 'sqlite':
            # binary_w = ''
            # import sqlite3
            # if isinstance(self.media, str):
            # media = sqlite3.Binary(self.media.encode())
            # else:
            # media = sqlite3.Binary(self.media)
            # else:
            # binary_w = '_binary'
            # media = self.media
            self.event_id = db().execute(
                sql('insert into event (addr_id, d, dd, scheduled, ' +
                    'delivered, location, keywords, sender, level_id, ' +
                    'expires, subject, msg, media) values (:addr_id, :d, ' +
                    ':dd, :scheduled, :delivered, :location, :keywords, ' +
                    ':sender, :level_id, :expires, :subject, :msg, :media)'),
                addr_id=self.addr.addr_id,
                d=self.d,
                dd=self.dd,
                scheduled=self.scheduled,
                delivered=self.delivered,
                location=self.location,
                keywords=','.join(self.keywords),
                sender=self.sender,
                level_id=self.level_id,
                expires=self.expires,
                subject=self.subject,
                msg=self.msg,
                media=self.media).lastrowid
        else:
            self.event_id = str(uuid.uuid4())

    def destroy(self):
        self._destroyed = True
        if self.event_id and roboger.core.get_keep_events():
            db().execute(
                sql('delete from event where id = :id'), id=self.event_id)


q = Queue()

subscriptions_by_id = {}
subscriptions_by_addr_id = {}
subscriptions_by_endpoint_id = {}

subscriptions_lock = threading.RLock()

queue_processor = QueueProcessor()
event_cleaner = EventCleaner()
