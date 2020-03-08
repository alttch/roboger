import requests

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
    'additionalProperties': False,
    'required': ['url']
}


def send(config, **kwargs):
    if config.get('template'):
        data = config['template']
        for p in [
                'event_id', 'msg', 'subject', 'formatted_subject', 'level',
                'location', 'tag', 'sender'
        ]:
            data = data.replace(f'${p}', str(kwargs.get(p, 'null')))
        data = data.replace('$media', str(kwargs.get('media_encoded', 'null')))
    else:
        data = "null"
    url = config['url']
    logger.debug(f'{__name__} {kwargs["event_id"]} sending JSON POST to {url}')
    r = requests.post(url,
                      headers={
                          'Content-Type':
                              'application/json',
                          'Content-Length':
                              str(len(data)),
                          'User-Agent':
                              'Roboger/{} (v{} build {})'.format(
                                  product.version[:product.version.rfind('.')],
                                  product.version, product.build)
                      },
                      data=data,
                      timeout=get_timeout())
    if not r.ok:
        raise RuntimeError(f'{__name__} server {url} status {r.status_code}')


def validate_config(config):
    validate(config, schema=PROPERTY_MAP_SCHEMA)
    if config.get('template'):
        json.loads(config['template'])
