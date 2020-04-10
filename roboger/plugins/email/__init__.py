__version__ = '1.1.0'
__description__ = 'sends event by email'

import smtplib
import filetype
import platform

from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart

from types import SimpleNamespace
from pyaltt2.network import parse_host_port
from pyaltt2.mail import SMTP

from roboger.core import logger, log_traceback
from pyaltt2.config import config_value

from jsonschema import validate

_d = SimpleNamespace(smtp=None, default_location=platform.node())

PROPERTY_MAP_SCHEMA = {
    'type': 'object',
    'properties': {
        'rcpt': {
            'type': 'string',
            'format': 'email'
        },
    },
    'additionalProperties': False
}

PLUGIN_PROPERTY_MAP_SCHEMA = {
    'type': 'object',
    'properties': {
        'smtp': {
            'type': 'object',
            'properties': {
                'host': {
                    'type': 'string',
                },
                'port': {
                    'type': 'integer',
                    'minimum': 1
                },
                'tls': {
                    'type': 'boolean',
                },
                'ssl': {
                    'type': 'boolean',
                },
                'login': {
                    'type': 'string',
                },
                'password': {
                    'type': 'string',
                },
            },
            'required': ['host']
        },
        'default-location': {
            'type': 'string',
        }
    },
    'additionalProperties': False,
}


def load(plugin_config, **kwargs):
    if 'smtp' in plugin_config:
        _d.default_location = plugin_config.get('default-location')
        smtp_config = plugin_config['smtp']
        config_value(config=smtp_config, config_path='/password', default=None, in_place=True)
        _d.smtp = SMTP(**smtp_config)
        logger.debug(
            f'{__name__} loaded, SMTP server: {_d.smtp.host}:{_d.smtp.port}, '
            f'ssl: {_d.smtp.ssl}, tls: {_d.smtp.tls}, '
            f'auth: {_d.smtp.login is not None}')
    else:
        logger.error(f'{__name__} not active, no SMTP server provided')


def send(config, event_id, msg, formatted_subject, sender, location, media,
         media_fname, **kwargs):
    if _d.smtp:
        rcpt = config.get('rcpt')
        if rcpt:
            logger.debug(f'{__name__} {event_id} sending message to {rcpt}')
            if not sender:
                sender = 'roboger'
            if '@' not in sender:
                sender += '@{}'.format(
                    location if location else _d.default_location)
            m = MIMEMultipart() if media else MIMEText(
                msg if msg is not None else '')
            m['Subject'] = formatted_subject
            m['From'] = sender
            m['To'] = rcpt
            if media:
                m.attach(MIMEText(msg if msg is not None else ''))
                if not media_fname:
                    ft = filetype.guess(media)
                    media_fname = 'attachment.txt' if ft is None else \
                            f'attachment.{ft.extension}'
                a = MIMEApplication(media, Name=media_fname)
                a['Content-Disposition'] = (f'attachment; '
                                            f'filename="{media_fname}"')
                m.attach(a)
            _d.smtp.send(sender, rcpt, m.as_string())
        else:
            logger.debug(f'{__name__} {event_id} failed to'
                         f' send message from {sender} to {rcpt}')
    else:
        logger.error(f'{__name__} {event_id} ignored, not active')


def validate_config(config, **kwargs):
    validate(config, schema=PROPERTY_MAP_SCHEMA)


def validate_plugin_config(plugin_config, **kwargs):
    validate(plugin_config, schema=PLUGIN_PROPERTY_MAP_SCHEMA)
