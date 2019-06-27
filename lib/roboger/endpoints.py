__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2018-2019 Altertech Group"
__license__ = "Apache License 2.0"
__version__ = "1.0.2"

from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
import email.utils

import smtplib

import roboger.core
import roboger.events

import requests
import logging
import json
import datetime
import threading

import filetype

import time

from roboger.bots.telegram import RTelegramBot
from roboger.core import db

from sqlalchemy import text as sql

endpoints_by_id = {}
endpoints_by_addr_id = {}

telegram_bot = RTelegramBot()

endpoint_types = {}
endpoint_codes = {}

endpoints_lock = threading.RLock()

push_services = {}


def get_endpoint_code(name):
    return endpoint_codes.get(name)


def update_config(cfg):
    # android
    try:
        api_key = cfg.get('endpoint_android', 'api_key')
        if api_key:
            try:
                from pyfcm import FCMNotification
                push_service = FCMNotification(api_key=api_key)
                push_services['android'] = push_service
            except:
                roboger.core.log_traceback()
    except:
        pass
    # telegram
    try:
        telegram_bot_token = cfg.get('endpoint_telegram', 'bot_token')
        logging.debug('endpoint.telegram bot token loaded')
    except:
        telegram_bot_token = None
    try:
        telegram_poll_interval = int(
            cfg.get('endpoint_telegram', 'poll_interval'))
    except:
        telegram_poll_interval = 1
    if telegram_bot_token:
        logging.debug('endpoint.telegram.poll_interval = %s' % \
                telegram_poll_interval)
        telegram_bot.set_token(telegram_bot_token)
        telegram_bot.poll_interval = telegram_poll_interval
    return True


def start():
    if telegram_bot.is_ready():
        if telegram_bot.test():
            telegram_bot.start()
        else:
            logging.error('Failed to start RTelegramBot')


@roboger.core.shutdown
def stop():
    if telegram_bot:
        telegram_bot.stop()


def get_endpoint(endpoint_id):
    with endpoints_lock:
        endpoint = endpoints_by_id.get(endpoint_id)
    return endpoint if endpoint and not endpoint._destroyed else None


def append_endpoint(e):
    with endpoints_lock:
        try:
            endpoints_by_id[e.endpoint_id] = e
            if e.addr.addr_id not in endpoints_by_addr_id:
                endpoints_by_addr_id[e.addr.addr_id] = {}
            endpoints_by_addr_id[e.addr.addr_id][e.endpoint_id] = e
            e.addr.append_endpoint(e)
        except:
            roboger.core.log_traceback()


def destroy_endpoint(e):
    with endpoints_lock:
        if isinstance(e, int):
            _e = get_endpoint(e)
        else:
            _e = e
        _e.destroy()
        try:
            del endpoints_by_id[_e.endpoint_id]
            del endpoints_by_addr_id[_e.addr.addr_id][_e.endpoint_id]
        except:
            roboger.core.log_traceback()


def destroy_endpoints_by_addr(u):
    with endpoints_lock:
        if u.addr_id not in endpoints_by_addr_id: return
        try:
            for e in endpoints_by_addr_id[u.addr_id].copy():
                destroy_endpoint(e)
            del endpoints_by_addr_id[u.addr_id]
        except:
            roboger.core.log_traceback()


def load():
    c = db().execute(sql('select id, name from endpoint_type'))
    while True:
        r = c.fetchone()
        if r is None: break
        endpoint_types[r.id] = r.name
        endpoint_codes[r.name] = r.id
    c = db().execute(
        sql('select id, addr_id, endpoint_type_id, data, data2, ' +
            'data3, active, skip_dups, description from endpoint'))
    while True:
        r = c.fetchone()
        if r is None: break
        u = roboger.addr.get_addr(r.addr_id)
        if not u:
            logging.error('Addr %u not found but endpoints exist!' % r.addr_id)
            continue
        e = None
        if r.endpoint_type_id == 1:
            e = AndroidEndpoint(
                addr=u,
                device_id=r.data,
                endpoint_id=r.id,
                active=r.active,
                skip_dups=r.skip_dups,
                description=r.description)
        elif r.endpoint_type_id == 2:
            e = EmailEndpoint(
                addr=u,
                rcpt=r.data,
                endpoint_id=r.id,
                active=r.active,
                skip_dups=r.skip_dups,
                description=r.description)
        elif r.endpoint_type_id == 3:
            e = HTTPPostEndpoint(
                addr=u,
                url=r.data,
                params=r.data3,
                endpoint_id=r.id,
                active=r.active,
                skip_dups=r.skip_dups,
                description=r.description)
        elif r.endpoint_type_id == 4:
            e = HTTPJSONEndpoint(
                addr=u,
                url=r.data,
                params=r.data3,
                endpoint_id=r.id,
                active=r.active,
                skip_dups=r.skip_dups,
                description=r.description)
        elif r.endpoint_type_id == 100:
            e = SlackEndpoint(
                addr=u,
                webhook=r.data,
                fmt=r.data2,
                endpoint_id=r.id,
                active=r.active,
                skip_dups=r.skip_dups,
                description=r.description)
        elif r.endpoint_type_id == 101:
            e = TelegramEndpoint(
                addr=u,
                chat_id=r.data,
                endpoint_id=r.id,
                active=r.active,
                skip_dups=r.skip_dups,
                description=r.description)
        append_endpoint(e)
    logging.debug('endpoint: %u endpoint(s) loaded' % len(endpoints_by_id))
    return True


class GenericEndpoint(object):

    emoji_code = {
        20: u'\U00002139',
        30: u'\U000026A0',
        40: u'\U0000203C',
        50: u'\U0001F170'
    }

    def __init__(self,
                 addr,
                 type_id,
                 endpoint_id=None,
                 data='',
                 data2='',
                 data3='',
                 active=1,
                 skip_dups=0,
                 description='',
                 autosave=True):
        self._destroyed = False
        self.addr = addr
        self.type_id = type_id
        self.active = active
        self.data = data if data else ''
        self.data2 = data2 if data2 else ''
        self.data3 = data3 if data3 else ''
        self.description = description if description else ''
        self.skip_dups = skip_dups
        self.subscriptions = []
        self.lock = threading.RLock()
        self.endpoint_id = endpoint_id
        self.last_event_time = 0
        self.last_event_hash = None
        if not endpoint_id:
            try:
                if autosave: self.save()
            except:
                roboger.core.log_traceback()
                self._destroyed = True

    def append_subscription(self, s):
        with self.lock:
            self.subscriptions.append(s)

    def check_dup(self, event):
        if self.skip_dups <= 0: return True
        h = event.get_hash()
        if self.last_event_hash and self.last_event_time and \
                 h == self.last_event_hash  and \
                 time.time() - self.last_event_time < self.skip_dups:
            logging.info('endpoint %s duplicate event' % self.endpoint_id)
            return False
        self.last_event_hash = h
        self.last_event_time = time.time()
        return True

    def remove_subscription(self, s):
        with self.lock:
            self.subscriptions.remove(s)

    def serialize(self):
        u = {}
        u['id'] = self.endpoint_id
        u['addr_id'] = self.addr.addr_id
        u['data'] = self.data
        u['data2'] = self.data2
        u['data3'] = self.data3
        u['active'] = self.active
        u['skip_dups'] = self.skip_dups
        u['description'] = self.description
        u['type_id'] = self.type_id
        u['type'] = endpoint_types.get(self.type_id)
        if roboger.core.is_development(): u['destroyed'] = self._destroyed
        return u

    def set_data(self, data='', data2='', data3=''):
        self.data = data if data else ''
        self.data2 = data2 if data2 else ''
        self.data3 = data3 if data3 else ''
        self.save()

    def set_skip_dups(self, skip_dups=0):
        try:
            self.skip_dups = int(skip_dups)
        except:
            self.skip_dups = 0
        self.save()

    def set_description(self, description=''):
        self.description = description if description else ''
        self.save()

    def set_active(self, active=1):
        self.active = active
        self.save()

    def save(self):
        if self._destroyed: return
        if self.endpoint_id:
            db().execute(
                sql('update endpoint set active = :active, ' +
                    'skip_dups = :skip_dups, ' +
                    'description = :description, data = :data, ' +
                    'data2 = :data2, data3 = :data3 where id = :id'),
                active=self.active,
                skip_dups=self.skip_dups,
                description=self.description,
                data=self.data,
                data2=self.data2,
                data3=self.data3,
                id=self.endpoint_id)
        else:
            self.endpoint_id = db().execute(
                sql('insert into endpoint(addr_id, endpoint_type_id, ' +
                    'data, data2, data3, active, skip_dups, description) ' +
                    'values (:addr_id, :type_id, :data, :data2, :data3, ' +
                    ':active, :skip_dups, :description)'),
                addr_id=self.addr.addr_id,
                type_id=self.type_id,
                data=self.data,
                data2=self.data2,
                data3=self.data3,
                active=self.active,
                skip_dups=self.skip_dups,
                description=self.description).lastrowid

    def destroy(self):
        self._destroyed = True
        self.active = 0
        self.addr.remove_endpoint(self)
        if self.endpoint_id:
            for s in self.subscriptions.copy():
                roboger.events.destroy_subscription(s)
            db().execute(
                sql('delete from endpoint where id = :id'), id=self.endpoint_id)

    def send(self, event):
        if not self.check_dup(event): return False
        return True


class AndroidEndpoint(GenericEndpoint):

    def __init__(self,
                 addr,
                 device_id,
                 endpoint_id=None,
                 active=1,
                 skip_dups=0,
                 description='',
                 autosave=True):
        self.device_id = device_id
        super().__init__(
            addr,
            1,
            endpoint_id,
            rcpt,
            active=active,
            description=description,
            skip_dups=skip_dups,
            autosave=autosave)

    def serialize(self):
        d = super().serialize()
        d['device_id'] = self.device_id
        return d

    def set_config(self, config):
        self.set_data(config.get('device_id', ''))

    def set_data(self, data=None, data2=None, data3=None):
        self.device_id = data
        super().set_data(data, data2, data3)

    def send(self, event):
        if not 'android' in push_services: return False
        if not self.check_dup(event): return False
        if not self.active or event._destroyed: return True
        if not self.device_id: return False
        if not event.sender: return False
        data = event.serialize(for_endpoint=True)
        logging.info('sending event %s via endpoint %u' % (event.event_id,
                                                           self.endpoint_id))
        try:
            logging.info(
                'Android endpoint sending event to %s' % self.device_id)
            push_services['android'].single_device_data_message(
                registration_id=self.device_id, data_message=data)
        except:
            logging.warning('failed to send event %s via endpoint %u' %
                            (event.event_id, self.endpoint_id))
            roboger.core.log_traceback()
            return False


class EmailEndpoint(GenericEndpoint):

    def __init__(self,
                 addr,
                 rcpt,
                 endpoint_id=None,
                 active=1,
                 skip_dups=0,
                 description='',
                 autosave=True):
        self.rcpt = rcpt
        super().__init__(
            addr,
            2,
            endpoint_id,
            rcpt,
            active=active,
            description=description,
            skip_dups=skip_dups,
            autosave=autosave)

    def serialize(self):
        d = super().serialize()
        d['rcpt'] = self.rcpt
        return d

    def set_config(self, config):
        self.set_data(config.get('rcpt', ''))

    def set_data(self, data=None, data2=None, data3=None):
        self.rcpt = data
        super().set_data(data, data2, data3)

    def send(self, event):
        if not self.check_dup(event): return False
        if not self.active or event._destroyed: return True
        if not self.rcpt: return False
        if not event.sender: return False
        t = event.msg if event.msg else ''
        if event.media:
            msg = MIMEMultipart()
        else:
            msg = MIMEText(t)
        logging.info('sending event %s via endpoint %u' % (event.event_id,
                                                           self.endpoint_id))
        msg['Subject'] = event.formatted_subject
        msg['From'] = event.sender
        msg['To'] = self.rcpt
        if event.media:
            msg.attach(MIMEText(t))
            ft = filetype.guess(event.media)
            if ft is None:
                fname = 'attachment.txt'
            else:
                fname = 'attachment.' + ft.extension
            a = MIMEApplication(event.media, Name=fname)
            a['Content-Disposition'] = 'attachment; filename="%s"' % fname
            msg.attach(a)
        try:
            logging.info('EmailEndpoint sending event to %s' % self.rcpt)
            host, port = roboger.core.smtp_config()
            sm = smtplib.SMTP(host, port)
            sm.sendmail(event.sender, self.rcpt, msg.as_string())
            sm.close()
            return True
        except:
            logging.warning('failed to send event %s via endpoint %u' %
                            (event.event_id, self.endpoint_id))
            roboger.core.log_traceback()
            return False


class HTTPPostEndpoint(GenericEndpoint):

    def __init__(self,
                 addr,
                 url,
                 params=None,
                 endpoint_id=None,
                 active=1,
                 skip_dups=0,
                 description='',
                 autosave=True):
        self.url = url
        if params:
            if isinstance(params, dict):
                self.params = params
            else:
                try:
                    self.params = json.loads(params)
                except:
                    self.params = None
        else:
            self.params = None
        super().__init__(
            addr,
            3,
            endpoint_id,
            url,
            data3=json.dumps(self.params),
            active=active,
            skip_dups=skip_dups,
            description=description,
            autosave=autosave)

    def serialize(self):
        d = super().serialize()
        d['url'] = self.url
        d['params'] = self.params
        return d

    def set_config(self, config):
        params = config.get('params', '')
        self.set_data(config.get('url', ''), data3=params)

    def set_data(self, data=None, data2=None, data3=None):
        self.url = data
        if data3:
            try:
                self.params = json.loads(data3)
            except:
                self.params = None
        else:
            self.params = None
        super().set_data(data, data2, data3)

    def send(self, event):
        if not self.check_dup(event): return False
        if not self.url: return False
        data = event.serialize(for_endpoint=True)
        if self.params: data['params'] = self.params
        if data['keywords'] and isinstance(data['keywords'], list):
            data['keywords'] = ','.join(data['keywords'])
        if isinstance(data['d'], datetime.datetime):
            data['d'] = data['d'].strftime("%Y/%m/%d %H:%M:%S")
        logging.info('sending event %s via endpoint %u' % (event.event_id,
                                                           self.endpoint_id))
        try:
            logging.info('HTTPPostEndpoint sending event to %s' % self.url)
            r = requests.post(
                self.url, data=data, timeout=roboger.core.timeout())
            if r.status_code != 200:
                logging.info('HTTPPostEndpoint %s return code %s' %
                             (self.url, r.status_code))
                return False
            return True
        except:
            logging.warning('failed to send event %s via endpoint %u' %
                            (event.event_id, self.endpoint_id))
            roboger.core.log_traceback()
            return False


class HTTPJSONEndpoint(GenericEndpoint):

    def __init__(self,
                 addr,
                 url,
                 params=None,
                 endpoint_id=None,
                 active=1,
                 skip_dups=0,
                 description='',
                 autosave=True):
        self.url = url
        if params:
            if isinstance(params, dict):
                self.params = params
            else:
                try:
                    self.params = json.loads(params)
                except:
                    self.params = None
        else:
            self.params = None
        super().__init__(
            addr,
            4,
            endpoint_id,
            url,
            data3=json.dumps(self.params),
            active=active,
            skip_dups=skip_dups,
            description=description,
            autosave=autosave)

    def serialize(self):
        d = super().serialize()
        d['url'] = self.url
        d['params'] = self.params
        return d

    def set_config(self, config):
        params = config.get('params', '')
        self.set_data(config.get('url', ''), data3=params)

    def set_data(self, data=None, data2=None, data3=None):
        self.url = data
        if data3:
            try:
                self.params = json.loads(data3)
            except:
                self.params = None
        else:
            self.params = None
        super().set_data(data, data2, data3)

    def send(self, event):
        if not self.check_dup(event): return False
        if not self.url: return False
        data = event.serialize(for_endpoint=True)
        data['params'] = self.params
        if isinstance(data['d'], datetime.datetime):
            data['d'] = data['d'].strftime("%Y/%m/%d %H:%M:%S")
        logging.info('sending event %s via endpoint %u' % (event.event_id,
                                                           self.endpoint_id))
        try:
            logging.info('HTTPJSONEndpoint sending event to %s' % self.url)
            r = requests.post(
                self.url, json=data, timeout=roboger.core.timeout())
            if r.status_code != 200:
                logging.info('HTTPJSONEndpoint %s return code %s' %
                             (self.url, r.status_code))
                return False
            return True
        except:
            logging.warning('failed to send event %s via endpoint %u' %
                            (event.event_id, self.endpoint_id))
            roboger.core.log_traceback()
            return False


class SlackEndpoint(GenericEndpoint):

    slack_color = {
        10: '#555555',
        20: 'good',
        30: 'warning',
        40: 'danger',
        50: '#FF2222'
    }

    def __init__(self,
                 addr,
                 webhook,
                 fmt='plain',
                 endpoint_id=None,
                 active=1,
                 skip_dups=0,
                 description='',
                 autosave=True):
        self.webhook = webhook
        self.rich_fmt = (fmt == 'rich')
        super().__init__(
            addr,
            100,
            endpoint_id,
            webhook,
            fmt,
            active=active,
            skip_dups=skip_dups,
            description=description,
            autosave=autosave)

    def serialize(self):
        d = super().serialize()
        d['url'] = self.webhook
        d['rich_fmt'] = self.rich_fmt
        return d

    def set_config(self, config):
        url = config.get('url')
        if not url:
            url = config.get('webhook')
        self.set_data(url, config.get('fmt'))

    def set_data(self, data=None, data2=None, data3=None):
        self.webhook = data
        self.rich_fmt = (data2 == 'rich')
        super().set_data(data, data2, data3)

    def send(self, event):
        if not self.check_dup(event): return False
        if not self.webhook: return False
        if self.rich_fmt:
            j = {'text': ''}
            color = self.slack_color.get(event.level_id)
            if not color: color = 'good'
            j['attachments'] = [{
                'fallback':
                event.formatted_subject,
                'color':
                color,
                'fields': [{
                    'title': event.formatted_subject,
                    'value': event.msg,
                    'short': event.subject
                }]
            }]
        else:
            msg = event.formatted_subject + '\n' + event.msg
            j = {'text': msg}
        if event.sender:
            j['username'] = event.sender
        logging.info('sending event %s via endpoint %u' % (event.event_id,
                                                           self.endpoint_id))
        try:
            r = requests.post(
                self.webhook, json=j, timeout=roboger.core.timeout())
            if r.status_code != 200:
                return False
            return True
        except:
            logging.warning('failed to send event %s via endpoint %u' %
                            (event.event_id, self.endpoint_id))
            roboger.core.log_traceback()
            return False


class TelegramEndpoint(GenericEndpoint):

    def __init__(self,
                 addr,
                 chat_id=None,
                 endpoint_id=None,
                 active=1,
                 skip_dups=0,
                 description='',
                 autosave=True):
        super().__init__(
            addr,
            101,
            endpoint_id,
            chat_id,
            active=active,
            skip_dups=skip_dups,
            description=description,
            autosave=autosave)
        self._set_chat_id(chat_id)

    def serialize(self):
        d = super().serialize()
        d['chat_id'] = self.chat_id
        if roboger.core.is_development():
            d['chat_id_plain'] = self._chat_id_plain
        else:
            d['chat_id_plain'] = True if self._chat_id_plain else None
        return d

    def set_config(self, config):
        self.set_data(config.get('chat_id'))

    def set_data(self, data=None, data2=None, data3=None):
        self._set_chat_id(data)
        super().set_data(data, data2, data3)

    def _set_chat_id(self, chat_id):
        if chat_id:
            try:
                self.chat_id = chat_id
                self._chat_id_plain = \
                        int(telegram_bot.ce.decrypt(chat_id.encode())) if \
                            telegram_bot else None
            except:
                self.chat_id = None
                self._chat_id_plain = None
                logging.info(
                    'Telegram endpoint %s: invalid chat id' % self.endpoint_id)
        else:
            self.chat_id = None
            self._chat_id_plain = None

    def send(self, event):
        if not self.check_dup(event): return False
        if self._chat_id_plain:
            msg = '<pre>%s</pre>\n' % event.sender if event.sender else ''
            em = '' if event.level_id not in self.emoji_code else \
                    self.emoji_code.get(event.level_id) + ' '
            msg += '<b>' + em + event.formatted_subject + \
                    '</b>\n'
            msg += event.msg
            logging.info('sending event %s via endpoint %u' %
                         (event.event_id, self.endpoint_id))
            if not telegram_bot.send_message(self._chat_id_plain, msg,
                                             (event.level_id <= 10)):
                logging.warning('failed to send event %s via endpoint %u' %
                                (event.event_id, self.endpoint_id))
                return False
            if event.media:
                ft = filetype.guess(event.media)
                if ft:
                    mt = ft.mime.split('/')[0]
                else:
                    mt = None
                if mt == 'image': send_func = telegram_bot.send_photo
                elif mt == 'video': send_func = telegram_bot.send_video
                elif mt == 'audio': send_func = telegram_bot.send_audio
                else: send_func = telegram_bot.send_document
                if not send_func(self._chat_id_plain,
                                 '<pre>%s</pre>' % event.sender, event.media,
                                 (event.level_id <= 10)):
                    return False
            return True
        return False
