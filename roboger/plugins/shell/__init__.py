__version__ = '1.0.0'
__description__ = 'launches system command'

import re
import os

from jsonschema import validate

from roboger.core import logger, log_traceback, product, get_timeout

PROPERTY_MAP_SCHEMA = {
    'type': 'object',
    'properties': {
        'command': {
            'type': 'string'
        }
    },
    'additionalProperties': False
}

_template_fields = [
    'event_id', 'addr', 'msg', 'subject', 'formatted_subject', 'level',
    'level_name', 'location', 'tag', 'sender', 'media'
]


def send(config, **kwargs):
    if 'command' in config:
        cmd = config['command'].replace('\n', '').replace('\r', '')
        for p in _template_fields:
            v = kwargs.get('media_encoded' if p == 'media' else p)
            if v is None: v = ''
            cmd = re.sub(fr'\${p}([^_])', fr'{v}\1', cmd)
        logger.debug(f'{__name__} executing ( {cmd} )')
        os.system(f'( {cmd} ) &')


def validate_config(config, **kwargs):
    validate(config, schema=PROPERTY_MAP_SCHEMA)


def validate_plugin_config(plugin_config, **kwargs):
    if plugin_config:
        raise ValueError('this plugin should have no configuration options')
