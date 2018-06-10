__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2018 Altertech Group"
__license__ = "See https://www.roboger.com/"
__version__ = "1.0.0"

from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
import email.utils

import smtplib

from roboger import db
import roboger.core
import roboger.events

import requests
import logging
import jsonpickle
import datetime

import filetype

import time

from roboger.bots.telegram import RTelegramBot

endpoints_by_id = {}
endpoints_by_addr_id = {}

telegram_bot_token = None
telegram_poll_interval = 1

telegram_bot = None

endpoint_types = {}


def update_config(cfg):
    global telegram_bot_token, telegram_poll_interval
    global telegram_bot
    try:
        telegram_bot_token = cfg.get('endpoint_telegram', 'bot_token')
        logging.debug('endpoint.telegram bot token loaded')
    except:
        pass
    try:
        telegram_poll_interval = \
                int(cfg.get('endpoint_telegram', 'poll_interval'))
    except:
        pass
    if telegram_bot_token:
        logging.debug('endpoint.telegram.poll_interval = %s' % \
                telegram_poll_interval)
        telegram_bot = RTelegramBot(telegram_bot_token)
    return True


def start():
    global telegram_bot
    roboger.core.append_stop_func(stop)
    if telegram_bot:
        telegram_bot.poll_interval = telegram_poll_interval
        if telegram_bot.test():
            telegram_bot.start()
        else:
            logging.error('Failed to start RTelegramBot')


def stop():
    if telegram_bot:
        telegram_bot.stop()


def get_endpoint(endpoint_id):
    endpoint = endpoints_by_id.get(endpoint_id)
    if not endpoint: return None
    return None if endpoint._destroyed else endpoint


def append_endpoint(e):
    endpoints_by_id[e.endpoint_id] = e
    if e.addr.addr_id not in endpoints_by_addr_id:
        endpoints_by_addr_id[e.addr.addr_id] = {}
    endpoints_by_addr_id[e.addr.addr_id][e.endpoint_id] = e
    e.addr.append_endpoint(e)


def destroy_endpoint(e, dbconn=None):
    if isinstance(e, int):
        _e = get_endpoint(e)
    else:
        _e = e
    _e.destroy(dbconn)
    try:
        del endpoints_by_id[_e.endpoint_id]
        del endpoints_by_addr_id[_e.addr.addr_id][_e.endpoint_id]
    except:
        roboger.core.log_traceback()


def destroy_endpoints_by_addr(u, dbconn=None):
    if u.addr_id not in endpoints_by_addr_id: return
    for e in endpoints_by_addr_id[u.addr_id].copy():
        destroy_endpoint(e, dbconn)
    try:
        del endpoints_by_addr_id[u.addr_id]
    except:
        roboger.core.log_traceback()


def load():
    c = db.query('select id, name from endpoint_type')
    while True:
        row = c.fetchone()
        if row is None: break
        endpoint_types[row[0]] = row[1]
    c.close()
    c = db.query('select id, addr_id, endpoint_type_id, ' + \
            'data, data2, data3, active, skip_dups, description from endpoint')
    while True:
        row = c.fetchone()
        if row is None: break
        u = roboger.addr.get_addr(row[1])
        if not u:
            logging.error('Addr %u not found but endpoints exist!' % row[1])
            continue
        e = None
        if row[2] == 2:
            e = EmailEndpoint(
                    u, row[3], row[0], row[6], row[7], row[8])
        elif row[2] == 3:
            e = HTTPPostEndpoint(
                    u, row[3], row[5], row[0], row[6], row[7], row[8])
        elif row[2] == 4:
            e = HTTPJSONEndpoint(
                    u, row[3], row[5], row[0], row[6], row[7], row[8])
        elif row[2] == 100:
            e = SlackEndpoint(u, row[3], row[4], row[0], row[6], row[7], row[8])
        elif row[2] == 101:
            e = TelegramEndpoint(u, row[3], row[0], row[6], row[7], row[8])
        append_endpoint(e)
    c.close()
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
        self.endpoint_id = endpoint_id
        if not endpoint_id:
            try:
                if autosave: self.save()
            except:
                roboger.core.log_traceback()
                self._destroyed = True

    def append_subscription(self, s):
        self.subscriptions.append(s)

    def check_dup(self, event):
        if self.skip_dups <= 0: return True
        h = event.get_hash()
        if self.last_event_hash and self.last_event_time and \
                 h == self.last_event_hash  and \
                 time.time() - self.last_event_time < self.skip_dups:
            logging.info('endpoint %s duplicate event' % \
                self.endpoint_id)
            return False
        self.last_event_hash = h
        self.last_event_time = time.time()
        return True

    def remove_subscription(self, s):
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
        if roboger.core.development: u['destroyed'] = self._destroyed
        return u

    def set_data(self, data='', data2='', data3='', dbconn=None):
        self.data = data if data else ''
        self.data2 = data2 if data2 else ''
        self.data3 = data3 if data3 else ''
        self.save(dbconn=dbconn)

    def set_skip_dups(self, skip_dups=0, dbconn=None):
        try:
            self.skip_dups = int(skip_dups)
        except:
            self.skip_dups = 0
        self.save(dbconn=dbconn)

    def set_description(self, description='', dbconn=None):
        self.description = description if description else ''
        self.save(dbconn=dbconn)

    def set_active(self, active=1, dbconn=None):
        self.active = active
        self.save(dbconn)

    def save(self, dbconn=None):
        if self._destroyed: return
        if self.endpoint_id:
            db.query('update endpoint set active = %s, skip_dups = %s, ' + \
                    'description = %s, data = %s, data2 = %s, data3 = %s' + \
                    ' where id = %s',
                    (self.active, self.skip_dups, self.description,
                        self.data, self.data2, self.data3, self.endpoint_id),
                    True, dbconn)
        else:
            self.endpoint_id = db.query(
                    'insert into endpoint(addr_id, endpoint_type_id,' + \
                    ' data, data2, data3, active, skip_dups, description) ' + \
                    'values (%s, %s, %s, %s, %s, %s, %s, %s)',
                    (self.addr.addr_id, self.type_id,
                        self.data, self.data2, self.data3, self.active,
                        self.skip_dups, self.description),
                    True, dbconn)

    def destroy(self, dbconn):
        self._destroyed = True
        self.active = 0
        self.addr.remove_endpoint(self)
        if self.endpoint_id:
            for s in self.subscriptions.copy():
                roboger.events.destroy_subscription(s, dbconn)
            db.query('delete from endpoint where id = %s', (self.endpoint_id,),
                     True, dbconn)

    def send(self, event):
        if not self.check_dup(event): return False
        return True


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

    def set_data(self, data=None, data2=None, data3=None, dbconn=None):
        self.rcpt = data
        super().set_data(data, data2, data3, dbconn)

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
        logging.info('sending event %u via endpoint %u' % \
                (event.event_id, self.endpoint_id))
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
            sm = smtplib.SMTP(roboger.core.smtp_host, roboger.core.smtp_port)
            sm.sendmail(event.sender, self.rcpt, msg.as_string())
            sm.close()
            return True
        except:
            logging.warning('failed to send event %u via endpoint %u' % \
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
        self.params = params
        super().__init__(
            addr,
            3,
            endpoint_id,
            url,
            data3=params,
            active=active,
            skip_dups=skip_dups,
            description=description,
            autosave=autosave)

    def serialize(self):
        d = super().serialize()
        d['url'] = self.url
        d['params'] = self.params
        return d

    def set_data(self, data=None, data2=None, data3=None, dbconn=None):
        self.url = data
        self.params = data3
        super().set_data(data, data2, data3, dbconn)

    def send(self, event):
        if not self.check_dup(event): return False
        if not self.url: return False
        data = event.serialize(for_endpoint=True)
        if self.params: data['params'] = self.params
        if data['keywords'] and isinstance(data['keywords'], list):
            data['keywords'] = ','.join(data['keywords'])
        if isinstance(data['d'], datetime.datetime):
            data['d'] = data['d'].strftime("%Y/%m/%d %H:%M:%S")
        logging.info('sending event %u via endpoint %u' % \
                (event.event_id, self.endpoint_id))
        try:
            logging.info('HTTPPostEndpoint sending event to %s' % self.url)
            r = requests.post(self.url, data=data, timeout=roboger.core.timeout)
            if r.status_code != 200:
                logging.info('HTTPPostEndpoint %s return code %s' % \
                        (self.url, r.status_code))
                return False
            return True
        except:
            logging.warning('failed to send event %u via endpoint %u' % \
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
            try:
                self.params = jsonpickle.decode(params)
            except:
                self.params = None
        else:
            self.params = None
        super().__init__(
            addr,
            4,
            endpoint_id,
            url,
            data3=params,
            active=active,
            skip_dups=skip_dups,
            description=description,
            autosave=autosave)

    def serialize(self):
        d = super().serialize()
        d['url'] = self.url
        d['params'] = self.params
        return d

    def set_data(self, data=None, data2=None, data3=None, dbconn=None):
        self.url = data
        if data3:
            try:
                self.params = jsonpickle.decode(data3)
            except:
                self.params = None
        else:
            self.params = None
        super().set_data(data, data2, data3, dbconn)

    def send(self, event):
        if not self.check_dup(event): return False
        if not self.url: return False
        data = event.serialize(for_endpoint=True)
        data['params'] = self.params
        if isinstance(data['d'], datetime.datetime):
            data['d'] = data['d'].strftime("%Y/%m/%d %H:%M:%S")
        logging.info('sending event %u via endpoint %u' % \
                (event.event_id, self.endpoint_id))
        try:
            logging.info('HTTPJSONEndpoint sending event to %s' % self.url)
            r = requests.post(self.url, json=data, timeout=roboger.core.timeout)
            if r.status_code != 200:
                logging.info('HTTPJSONEndpoint %s return code %s' % \
                        (self.url, r.status_code))
                return False
            return True
        except:
            logging.warning('failed to send event %u via endpoint %u' % \
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
        d['webhook'] = self.webhook
        d['rich_fmt'] = self.rich_fmt
        return d

    def set_data(self, data=None, data2=None, data3=None, dbconn=None):
        self.webhook = data
        self.rich_fmt = (data2 == 'rich')
        super().set_data(data, data2, data3, dbconn)

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
        logging.info('sending event %u via endpoint %u' % \
                (event.event_id, self.endpoint_id))
        try:
            r = requests.post(
                self.webhook, json=j, timeout=roboger.core.timeout)
            if r.status_code != 200:
                return False
            return True
        except:
            logging.warning('failed to send event %u via endpoint %u' % \
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
        if roboger.core.development:
            d['chat_id_plain'] = self._chat_id_plain
        else:
            d['chat_id_plain'] = True if self._chat_id_plain else None
        return d

    def set_data(self, data=None, data2=None, data3=None, dbconn=None):
        self._set_chat_id(data)
        super().set_data(data, data2, data3, dbconn)

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
                logging.info('Telegram endpoint %s: invalid chat id' % \
                        self.endpoint_id)
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
            logging.info('sending event %u via endpoint %u' % \
                    (event.event_id, self.endpoint_id))
            if not telegram_bot.send_message(self._chat_id_plain, msg,
                                             (event.level_id <= 10)):
                logging.warning('failed to send event %u via endpoint %u' % \
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
