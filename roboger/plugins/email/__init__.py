__version__ = '1.0.0'
__description__ = 'sends event by email'

import smtplib
import filetype
import platform

from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart

from types import SimpleNamespace
from pyaltt2.network import parse_host_port

from roboger.core import logger, log_traceback

from jsonschema import validate

_cfg = SimpleNamespace(host=None, port=25)

hostname = platform.node()

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
        'smtp-server': {
            'type': 'string',
        },
        'default-location': {
            'type': 'string',
        }
    },
    'additionalProperties': False,
    'required': ['smtp-server']
}


def load(plugin_config, **kwargs):
    smtp = plugin_config.get('smtp-server')
    if smtp:
        _cfg.host, _cfg.port = parse_host_port(smtp, 25)
        logger.debug(f'{__name__} loaded, SMTP server: {_cfg.host}:{_cfg.port}')
    else:
        logger.error(f'{__name__} not active, no SMTP server provided')
    _cfg.default_location = plugin_config.get('default-location')


def send(config, event_id, msg, formatted_subject, sender, location, media,
         media_fname, **kwargs):
    if _cfg.host:
        rcpt = config.get('rcpt')
        if rcpt:
            logger.debug(f'{__name__} {event_id} sending message to {rcpt}')
            if not sender:
                sender = 'roboger'
            if '@' not in sender:
                sender += '@{}'.format(location if location else (
                    _cfg.default_location if _cfg.default_location else hostname
                ))
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
            sm = smtplib.SMTP(_cfg.host, _cfg.port)
            sm.sendmail(sender, rcpt, m.as_string())
            sm.close()
        else:
            logger.debug(f'{__name__} {event_id} failed to'
                         f' send message from {sender} to {rcpt}')
    else:
        logger.error(f'{__name__} {event_id} ignored, not active')


def validate_config(config, **kwargs):
    validate(config, schema=PROPERTY_MAP_SCHEMA)


def validate_plugin_config(plugin_config, **kwargs):
    validate(plugin_config, schema=PLUGIN_PROPERTY_MAP_SCHEMA)
