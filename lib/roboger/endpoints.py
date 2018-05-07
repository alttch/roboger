__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2018 Altertech Group"
__license__ = "See https://www.roboger.com/"
__version__ = "0.0.1"

from email.mime.text import MIMEText
import smtplib

from roboger import db
import roboger.core
import roboger.events

import requests
import logging

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
    except: pass
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


def destroy_endpoint(e, dbconn = None):
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


def destroy_endpoints_by_addr(u, dbconn = None):
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
            'data, data2, data3, active, description from endpoint')
    while True:
        row = c.fetchone()
        if row is None: break
        u = roboger.addr.get_addr(row[1])
        if not u:
            logging.error('Addr %u not found but endpoints exist!' % row[1])
            continue
        e = None
        if row[2] == 2:
            e = EmailEndpoint(u, row[3], row[0], row[6], row[7])
        elif row[2] == 3:
            e = HTTPJSONEndpoint(u, row[3], row[0], row[6], row[7])
        elif row[2] == 4:
            e = HTTPPostEndpoint(u, row[3], row[0], row[6], row[7])
        elif row[2] == 100:
            e = SlackEndpoint(u, row[3], row[4], row[0], row[6], row[7])
        elif row[2] == 101:
            e = TelegramEndpoint(u, row[3], row[0], row[6], row[7])
        append_endpoint(e)
    c.close()
    logging.debug('endpoint: %u endpoint(s) loaded' % len(endpoints_by_id))
    return True


class GenericEndpoint(object):

    endpoint_id = None
    addr = None
    data = None
    data2 = None
    data3 = None
    description = ''
    active = 1
    type_id = None
    _destroyed = False
    subscriptions = []

    def __init__(self, addr, type_id, endpoint_id = None,
            data = '', data2 = '', data3 = '', active = 1,
            description = '', autosave = True):
        self.addr = addr
        self.type_id = type_id
        self.active = active
        self.data = data if data else ''
        self.data2 = data2 if data2 else ''
        self.data3 = data3 if data3 else ''
        self.description = description if description else ''
        if endpoint_id:
            self.endpoint_id = endpoint_id
        else:
            try:
                if autosave: self.save()
            except:
                roboger.core.log_traceback()
                self._destroyed = True


    def append_subscription(self, s):
        self.subscriptions.append(s)


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
        u['description'] = self.description
        u['type_id' ] = self.type_id
        u['type'] = endpoint_types.get(self.type_id)
        if roboger.core.development: u['destroyed'] = self._destroyed
        return u


    def set_data(self, data = '', data2 = '', data3 = '', dbconn = None):
        self.data = data if data else ''
        self.data2 = data2 if data2 else ''
        self.data3 = data3 if data3 else ''
        self.save(dbconn = dbconn)


    def set_description(self, description = '', dbconn = None):
        self.description = description if description else ''
        self.save(dbconn = dbconn)


    def set_active(self, active = 1, dbconn = None):
        self.active = active
        self.save(dbconn)


    def save(self, dbconn = None):
        if self._destroyed: return
        if self.endpoint_id:
            db.query('update endpoint set active = %s, description = %s, ' + \
                    'data = %s, data2 = %s, data3 = %s' + \
                    ' where id = %s',
                    (self.active, self.description, self.data, self.data2,
                        self.data3, self.endpoint_id), True, dbconn)
        else:
            self.endpoint_id = db.query(
                    'insert into endpoint(addr_id, endpoint_type_id,' + \
                    ' data, data2, data3, active, description) values ' + \
                    ' (%s, %s, %s, %s, %s, %s, %s)',
                    (self.addr.addr_id, self.type_id,
                        self.data, self.data2, self.data3, self.active,
                        self.description),
                    True, dbconn)


    def destroy(self, dbconn):
        self._destroyed = True
        self.active = 0
        self.addr.remove_endpoint(self)
        if self.endpoint_id:
            for s in self.subscriptions.copy():
                roboger.events.destroy_subscription(s, dbconn)
            db.query('delete from endpoint where id = %s',
                    (self.endpoint_id, ), True, dbconn)


    def send(self, event):
        return False



class EmailEndpoint(GenericEndpoint):

    rcpt = None

    def __init__(self, addr, rcpt, endpoint_id = None, active = 1,
            description = '', autosave = True):
        self.rcpt = rcpt
        super().__init__(addr, 2, endpoint_id, rcpt, active = active,
                description = description, autosave = autosave)


    def serialize(self):
        d = super().serialize()
        d['rcpt'] = self.rcpt
        return d


    def set_data(self, data = None, data2 = None, data3 = None,
            dbconn = None):
        self.rcpt = data
        super().set_data(data, data2, data3, dbconn)


    def send(self, event):
        if not self.active or event._destroyed: return True
        if not self.rcpt: return False
        t = event.msg if event.msg else ''
        msg = MIMEText(t)
        msg['Subject'] = event.formatted_subject
        msg['From'] = event.sender
        msg['To'] = self.rcpt
        try:
            logging.info('EmailEndpoint sending event to %s' % self.rcpt)
            sm = smtplib.SMTP(roboger.core.smtp_host, roboger.core.smtp_port)
            sm.sendmail(event.sender, self.rcpt, msg.as_string())
            sm.close()
            return True
        except:
            roboger.core.log_traceback()
            return False



class HTTPPostEndpoint(GenericEndpoint):
    
    url = None

    def __init__(self, addr, url, endpoint_id = None, active = 1,
            description = '', autosave = True):
        self.url = url
        super().__init__(addr, 3, endpoint_id, url, active = active,
                description = description, autosave = autosave)


    def serialize(self):
        d = super().serialize()
        d['url'] = self.url
        return d


    def set_data(self, data = None, data2 = None, data3 = None,
            dbconn = None):
        self.url = data
        super().set_data(data, data2, data3, dbconn)


    def send(self, event):
        if not self.url: return False
        data = event.serialize(for_endpoint = True)
        try:
            logging.info('HTTPPostEndpoint sending event to %s' % self.url)
            r = requests.post(self.url,
                    data = data, timeout = roboger.core.timeout)
            if r.status_code != 200:
                logging.info('HTTPPostEndpoint %s return code %s' % \
                        (self.url, r.status_code))
                return False
            return True
        except:
            roboger.core.log_traceback()
            return False


class HTTPJSONEndpoint(GenericEndpoint):
    
    url = None

    def __init__(self, addr, url, endpoint_id = None, active = 1,
            description = '', autosave = True):
        self.url = url
        super().__init__(addr, 4, endpoint_id, url, active = active,
                description = description, autosave = autosave)


    def serialize(self):
        d = super().serialize()
        d['url'] = self.url
        return d


    def set_data(self, data = None, data2 = None, data3 = None,
            dbconn = None):
        self.url = data
        super().set_data(data, data2, data3, dbconn)


    def send(self, event):
        if not self.url: return False
        data = event.serialize(for_endpoint = True)
        try:
            logging.info('HTTPJSONEndpoint sending event to %s' % self.url)
            r = requests.post(self.url,
                    data = data, timeout = roboger.core.timeout)
            if r.status_code != 200:
                logging.info('HTTPJSONEndpoint %s return code %s' % \
                        (self.url, r.status_code))
                return False
            return True
        except:
            roboger.core.log_traceback()
            return False


class SlackEndpoint(GenericEndpoint):

    webhook = None
    rich_fmt = False
    slack_color = {
            10: '#555555',
            20: 'good',
            30: 'warning',
            40: 'danger',
            50: '#FF2222'
            }

    def __init__(self, addr, webhook, fmt = 'plain',
            endpoint_id = None, active = 1, description = '', autosave = True):
        self.webhook = webhook
        self.rich_fmt = (fmt == 'rich')
        super().__init__(addr, 100, endpoint_id, webhook, fmt, active = active,
                description = description, autosave = autosave)


    def serialize(self):
        d = super().serialize()
        d['webhook'] = self.webhook
        d['rich_fmt'] = self.rich_fmt
        return d


    def set_data(self, data = None, data2 = None, data3 = None,
            dbconn = None):
        self.webhook = data
        self.rich_fmt = (data2 == 'rich')
        super().set_data(data, data2, data3, dbconn)


    def send(self, event):
        # return True
        if not self.webhook: return False
        if self.rich_fmt:
            j = { 'text': '' }
            color = self.slack_color.get(event.level_id)
            if not color: color = 'good'
            j['attachments'] = [{
                'fallback': event.formatted_subject,
                'color': color,
                'fields': [{
                    'title': event.formatted_subject,
                    'value': event.msg,
                    'short': event.subject
                    }]
                }]
        else:
            msg = event.formatted_subject + '\n' + event.msg
            j = { 'text': msg }
        if event.sender:
            j['username' ] = event.sender
        try:
            r = requests.post(self.webhook,
                    json = j, timeout = roboger.core.timeout)
            if r.status_code != 200:
                return False
            return True
        except:
            roboger.core.log_traceback()
            return False


class TelegramEndpoint(GenericEndpoint):

    chat_id = None
    _chat_id_plain = None

    def __init__(self, addr, chat_id = None, endpoint_id = None, active = 1,
            description = '', autosave = True):
        super().__init__(addr, 101, endpoint_id, chat_id, active = active,
                description = description, autosave = autosave)
        self._set_chat_id(chat_id)


    def serialize(self):
        d = super().serialize()
        d['chat_id'] = self.chat_id
        if roboger.core.development:
            d['chat_id_plain'] = self._chat_id_plain
        else:
            d['chat_id_plain'] = 'valid' if self._chat_id_plain else None
        return d


    def set_data(self, data = None, data2 = None, data3 = None,
            dbconn = None):
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
                logging.debug('Telegram endpoint %s: invalid chat id' % \
                        self.endpoint_id)
        else:
            self.chat_id = None
            self._chat_id_plain = None


    def send(self, event):
        if self._chat_id_plain:
            msg = '<pre>%s</pre>\n' % event.sender if event.sender else ''
            msg += '<b>' + event.formatted_subject + \
                    '</b>\n'
            msg += event.msg
            return telegram_bot.send_message(
                    self._chat_id_plain, msg, (event.level_id <= 10))
        return False
