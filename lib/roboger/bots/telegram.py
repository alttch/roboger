import requests
import jsonpickle
import threading
import time
import roboger.core
import logging


class RTelegramBot(object):

    token = None
    uri = ''
    timeout = 5
    poll_interval = 2
    update_offset = 0
    update_thread = None
    update_thread_active = True
    

    def __init__(self, token):
        self.token = token
        self.uri = 'https://api.telegram.org/bot%s' % self.token


    def test(self):
        result = self.call('getMe')
        return result is not None


    def call(self, func, args = None):
        try:
            r = requests.post('%s/%s' % (self.uri, func), json = args,
                    timeout = self.timeout)
            if r.status_code != 200: return None
            result = jsonpickle.decode(r.text)
            return result if result.get('ok') else None
        except:
            roboger.core.log_traceback()
            return None


    def start(self):
        self.update_thread = threading.Thread(
                name = 'RTelegramBot_t_get_updates',
                target = self._t_get_updates)
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
            result = self.call('getUpdates',
                    { 'offset': self.update_offset + 1 })
            if result and 'result' in result:
                for m in result['result']:
                    msg = m.get('message')
                    if msg: self.process_update(msg)
                    update_id = m.get('update_id')
                    if update_id and update_id > self.update_offset:
                        self.update_offset = update_id
            time.sleep(self.poll_interval)


    def send_message(self, chat_id, msg, quiet = False):
        return self.call('sendMessage',
                {
                    'chat_id': chat_id,
                    'text': msg,
                    'parse_mode': 'HTML',
                    'disable_web_page_preview': True,
                    'disable_notification': quiet
                }) is not None


    def process_update(self, msg):
        chat = msg.get('chat')
        if not chat: return
        chat_id = chat.get('id')
        if not chat_id: return
        text = msg.get('text')
        if text == '/start':
            self.send_message(chat_id, 'Hello, I\'m Roboger Telegram Bot' + \
                    ' ( https://www.roboger.com/ )')
            self.send_message(chat_id,
                    'I\'m at your service. Put your chat ID' + 
                    'into endpoint parameters and we will start. ' + \
                            'Your chat ID is:')
            self.send_message(chat_id, '<b>%u</b>' % chat_id)
            if chat_id < 0:
                self.send_message(chat_id, 'Warning: your chat ID starts' + \
                        ' with a minus sign (-), don\'t forget to copy it too')
        else:
            self.send_message(chat_id,
                'Type /start to obtain chat ID and register your endpoint')

