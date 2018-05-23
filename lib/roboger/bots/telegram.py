import requests
import jsonpickle
import threading
import time
import roboger.core
import logging

from cryptography.fernet import Fernet
import base64
import hashlib


class RTelegramBot(object):

    def __init__(self, token):
        self.token = token
        self.uri = 'https://api.telegram.org/bot%s' % self.token
        self.timeout = 5
        self.poll_interval = 2
        self.update_offset = 0
        self.update_thread = None
        self.update_thread_active = True
        self.ce = None
        if self.token:
            _k = base64.b64encode(hashlib.sha256(token.encode()).digest())
            self.ce = Fernet(_k)

    def test(self):
        result = self.call('getMe')
        return result is not None

    def call(self, func, args=None, files=None, retry=True):
        logging.debug('Telegram API call %s' % func)
        try:
            if files:
                r = requests.post(
                    '%s/%s' % (self.uri, func),
                    data=args,
                    files=files,
                    timeout=self.timeout)
            else:
                r = requests.post(
                    '%s/%s' % (self.uri, func), json=args, timeout=self.timeout)
            if r.status_code == 200:
                result = jsonpickle.decode(r.text)
                if result.get('ok'): return result
            if not retry: return None
            time.sleep(self.poll_interval)
            return self.call(func=func, args=args, files=files, retry=False)
        except:
            roboger.core.log_traceback()
            return None

    def start(self):
        self.update_thread = threading.Thread(
            name='RTelegramBot_t_get_updates', target=self._t_get_updates)
        self.update_thread.start()

    def stop(self):
        if self.update_thread_active and \
                self.update_thread and \
                self.update_thread.isAlive():
            self.update_thread_active = False
            self.update_thread.join()

    def _t_get_updates(self):
        logging.debug('update thread started')
        self.update_thread_active = True
        while self.update_thread_active:
            result = self.call('getUpdates', {'offset': self.update_offset + 1})
            if result and 'result' in result:
                for m in result['result']:
                    msg = m.get('message')
                    if msg: self.process_update(msg)
                    update_id = m.get('update_id')
                    if update_id and update_id > self.update_offset:
                        self.update_offset = update_id
            time.sleep(self.poll_interval)

    def send_message(self, chat_id, msg, quiet=False):
        return self.call(
            'sendMessage', {
                'chat_id': chat_id,
                'text': msg,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True,
                'disable_notification': quiet
            }) is not None

    def send_document(self, chat_id, caption, media, quiet=False):
        return self.call(
            'sendDocument', {
                'chat_id': chat_id,
                'caption': caption,
                'parse_mode': 'HTML',
                'disable_notification': quiet
            }, {'document': media}) is not None

    def send_photo(self, chat_id, caption, media, quiet=False):
        return self.call(
            'sendPhoto', {
                'chat_id': chat_id,
                'caption': caption,
                'parse_mode': 'HTML',
                'disable_notification': quiet
            }, {'photo': media}) is not None

    def send_audio(self, chat_id, caption, media, quiet=False):
        return self.call(
            'sendAudio', {
                'chat_id': chat_id,
                'caption': caption,
                'parse_mode': 'HTML',
                'disable_notification': quiet
            }, {'audio': media}) is not None

    def send_video(self, chat_id, caption, media, quiet=False):
        return self.call(
            'sendVideo', {
                'chat_id': chat_id,
                'caption': caption,
                'parse_mode': 'HTML',
                'disable_notification': quiet
            }, {'video': media}) is not None

    def process_update(self, msg):
        chat = msg.get('chat')
        if not chat: return
        chat_id = chat.get('id')
        if not chat_id: return
        text = msg.get('text')
        if not text: return
        text = text.split('@')[0]
        if text == '/start':
            self.send_message(chat_id, 'Hello, I\'m Roboger Telegram Bot' + \
                    ' ( https://www.roboger.com/ )')
            self.send_message(chat_id,
                    'I\'m at your service. Put your chat ID ' +
                    'into endpoint parameters and we will start. ' + \
                            'Your chat ID is:')
            chat_id_e = self.ce.encrypt(str(chat_id).encode())
            self.send_message(chat_id, '<b>%s</b>' % chat_id_e.decode())
        else:
            self.send_message(
                chat_id,
                'Type /start to obtain chat ID and register your endpoint')
