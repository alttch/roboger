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
from .core import get_app, get_db, send, product

from .core import addr_get, addr_get_list, addr_create, addr_delete
from .core import addr_set_active, addr_change

from functools import wraps

from pyaltt2.network import netacl_match

success = {'ok': True}


def _response_new_location(payload, code, new_id, resource):
    r = jsonify(payload) if payload else Response()
    r.status_code = code
    r.headers['Location'] = f'{api_uri_rest}/{resource}/{new_id}'
    r.autocorrect_location_header = False
    return r


def _response_created(payload, id_field, resource):
    return _response_new_location(payload, 201, id_field, resource)


def _response_moved(payload, id_field, resource):
    return _response_new_location(payload, 301, id_field, resource)


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


def _process_addr(a):
    try:
        return (int(a), None)
        addr_id = int(a)
        addr = None
    except:
        return (None, a if isinstance(a, str) else None)


@admin_method
def r_addr_list(**kwargs):
    return jsonify(addr_get_list())


@admin_method
def r_addr_get(a, **kwargs):
    addr_id, addr = _process_addr(a)
    try:
        return jsonify(addr_get(addr_id=addr_id, addr=addr))
    except LookupError:
        abort(404)


@admin_method
def r_addr_cmd(a, cmd, **kwargs):
    addr_id, addr = _process_addr(a)
    if cmd == 'change':
        new_addr = addr_change(addr_id=addr_id, addr=addr)
        return _response_moved(None, new_addr, 'addr')
    else:
        abort(404)


@admin_method
def r_addr_create(**kwargs):
    result = addr_create()
    return _response_created(result, result['a'], 'addr')


@admin_method
def r_addr_modify(a, **kwargs):
    if kwargs:
        addr_id, addr = _process_addr(a)
        if 'active' in kwargs:
            addr_set_active(addr_id=addr_id,
                            addr=addr,
                            active=int(kwargs['active']))
        return addr_get(addr_id=addr_id, addr=addr)
    else:
        return _response_empty()


@admin_method
def r_addr_delete(a, **kwargs):
    addr_id, addr = _process_addr(a)
    try:
        addr_delete(addr_id=addr_id, addr=addr)
        return _response_empty()
    except LookupError:
        abort(404)


# LEGACY


@admin_method
def test(**kwargs):
    result = success.copy()
    result.update({'version': product.version, 'build': product.build})
    return jsonify(result)


@admin_method
def m_addr_list(addr_id=None, addr=None, **kwargs):
    if addr_id or addr:
        try:
            return addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
    else:
        return jsonify(addr_get_list())


@admin_method
def m_addr_create(**kwargs):
    return jsonify(addr_create())


@admin_method
def m_addr_change(addr_id=None, addr=None, **kwargs):
    try:
        new_addr = addr_change(addr_id=addr_id, addr=addr)
        return jsonify(addr_get(addr=new_addr))
    except LookupError:
        abort(404)


@admin_method
def m_addr_set_active(addr_id=None, addr=None, active=1, **kwargs):
    try:
        return jsonify(
            addr_set_active(addr_id=addr_id, addr=addr, active=int(active)))
    except LookupError:
        abort(404)


@admin_method
def m_addr_enable(addr_id=None, addr=None, active=1, **kwargs):
    try:
        return jsonify(addr_set_active(addr_id=addr_id, addr=addr, active=1))
    except LookupError:
        abort(404)


@admin_method
def m_addr_disable(addr_id=None, addr=None, active=1, **kwargs):
    try:
        return jsonify(addr_set_active(addr_id=addr_id, addr=addr, active=0))
    except LookupError:
        abort(404)


@admin_method
def m_addr_delete(addr_id=None, addr=None, **kwargs):
    try:
        addr_delete(addr_id=addr_id, addr=addr)
        return jsonify(success)
    except LookupError:
        abort(404)
