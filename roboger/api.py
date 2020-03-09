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

success = {'ok': True}


def public_method(f):

    @wraps(f)
    def do():
        return jsonify(f(**request.json))

    return do


def admin_method(f):

    @wraps(f)
    def do():
        key = request.headers.get('X-Auth-Key', request.json.get('k'))
        if key is None:
            abort(401)
        if key != core_config['master']['key']:
            abort(403)
        return jsonify(f(**request.json))

    return do


@public_method
def ping(**kwargs):
    return success


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
        return success
    except:
        log_traceback()
        abort(503)


def init():
    app = get_app()
    app.add_url_rule('/ping', 'ping', ping, methods=['GET'])
    app.add_url_rule('/push', 'push', push, methods=['POST'])
    app.add_url_rule('/manage/test', 'test', test, methods=['GET', 'POST'])
    app.add_url_rule('/manage/addr_list',
                     'm_addr_list',
                     m_addr_list,
                     methods=['POST'])
    app.add_url_rule('/manage/addr_create',
                     'm_addr_create',
                     m_addr_create,
                     methods=['POST'])
    app.add_url_rule('/manage/addr_change',
                     'm_addr_change',
                     m_addr_change,
                     methods=['POST'])
    app.add_url_rule('/manage/addr_set_active',
                     'm_addr_set_active',
                     m_addr_set_active,
                     methods=['POST'])
    app.add_url_rule('/manage/addr_enable',
                     'm_addr_enable',
                     m_addr_enable,
                     methods=['POST'])
    app.add_url_rule('/manage/addr_disable',
                     'm_addr_disable',
                     m_addr_disable,
                     methods=['POST'])
    app.add_url_rule('/manage/addr_delete',
                     'm_addr_delete',
                     m_addr_delete,
                     methods=['POST'])


@admin_method
def test(**kwargs):
    result = success.copy()
    result.update({'version': product.version, 'build': product.build})
    return result


@admin_method
def m_addr_list(addr_id=None, addr=None, **kwargs):
    if addr_id or addr:
        try:
            return addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
    else:
        return addr_get_list()


@admin_method
def m_addr_create(**kwargs):
    return addr_create()


@admin_method
def m_addr_change(addr_id=None, addr=None, **kwargs):
    try:
        return addr_change(addr_id=addr_id, addr=addr)
    except LookupError:
        abort(404)


@admin_method
def m_addr_set_active(addr_id=None, addr=None, active=1, **kwargs):
    try:
        return addr_set_active(addr_id=addr_id, addr=addr, active=int(active))
    except LookupError:
        abort(404)


@admin_method
def m_addr_enable(addr_id=None, addr=None, active=1, **kwargs):
    try:
        return addr_set_active(addr_id=addr_id, addr=addr, active=1)
    except LookupError:
        abort(404)


@admin_method
def m_addr_disable(addr_id=None, addr=None, active=1, **kwargs):
    try:
        return addr_set_active(addr_id=addr_id, addr=addr, active=0)
    except LookupError:
        abort(404)


@admin_method
def m_addr_delete(addr_id=None, addr=None, **kwargs):
    try:
        addr_delete(addr_id=addr_id, addr=addr)
        return success
    except LookupError:
        abort(404)
