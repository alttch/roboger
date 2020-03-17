__version__ = '1.0.0'
__description__ = 'forwards event to another Roboger server'

import requests

from jsonschema import validate

from roboger.core import logger, log_traceback, product, get_timeout

PROPERTY_MAP_SCHEMA = {
    'type': 'object',
    'properties': {
        'url': {
            'type': 'string',
            'format': 'uri'
        },
        'addr': {
            'type': 'string'
        }
    },
    'additionalProperties': False
}

_copy_fields = ['msg', 'subject', 'level', 'location', 'tag', 'sender']


def send(config, **kwargs):
    url = config['url']
    addr = config['addr']
    if url.endswith('/'):
        url = url[:-1]
    data = {k: kwargs.get(k) for k in _copy_fields}
    data['media'] = kwargs.get('media_encoded')
    data['addr'] = addr
    logger.debug(f'{__name__} {kwargs["event_id"]} '
                 f'sending Roboger chain event to {url} {addr}')
    r = requests.post(f'{url}/push',
                      headers={'User-Agent': product.user_agent},
                      json=data,
                      timeout=get_timeout())
    if not r.ok:
        raise RuntimeError(f'{__name__} server {url} status {r.status_code}')


def validate_config(config, **kwargs):
    validate(config, schema=PROPERTY_MAP_SCHEMA)


def validate_plugin_config(plugin_config, **kwargs):
    if plugin_config:
        raise ValueError('this plugin should have no configuration options')
