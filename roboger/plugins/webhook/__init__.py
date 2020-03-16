import requests
import re

from jsonschema import validate
try:
    import rapidjson as json
except:
    import json

from roboger.core import logger, log_traceback, product, get_timeout

PROPERTY_MAP_SCHEMA = {
    'type': 'object',
    'properties': {
        'url': {
            'type': 'string',
            'format': 'uri'
        },
        'template': {
            'type': 'string'
        }
    },
    'additionalProperties': False
}

_template_fields = [
    'event_id', 'msg', 'subject', 'formatted_subject', 'level', 'level_name',
    'location', 'tag', 'sender', 'media'
]


def send(config, **kwargs):
    if config.get('template'):
        data = config['template'].replace('\n', '').replace('\r', '')
        for p in _template_fields:
            v = kwargs.get('media_encoded' if p == 'media' else p)
            if p != 'level':
                v = 'null' if v is None else f'"{v}"'
            data = re.sub(fr'\${p}([^_])', fr'{v}\1', data)
    else:
        data = "null"
    url = config['url']
    logger.debug(f'{__name__} {kwargs["event_id"]} sending JSON POST to {url}')
    r = requests.post(url,
                      headers={
                          'Content-Type': 'application/json',
                          'Content-Length': str(len(data)),
                          'User-Agent': product.user_agent
                      },
                      data=data,
                      timeout=get_timeout())
    if not r.ok:
        raise RuntimeError(f'{__name__} server {url} status {r.status_code}')


def validate_config(config, **kwargs):
    validate(config, schema=PROPERTY_MAP_SCHEMA)
    tpl = config.get('template')
    if tpl is not None:
        tpl = tpl.replace('\n', '').replace('\r', '')
        for p in _template_fields:
            val = 0 if p == 'level' else '""'
            tpl = re.sub(fr'\${p}([^_])', fr'{val}\1', tpl)
        json.loads(tpl)
