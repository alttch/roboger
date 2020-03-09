__author__ = 'Altertech, http://www.altertech.com/'
__copyright__ = 'Copyright (C) 2018-2020 Altertech Group'
__license__ = 'Apache License 2.0'
__version__ = '1.5.0'

from flask import request, jsonify, Response, abort

import base64
import uuid
import logging
from functools import wraps

from sqlalchemy import text as sql

from .core import logger, convert_level, log_traceback, config as core_config
from .core import get_app, get_db, send, product, is_secure_mode

from .core import addr_get, addr_list, addr_create, addr_delete
from .core import addr_set_active, addr_change

from .core import endpoint_get, endpoint_list, endpoint_create
from .core import endpoint_update, endpoint_delete

from functools import wraps

from pyaltt2.network import netacl_match

success = {'ok': True}


def arr_from_str(s):
    if not isinstance(s, str) or s.find('|') == -1: return s
    result = []
    vals = s.split('|')
    for v in vals:
        try:
            _v = float(v)
            if _v == int(_v): _v = int(_v)
        except:
            _v = v
        result.append(_v)
    return result


# throws exception
def dict_from_str(s, spl=','):
    if not isinstance(s, str): return s
    result = {}
    if not s: return result
    vals = s.split(spl)
    for v in vals:
        name, value = v.split('=')
        if value.find('||') != -1:
            _value = value.split('||')
            value = []
            for _v in _value:
                if _v.find('|') != -1:
                    value.append(arr_from_str(_v))
                else:
                    value.append([_v])
        else:
            value = arr_from_str(value)
        if isinstance(value, str):
            try:
                value = float(value)
                if value == int(value): value = int(value)
            except:
                pass
        result[name] = value
    return result


def _response_new_location(payload, code, new_id, resource):
    r = jsonify(payload) if payload else Response()
    r.status_code = code
    r.headers['Location'] = f'{api_uri_rest}/{resource}/{new_id}'
    r.autocorrect_location_header = False
    return r


def _response_created(payload, id, resource):
    return _response_new_location(payload, 201, id, resource)


def _response_moved(payload, id, resource):
    return _response_new_location(payload, 301, id, resource)


def _response_empty():
    return Response(status=204)


def _response_accepted():
    return Response(status=202)


def http_real_ip():
    return request.remote_addr


def public_method(f):

    @wraps(f)
    def do(*args):
        return f(*args, **(request.json if request.json else {}))

    return do


def admin_method(f):

    @wraps(f)
    def do(*args, **kwargs):
        ip = http_real_ip()
        payload = request.json if request.json else {}
        key = request.headers.get('X-Auth-Key', payload.get('k'))
        if key is None:
            logger.warning(
                f'API unauthorized access to admin functions from {ip}:'
                ' no key provided')
            abort(401)
        if key != core_config['master']['key']:
            logger.warning(
                f'API unauthorized access to admin functions from {ip}:'
                ' invalid key provided')
            abort(403)
        if core_config['_acl'] and not netacl_match(ip, core_config['_acl']):
            logger.warning(
                f'API unauthorized access to admin functions from {ip}:'
                ' ACL doesn\'t match')
            abort(403)
        return f(*args, **{**kwargs, **payload})

    return do


@public_method
def ping(**kwargs):
    get_db()
    return _response_empty()


@public_method
def push(**kwargs):
    try:
        event_id = str(uuid.uuid4())
        addr = kwargs.get('addr')
        logger.info(f'API message to {addr}')
        msg = kwargs.get('msg', '')
        subject = kwargs.get('subject', '')
        level = convert_level(kwargs.get('level'))
        location = kwargs.get('location')
        if location == '': location = None
        tag = kwargs.get('tag')
        if tag == '': tag = None
        sender = kwargs.get('sender')
        if sender == '': sender = None
        media_encoded = kwargs.get('media')
        if media_encoded == '': media_encoded = None
        if media_encoded:
            try:
                media = base64.b64decode(media_encoded)
            except:
                media = None
                media_encoded = None
                logger.warning(
                    f'API invalid media file in {event_id} message to {addr}')
        else:
            media = None
        formatted_subject = ''
        level_name = logging.getLevelName(level)
        formatted_subject = level_name
        if location:
            formatted_subject += f' @{location}'
        elif location:
            formatted_subject = location
        if subject: formatted_subject += f': {subject}'
        for row in get_db().execute(sql("""
            SELECT plugin_name, config
            FROM subscription join endpoint ON
                endpoint.id = subscription.endpoint_id
            WHERE addr_id IN (SELECT id FROM addr WHERE a=:addr and active=1)
                AND subscription.active = 1
                AND endpoint.active = 1
                AND (location=:location or location IS null)
                AND (tag=:tag or tag IS null)
                AND (sender=:sender or sender IS null)
                AND (
                    (level_id=:level AND level_match='e') OR
                    (level_id<:level and level_match='g') OR
                    (level_id<=:level and level_match='ge') OR
                    (level_id>:level and level_match='l') OR
                    (level_id>=:level and level_match='le')
                    )
                    """),
                                    addr=addr,
                                    location=location,
                                    tag=tag,
                                    sender=sender,
                                    level=level):
            send(row.plugin_name,
                 config=row.config,
                 event_id=event_id,
                 msg=msg,
                 subject=subject,
                 formatted_subject=formatted_subject,
                 level=level_name,
                 level_id=level,
                 location=location,
                 tag=tag,
                 sender=sender,
                 media=media,
                 media_encoded=media_encoded)
        return _response_accepted()
    except:
        log_traceback()
        abort(503)


api_uri = '/manage'

api_uri_rest = f'{api_uri}/v2'


def init():
    app = get_app()
    app.add_url_rule('/ping', 'ping', ping, methods=['GET'])
    app.add_url_rule('/push', 'push', push, methods=['POST'])
    # v2 (RESTful)
    app.add_url_rule(f'{api_uri_rest}/core', 'test', test, methods=['GET'])
    app.add_url_rule(f'{api_uri_rest}/addr',
                     'addr.list',
                     r_addr_list,
                     methods=['GET'])
    app.add_url_rule(f'{api_uri_rest}/addr/<a>',
                     'addr.post',
                     r_addr_cmd,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri_rest}/addr/<a>',
                     'addr.get',
                     r_addr_get,
                     methods=['GET'])
    app.add_url_rule(f'{api_uri_rest}/addr',
                     'addr.create',
                     r_addr_create,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri_rest}/addr/<a>',
                     'addr.modify',
                     r_addr_modify,
                     methods=['PATCH'])
    app.add_url_rule(f'{api_uri_rest}/addr/<a>',
                     'addr.delete',
                     r_addr_delete,
                     methods=['DELETE'])
    app.add_url_rule(f'{api_uri_rest}/addr/<a>/endpoint',
                     'endpoint.list',
                     r_endpoint_list,
                     methods=['GET'])
    app.add_url_rule(f'{api_uri_rest}/addr/<a>/endpoint/<ep>',
                     'endpoint.post',
                     r_endpoint_cmd,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri_rest}/addr/<a>/endpoint/<ep>',
                     'endpoint.get',
                     r_endpoint_get,
                     methods=['GET'])
    app.add_url_rule(f'{api_uri_rest}/addr/<a>/endpoint',
                     'endpoint.create',
                     r_endpoint_create,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri_rest}/addr/<a>/endpoint/<ep>',
                     'endpoint.modify',
                     r_endpoint_modify,
                     methods=['PATCH'])
    app.add_url_rule(f'{api_uri_rest}/addr/<a>/endpoint/<ep>',
                     'endpoint.delete',
                     r_endpoint_delete,
                     methods=['DELETE'])
    # legacy
    app.add_url_rule(f'{api_uri}/test', 'test', test, methods=['GET', 'POST'])
    app.add_url_rule(f'{api_uri}/addr_list',
                     'm_addr_list',
                     m_addr_list,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/addr_create',
                     'm_addr_create',
                     m_addr_create,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/addr_change',
                     'm_addr_change',
                     m_addr_change,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/addr_set_active',
                     'm_addr_set_active',
                     m_addr_set_active,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/addr_enable',
                     'm_addr_enable',
                     m_addr_enable,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/addr_disable',
                     'm_addr_disable',
                     m_addr_disable,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/addr_delete',
                     'm_addr_delete',
                     m_addr_delete,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/endpoint_types',
                     'm_endpoint_types',
                     m_endpoint_types,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/endpoint_list',
                     'm_endpoint_list',
                     m_endpoint_list,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/endpoint_create',
                     'm_endpoint_create',
                     m_endpoint_create,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/endpoint_data',
                     'm_endpoint_data',
                     m_endpoint_data,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/endpoint_config',
                     'm_endpoint_config',
                     m_endpoint_config,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/endpoint_skipdups',
                     'm_endpoint_skipdups',
                     m_endpoint_skipdups,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/endpoint_description',
                     'm_endpoint_description',
                     m_endpoint_description,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/endpoint_enable',
                     'm_endpoint_enable',
                     m_endpoint_enable,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/endpoint_disable',
                     'm_endpoint_disable',
                     m_endpoint_disable,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/endpoint_set_active',
                     'm_endpoint_set_active',
                     m_endpoint_set_active,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/endpoint_delete',
                     'm_endpoint_delete',
                     m_endpoint_delete,
                     methods=['POST'])


def _accept_resource(resource):
    accept_list = [
        h.split(';', 1)[0].strip()
        for h in request.headers.get('Accept', '').split(',')
    ]
    return '*/*' in accept_list or 'application/*' in accept_list or \
            f'application/{resource}+json' in accept_list


def _process_addr(a):
    try:
        return (int(a), None)
        addr_id = int(a)
        addr = None
    except:
        return (None, a if isinstance(a, str) else None)


@admin_method
def r_addr_list():
    return jsonify(addr_list())


@admin_method
def r_addr_get(a):
    addr_id, addr = _process_addr(a)
    try:
        return jsonify(addr_get(addr_id=addr_id, addr=addr))
    except LookupError:
        abort(404)


@admin_method
def r_addr_cmd(a, cmd):
    addr_id, addr = _process_addr(a)
    if cmd == 'change':
        new_addr = addr_change(addr_id=addr_id, addr=addr)
        return _response_moved(None, new_addr, 'addr')
    else:
        abort(404)


@admin_method
def r_addr_create():
    result = addr_get(addr_create())
    return _response_created(
        result if _accept_resource('roboger.addr') else None, result['a'],
        'addr')


@admin_method
def r_addr_modify(a, active=None):
    if active is not None:
        addr_id, addr = _process_addr(a)
        addr_set_active(addr_id=addr_id, addr=addr, active=int(active))
    return jsonify(addr_get(
        addr_id=addr_id,
        addr=addr)) if _accept_resource('roboger.addr') else _response_empty()


@admin_method
def r_addr_delete(a):
    addr_id, addr = _process_addr(a)
    try:
        addr_delete(addr_id=addr_id, addr=addr)
        return _response_empty()
    except LookupError:
        abort(404)


@admin_method
def r_endpoint_list(a):
    addr_id, addr = _process_addr(a)
    try:
        addr = addr_get(addr_id=addr_id, addr=addr)
    except LookupError:
        abort(404)
    return jsonify(endpoint_list(addr_id=addr['id']))


def _get_endpoint_verify_addr(ep, a):
    addr_id, addr = _process_addr(a)
    endpoint = endpoint_get(ep)
    addr = addr_get(addr_id=addr_id, addr=addr)
    if endpoint['addr_id'] == addr['id']:
        return endpoint
    else:
        raise LookupError


@admin_method
def r_endpoint_get(a, ep):
    try:
        endpoint = _get_endpoint_verify_addr(ep, a)
        return jsonify(endpoint)
    except LookupError:
        abort(404)


@admin_method
def r_endpoint_cmd(a, ep, cmd):
    try:
        endpoint = _get_endpoint_verify_addr(ep, a)
        abort(405)
    except LookupError:
        abort(404)


@admin_method
def r_endpoint_create(a, plugin_name, **kwargs):
    addr_id, addr = _process_addr(a)
    try:
        result = endpoint_get(
            endpoint_create(plugin_name,
                            addr_id=addr_id,
                            addr=addr,
                            validate_config=True,
                            **kwargs))
    except LookupError:
        abort(404)
    except ValueError as e:
        return Response(str(e), status=400)
    return _response_created(
        result if _accept_resource('roboger.endpoint') else None, result['id'],
        f'addr/{a}/endpoint')


@admin_method
def r_endpoint_modify(a, ep, **kwargs):
    try:
        endpoint = _get_endpoint_verify_addr(ep, a)
    except LookupError:
        abort(404)
    if kwargs:
        for field in ['id', 'addr_id', 'plugin_name']:
            if field in kwargs:
                return Response(f'Field "{field}" is protected', status=405)
        try:
            endpoint_update(ep,
                            kwargs,
                            validate_config=True,
                            plugin_name=endpoint['plugin_name'])
        except ValueError as e:
            return Response(str(e), status=400)
    return jsonify(endpoint_get(ep)) if _accept_resource(
        'roboger.endpoint') else _response_empty()


@admin_method
def r_endpoint_delete(a, ep):
    try:
        endpoint = _get_endpoint_verify_addr(ep, a)
        endpoint_delete(endpoint_id=ep)
        return _response_empty()
    except LookupError:
        abort(404)


# LEGACY

_legacy_endpoint_types = {
    1: 'android',
    2: 'email',
    4: 'webhook',
    100: 'slack',
    101: 'telegram'
}

_legacy_endpoint_ids = {v: k for k, v in _legacy_endpoint_types.items()}


@admin_method
def test(**kwargs):
    result = success.copy()
    result.update({'version': product.version, 'build': product.build})
    return jsonify(result)


@admin_method
def m_addr_list(addr_id=None, addr=None, **kwargs):
    logger.warning('API DEPRECATED addr_list')
    if addr_id or addr:
        try:
            return addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
    else:
        return jsonify(addr_list())


@admin_method
def m_addr_create(**kwargs):
    logger.warning('API DEPRECATED addr_create')
    return jsonify(addr_get(addr_create()))


@admin_method
def m_addr_change(addr_id=None, addr=None, **kwargs):
    logger.warning('API DEPRECATED addr_change')
    try:
        new_addr = addr_change(addr_id=addr_id, addr=addr)
        return jsonify(addr_get(addr=new_addr))
    except LookupError:
        abort(404)


@admin_method
def m_addr_set_active(addr_id=None, addr=None, active=1, **kwargs):
    logger.warning('API DEPRECATED addr_set_active')
    try:
        return jsonify(
            addr_set_active(addr_id=addr_id, addr=addr, active=int(active)))
    except LookupError:
        abort(404)


@admin_method
def m_addr_enable(addr_id=None, addr=None, active=1, **kwargs):
    logger.warning('API DEPRECATED addr_enable')
    try:
        return jsonify(addr_set_active(addr_id=addr_id, addr=addr, active=1))
    except LookupError:
        abort(404)


@admin_method
def m_addr_disable(addr_id=None, addr=None, active=1, **kwargs):
    logger.warning('API DEPRECATED addr_disable')
    try:
        return jsonify(addr_set_active(addr_id=addr_id, addr=addr, active=0))
    except LookupError:
        abort(404)


@admin_method
def m_addr_delete(addr_id=None, addr=None, **kwargs):
    logger.warning('API DEPRECATED addr_delete')
    try:
        addr_delete(addr_id=addr_id, addr=addr)
        return jsonify(success)
    except LookupError:
        abort(404)


@admin_method
def m_endpoint_types(**kwargs):
    return jsonify(_legacy_endpoint_types)


def _format_legacy_endpoint(endpoint):
    endpoint['type'] = endpoint['plugin_name']
    del endpoint['plugin_name']
    endpoint['type_id'] = _legacy_endpoint_ids.get(endpoint['type'])
    endpoint['data'] = ''
    endpoint['data2'] = ''
    endpoint['data3'] = ''
    if endpoint['type'] == 'email':
        endpoint['data'] = endpoint['config'].get('rcpt', '')
        endpoint['rcpt'] = endpoint['data']
    elif endpoint['type'] == 'slack':
        endpoint['data'] = endpoint['config'].get('url', '')
        endpoint['url'] = endpoint['data']
        endpoint['webhook'] = endpoint['data']
        endpoint['rich_fmt'] = endpoint['config'].get('rich') is True
        if endpoint['rich_fmt']:
            endpoint['data2'] = 'rich'
    elif endpoint['type'] == 'telegram':
        endpoint['data'] = endpoint['config'].get('chat_id', '')
        endpoint['chat_id'] = endpoint['data']
    del endpoint['config']
    endpoint['skip_dups'] = 0
    return endpoint


@admin_method
def m_endpoint_list(endpoint_id=None, addr_id=None, addr=None, **kwargs):
    logger.warning('API DEPRECATED endpoint_list')
    if endpoint_id:
        try:
            endpoint = endpoint_get(endpoint_id=endpoint_id)
            if is_secure_mode():
                try:
                    addr = addr_get(addr_id=addr_id, addr=addr)
                except LookupError:
                    abort(404)
                if addr['id'] != endpoint['addr_id']:
                    abort(403)
            return jsonify(_format_legacy_endpoint(endpoint))
        except LookupError:
            abort(404)
    else:
        return jsonify([
            _format_legacy_endpoint(endpoint)
            for endpoint in endpoint_list(addr_id=addr_id, addr=addr)
        ])


def _format_legacy_endpoint_config(plugin_name, kwargs):
    cfg = kwargs.get('config')
    if isinstance(cfg, str):
        cfg = dict_from_str(cfg)
    if not isinstance(cfg, dict):
        cfg = {}
    if plugin_name == 'email':
        if 'rcpt' not in cfg:
            rcpt = kwargs.get('data')
            if rcpt:
                cfg['rcpt'] = rcpt
    elif plugin_name == 'slack':
        if 'url' not in cfg:
            url = cfg.get('webhook')
        else:
            url = cfg.get('url')
        if not url:
            url = kwargs.get('data')
        if url:
            cfg['url'] = url
        try:
            del cfg['webhook']
        except:
            pass
        fmt = cfg.get('fmt')
        if not fmt:
            fmt = kwargs.get('data2')
        try:
            del cfg['fmt']
        except:
            pass
        cfg['rich'] = fmt != 'plain'
    elif plugin_name == 'telegram':
        if 'chat_id' not in cfg:
            chat_id = kwargs.get('data')
        if chat_id:
            cfg['chat_id'] = chat_id
    kwargs['config'] = cfg


@admin_method
def m_endpoint_create(**kwargs):
    logger.warning('API DEPRECATED endpoint_create')
    if 'et' in kwargs:
        plugin_name = _legacy_endpoint_types[int(kwargs['et'])]
        del kwargs['et']
    else:
        plugin_name = kwargs['type']
        del kwargs['type']
    del kwargs['k']
    _format_legacy_endpoint_config(plugin_name, kwargs)
    for d in ('data', 'data2', 'data3', 'skip_dups'):
        try:
            del kwargs[d]
        except:
            pass
    return jsonify(
        _format_legacy_endpoint(
            endpoint_get(endpoint_create(plugin_name, **kwargs))))


@admin_method
def m_endpoint_data(endpoint_id,
                    addr_id=None,
                    addr=None,
                    data=None,
                    data2=None,
                    data3=None,
                    **kwargs):
    logger.warning('API DEPRECATED endpoint_data')
    try:
        endpoint = endpoint_get(endpoint_id=endpoint_id)
    except LookupError:
        abort(404)
    if is_secure_mode():
        try:
            addr = addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
        if addr['id'] != endpoint['addr_id']:
            abort(403)
    cfg = endpoint['config']
    plugin_name = endpoint['plugin_name']
    if plugin_name == 'email':
        if data: cfg['rcpt'] = data
    elif plugin_name == 'slack':
        if data: cfg['url'] = data
        if data2: cfg['rich'] = data2 != 'plain'
    elif plugin_name == 'telegram':
        if data: cfg['chat_id'] = data
    try:
        endpoint_update(endpoint_id, data={'config': cfg})
    except LookupError:
        abort(404)
    endpoint['config'] = cfg
    return jsonify(_format_legacy_endpoint(endpoint))


@admin_method
def m_endpoint_config(endpoint_id, addr_id=None, addr=None, **kwargs):
    logger.warning('API DEPRECATED endpoint_config')
    try:
        endpoint = endpoint_get(endpoint_id=endpoint_id)
    except LookupError:
        abort(404)
    if is_secure_mode():
        try:
            addr = addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
        if addr['id'] != endpoint['addr_id']:
            abort(403)
    _format_legacy_endpoint_config(endpoint['plugin_name'], kwargs)
    try:
        endpoint_update(endpoint_id, data={'config': kwargs['config']})
    except LookupError:
        abort(404)
    endpoint['config'] = kwargs.get('config')
    return jsonify(_format_legacy_endpoint(endpoint))


@admin_method
def m_endpoint_skipdups(endpoint_id, addr_id=None, addr=None, **kwargs):
    logger.warning('API DEPRECATED endpoint_skipdups [dummy]')
    try:
        endpoint = endpoint_get(endpoint_id=endpoint_id)
    except LookupError:
        abort(404)
    if is_secure_mode():
        try:
            addr = addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
        if addr['id'] != endpoint['addr_id']:
            abort(403)
    return jsonify(_format_legacy_endpoint(endpoint))


@admin_method
def m_endpoint_description(endpoint_id,
                           addr_id=None,
                           addr=None,
                           description='',
                           **kwargs):
    logger.warning('API DEPRECATED endpoint_description')
    if description is None:
        description = ''
    try:
        endpoint = endpoint_get(endpoint_id=endpoint_id)
    except LookupError:
        abort(404)
    if is_secure_mode():
        try:
            addr = addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
        if addr['id'] != endpoint['addr_id']:
            abort(403)
    try:
        endpoint_update(endpoint_id, data={'description': description})
    except LookupError:
        abort(404)
    endpoint['description'] = description
    return jsonify(_format_legacy_endpoint(endpoint))


@admin_method
def m_endpoint_enable(endpoint_id, addr_id=None, addr=None, **kwargs):
    logger.warning('API DEPRECATED endpoint_enable')
    try:
        endpoint = endpoint_get(endpoint_id=endpoint_id)
    except LookupError:
        abort(404)
    if is_secure_mode():
        try:
            addr = addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
        if addr['id'] != endpoint['addr_id']:
            abort(403)
    try:
        endpoint_update(endpoint_id, data={'active': 1})
    except LookupError:
        abort(404)
    endpoint['active'] = 1
    return jsonify(_format_legacy_endpoint(endpoint))


@admin_method
def m_endpoint_disable(endpoint_id, addr_id=None, addr=None, **kwargs):
    logger.warning('API DEPRECATED endpoint_disable')
    try:
        endpoint = endpoint_get(endpoint_id=endpoint_id)
    except LookupError:
        abort(404)
    if is_secure_mode():
        try:
            addr = addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
        if addr['id'] != endpoint['addr_id']:
            abort(403)
    try:
        endpoint_update(endpoint_id, data={'active': 0})
    except LookupError:
        abort(404)
    endpoint['active'] = 0
    return jsonify(_format_legacy_endpoint(endpoint))


@admin_method
def m_endpoint_set_active(endpoint_id,
                          addr_id=None,
                          addr=None,
                          active=1,
                          **kwargs):
    logger.warning('API DEPRECATED endpoint_set_active')
    active = int(active)
    try:
        endpoint = endpoint_get(endpoint_id=endpoint_id)
    except LookupError:
        abort(404)
    if is_secure_mode():
        try:
            addr = addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
        if addr['id'] != endpoint['addr_id']:
            abort(403)
    try:
        endpoint_update(endpoint_id, data={'active': active})
    except LookupError:
        abort(404)
    endpoint['active'] = active
    return jsonify(_format_legacy_endpoint(endpoint))


@admin_method
def m_endpoint_delete(endpoint_id, addr_id=None, addr=None, **kwargs):
    logger.warning('API DEPRECATED endpoint_delete')
    try:
        endpoint = endpoint_get(endpoint_id=endpoint_id)
    except LookupError:
        abort(404)
    if is_secure_mode():
        try:
            addr = addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
        if addr['id'] != endpoint['addr_id']:
            abort(403)
    try:
        endpoint_delete(endpoint_id)
    except LookupError:
        abort(404)
    return jsonify(success)
