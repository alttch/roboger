import requests
import json
import time
import roboger.core
import logging

import base64
import hashlib

from cryptography.fernet import Fernet
from pyaltt import background_worker


@background_worker(on_error=roboger.core.log_traceback)
def telegram_bot(o, **kwargs):
    if not o._token:
        raise Exception('token not provided')
    result = o.call('getUpdates', {'offset': o.update_offset + 1})
    if result and 'result' in result:
        for m in result['result']:
            if m.get('message'): o.process_update(msg)
            update_id = m.get('update_id')
            if update_id and update_id > o.update_offset:
                o.update_offset = update_id


class RTelegramBot():

    def __init__(self):
        self._token = None
        self.ce = None
        self.__uri = None
        self.timeout = 10
        self.poll_interval = 2
        self.update_offset = 0

    def start(self):
        telegram_bot.start(o=self, _interval=self.poll_interval)

    def stop(self):
        telegram_bot.stop()

    def set_token(self, token=None):
        if token:
            self.__uri = 'https://api.telegram.org/bot%s' % token
            _k = base64.b64encode(hashlib.sha256(token.encode()).digest())
            self.ce = Fernet(_k)
            self._token = token
        else:
            self.ce = None
            self._token = None

    def is_ready(self):
        return self._token is not None

    def test(self):
        result = self.call('getMe')
        return result is not None

    def call(self, func, args=None, files=None, retry=True):
        logging.debug('Telegram API call %s' % func)
        try:
            if files:
                r = requests.post(
                    '%s/%s' % (self.__uri, func),
                    data=args,
                    files=files,
                    timeout=self.timeout)
            else:
                r = requests.post(
                    '%s/%s' % (self.__uri, func),
                    json=args,
                    timeout=self.timeout)
            if r.status_code == 200:
                result = r.json()
                if result.get('ok'): return result
            if not retry: return None
            time.sleep(self.poll_interval)
            return self.call(func=func, args=args, files=files, retry=False)
        except:
            roboger.core.log_traceback()
            return None

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
            self.send_message(
                chat_id, 'Hello, I\'m Roboger Telegram Bot' +
                ' ( https://www.roboger.com/ )')
            self.send_message(
                chat_id, 'I\'m at your service. Put your chat ID ' +
                'into endpoint parameters and we will start. ' +
                'Your chat ID is:')
            chat_id_e = self.ce.encrypt(str(chat_id).encode())
            self.send_message(chat_id, '<b>%s</b>' % chat_id_e.decode())
        else:
            self.send_message(
                chat_id,
                'Type /start to obtain chat ID and register your endpoint')
