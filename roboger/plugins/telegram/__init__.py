__version__ = '1.0.0'
__description__ = 'sends event via Telegram bot'

import tebot.bot

from roboger.core import logger, log_traceback, config as core_config
from roboger.core import get_app, get_timeout, emoji_code
from pyaltt2.crypto import gen_random_str, Rioja
from pyaltt2.config import config_value

from flask import request
from types import SimpleNamespace

from jsonschema import validate

import logging

tebot.bot.logger = logging.getLogger('gunicorn.error')

bot = tebot.bot.TeBot()

_d = SimpleNamespace(ce=None)

PROPERTY_MAP_SCHEMA = {
    'type': 'object',
    'properties': {
        'chat_id': {
            'type': 'string'
        }
    },
    'additionalProperties': False
}

PLUGIN_PROPERTY_MAP_SCHEMA = {
    'type': 'object',
    'properties': {
        'token': {
            'type': 'string',
        }
    },
    'additionalProperties': False,
    'required': ['token']
}


def load(plugin_config, **kwargs):
    token = config_value(config=plugin_config, config_path='/token')
    bot.set_token(token)
    _d.ce = Rioja(token)
    bot.timeout = get_timeout()
    mykey = gen_random_str()
    get_app().add_url_rule(f'/plugin/telegram/{mykey}',
                           'plugin.telegram.webhook',
                           webhook,
                           methods=['POST'])
    url = f'{core_config["url"]}/plugin/telegram/{mykey}'
    logger.debug(f'{__name__} setting web hook to {url}')
    result = bot.set_webhook(url)
    logger.debug(f'{__name__} Telegram API reply {result}')


@bot.route(methods='message')
def handle_message(**kwargs):
    try:
        bot.send('Type /start to obtain chat ID and register your endpoint')
    except:
        log_traceback()


@bot.route(path='/start')
def handle_start(chat_id, **kwargs):
    try:
        bot.send(
            'Hello, I\'m Roboger Telegram Bot ( https://www.roboger.com/ )')
        bot.send(
            'I\'m at your service. Put your chat ID into endpoint parameters '
            'and we will start. Your chat ID is:')
        bot.send(_d.ce.encrypt(str(chat_id)))
    except:
        log_traceback()


def webhook():
    try:
        bot.process_update(request.json)
    except:
        log_traceback()
    return {'ok': True}


def send(config, event_id, msg, sender, formatted_subject, media, level,
         **kwargs):
    if 'chat_id' in config:
        chat_id = _d.ce.decrypt(config['chat_id'])
        if not sender: sender = ''
        text = (f'<pre>{sender}</pre>\n'
                f'<b>{emoji_code.get(level, "")}{formatted_subject}</b>\n{msg}')
        quiet = level <= 10
        if bot.send_message(chat_id,
                            text,
                            disable_web_page_preview=True,
                            disable_notification=quiet):
            if media:
                if not bot.send(text=f'<pre>{sender}</pre>',
                                chat_id=chat_id,
                                media=media,
                                disable_notification=quiet):
                    logger.warning(
                        f'{__name__} {event_id} failed to send media')
        else:
            logger.warning(f'{__name__} {event_id} failed to send')
    else:
        logger.warning(f'{__name__} {event_id} ignored, chat id is not set')


def validate_config(config, **kwargs):
    validate(config, schema=PROPERTY_MAP_SCHEMA)


def validate_plugin_config(plugin_config, **kwargs):
    validate(plugin_config, schema=PLUGIN_PROPERTY_MAP_SCHEMA)
