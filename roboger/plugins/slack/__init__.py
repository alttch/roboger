__version__ = '1.0.0'
__description__ = 'sends event to Slack'

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
        'rich': {
            'type': 'boolean'
        }
    },
    'additionalProperties': False
}

slack_color = {
    10: '#555555',
    20: 'good',
    30: 'warning',
    40: 'danger',
    50: '#FF2222'
}


def send(config, event_id, level, formatted_subject, subject, msg, sender,
         **kwargs):
    url = config['url']
    logger.debug(f'{__name__} {event_id} sending Slack webhook to {url}')
    if config.get('rich'):
        data = {'text': ''}
        color = slack_color.get(level, 'good')
        data['attachments'] = [{
            'fallback':
                formatted_subject,
            'color':
                color,
            'fields': [{
                'title': formatted_subject,
                'value': msg,
                'short': subject
            }]
        }]
    else:
        data = {'text': f'{formatted_subject}\n{msg}'}
    if sender:
        data['username'] = sender
    r = requests.post(url,
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
