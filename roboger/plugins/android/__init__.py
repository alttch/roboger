__version__ = '1.0.0'
__description__ = 'official Roboger app plugin, don\'t use'

import filetype

from types import SimpleNamespace
from pyfcm import FCMNotification
from jsonschema import validate

from roboger.core import logger, log_traceback, bucket_put
from pyaltt2.config import config_value

_cfg = SimpleNamespace(api_key=None)

PROPERTY_MAP_SCHEMA = {
    'type': 'object',
    'properties': {
        'registration_id': {
            'type': 'string',
        },
        'device_id': {
            'type': 'string',
        }
    },
    'additionalProperties': False
}

PLUGIN_PROPERTY_MAP_SCHEMA = {
    'type': 'object',
    'properties': {
        'api-key': {
            'type': 'string',
        }
    },
    'additionalProperties': False,
    'required': ['api-key']
}


def load(plugin_config, **kwargs):
    api_key = config_value(config=plugin_config, config_path='/api-key')
    _cfg.push_service = FCMNotification(api_key=api_key)


def send(config, event_id, addr_id, msg, subject, formatted_subject, sender,
         location, media, media_fname, level, **kwargs):
    if config.get('registration_id'):
        data = {
            'location': location,
            'sender': sender if sender else 'roboger',
            'level': level,
            'subject': subject,
            'id': event_id,
            'msg': msg
        }
        if media:
            ft = filetype.guess(media)
            object_id = bucket_put(content=media,
                                   creator='plugin.android',
                                   addr_id=addr_id,
                                   public=True,
                                   fname=media_fname if media_fname else None)
            data['media'] = {
                'type': (ft.extension if ft else 'Unknown'),
                'data': object_id
            }
        _cfg.push_service.single_device_data_message(
            registration_id=config['registration_id'], data_message=data)
    else:
        logger.info(f'{__name__} {event_id} ignored, device not active')


def validate_config(config, **kwargs):
    validate(config, schema=PROPERTY_MAP_SCHEMA)


def validate_plugin_config(plugin_config, **kwargs):
    validate(plugin_config, schema=PLUGIN_PROPERTY_MAP_SCHEMA)
