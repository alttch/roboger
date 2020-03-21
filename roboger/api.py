__author__ = 'Altertech, http://www.altertech.com/'
__copyright__ = 'Copyright (C) 2018-2020 Altertech Group'
__license__ = 'Apache License 2.0'
__version__ = '2.0.30'

from flask import request, jsonify, Response, abort, send_file, make_response
from flask_restx import Api, Resource, reqparse

import simplejson

# TODO: remove for Python 3.7+
import flask
flask.json = simplejson

import base64
import uuid
import io
import logging
import datetime
from functools import wraps

from sqlalchemy import text as sql

from .core import logger, convert_level, log_traceback, config as core_config
from .core import get_real_ip
from .core import get_app, get_db, send, product, is_secure_mode, is_use_limits
from .core import check_addr_limit, OverlimitError, reset_addr_limits

from .core import addr_get, addr_list, addr_create, addr_delete
from .core import addr_set_active, addr_set_limit, addr_change

from .core import endpoint_get, endpoint_list, endpoint_create
from .core import endpoint_update, endpoint_delete
from .core import endpoint_delete_subscriptions

from .core import subscription_get, subscription_list, subscription_create
from .core import subscription_update, subscription_delete
from .core import cleanup as core_cleanup, plugin_list

from .core import json, is_parse_db_json, delete_everything
from .core import bucket_get, bucket_touch

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


def _response_conflict(msg=None):
    return Response(msg if msg else 'resource already exists', status=409)


def _response_empty():
    return Response(status=204)


def _response_not_found(msg=None):
    return Response(msg, status=404)


def _response_accepted():
    return Response(status=202)


def public_method(f):

    @wraps(f)
    def do(*args, **kwargs):
        logger.debug(f'API call {get_real_ip()} {f.__qualname__}')
        return f(*args, **kwargs)

    return do


def admin_method(f):

    @wraps(f)
    def do(*args, **kwargs):
        ip = get_real_ip()
        payload = request.json if request.json else {}
        kw = {**kwargs, **payload}
        logger.debug(f'API admin call {ip} method: {f.__name__}, args: {args}, '
                     f'kwargs: {kw}')
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
        return f(*args, **kw)

    return do


api_uri = '/manage'

api_uri_rest = f'{api_uri}/v2'


def init():
    app = get_app()

    api = Api(app=app)
    ns_public = api.namespace('/', description='Public functions')

    @ns_public.route('/ping')
    class Ping(Resource):

        method_decorators = [public_method]

        @api.response(204, 'server works properly')
        def get(self):
            """
            Check server health
            """
            get_db()
            return '', 204

    @ns_public.route('/file/<string:object_id>')
    class File(Resource):

        method_decorators = [public_method]

        @api.response(200, 'serving file')
        @api.response(404, 'file not found')
        @api.produces(['*/*'])
        def get(self, object_id):
            try:
                o = bucket_get(object_id, public=True)
                buf = io.BytesIO()
                buf.write(o['content'])
                buf.seek(0)
                bucket_touch(object_id)
                resp = make_response(
                    send_file(buf,
                              mimetype=o['mimetype'],
                              cache_timeout=round(
                                  o['expires'].total_seconds())))
                for k, v in o['metadata'].items():
                    resp.headers[f'x-roboger-{k}'] = str(v)
                resp.headers['Content-Type'] = o['mimetype']
                if o['fname']:
                    resp.headers['roboger-file-name'] = o['fname']
                return resp
            except LookupError:
                return 'no such file', 404

    @ns_public.route('/push')
    class Push(Resource):

        method_decorators = [public_method]

        p_push = reqparse.RequestParser()
        p_push.add_argument('addr',
                            required=True,
                            help='recipient address',
                            type=str)
        p_push.add_argument('sender',
                            default=None,
                            help='event sender',
                            type=str)
        p_push.add_argument('msg', default='', help='message text', type=str)
        p_push.add_argument('subject',
                            default='',
                            help='message subject',
                            type=str)
        p_push.add_argument('level', default='info', help='event level')
        p_push.add_argument('location',
                            default=None,
                            help='event location',
                            type=str)
        p_push.add_argument('tag', default=None, help='event tag', type=str)
        p_push.add_argument('keywords',
                            default=None,
                            help='event keyword (obsolete, don\'t use)',
                            type=str)
        p_push.add_argument('expires',
                            default=None,
                            help='reserved, don\'t use')
        p_push.add_argument('media',
                            default=None,
                            help='base64-encoded media file',
                            type=str)
        p_push.add_argument('media_fname',
                            default=None,
                            help='media file name, auto generated if empty',
                            type=str)

        @api.response(202, 'event message successfully accepted')
        @api.response(404, 'recipient address not found')
        @api.response(406, 'recipient address is disabled')
        @api.response(429, 'recipient address is out of limit')
        @api.response(503, 'server error')
        @api.expect(p_push, validate=True)
        def post(self):
            """
            Push event message
            """
            try:
                event_id = str(uuid.uuid4())
                try:
                    a = self.p_push.parse_args(strict=True)
                except Exception as e:
                    return str(e), 400
                logger.info(f'API message to {a.addr}')
                # TODO: remove keywords when removing legacy
                if a.keywords is not None:
                    a.tag = a.keywords
                if a.media:
                    try:
                        media = base64.b64decode(a.media)
                        if a.media_fname and '/' in a.media_fname:
                            a.media_fname = a.media_fname.rsplit('/', 1)[-1]
                    except:
                        media = None
                        a.media = None
                        logger.warning(
                            f'API invalid media file, event {event_id}'
                            f' message to {a.addr}')
                else:
                    media = None
                level = convert_level(a.level)
                level_name = logging.getLevelName(level)
                if a.sender:
                    s = a.sender.split('@', 1)[0] if a.location else a.sender
                else:
                    s = None
                formatted_subject = '{} {}{}{}'.format(
                    level_name, s if s is not None else '',
                    f'@{a.location}' if a.location else '',
                    f': {a.subject}' if a.subject else '')

                try:
                    addr = addr_get(addr=a.addr)
                    if addr['active'] < 1:
                        return f'addr {a.addr} is disabled', 406
                    if is_use_limits():
                        check_addr_limit(addr,
                                         level=level,
                                         size=request.content_length)
                except LookupError:
                    logger.info(f'API no such address: {a.addr}')
                    return f'addr {a.addr} not found', 404
                except OverlimitError as e:
                    return str(e), 429
                for row in get_db().execute(sql("""
                    SELECT plugin_name, config, addr.id as addr_id
                    FROM subscription JOIN endpoint ON
                        endpoint.id = subscription.endpoint_id JOIN addr ON
                        endpoint.addr_id = addr.id WHERE
                        addr.a=:a
                        AND addr.active=1
                        AND subscription.active = 1
                        AND endpoint.active = 1
                        AND (location=:location or location IS null)
                        AND (tag=:tag or tag IS null)
                        AND (sender=:sender or sender IS null)
                        AND (
                            (level=:level AND level_match='e') OR
                            (level<:level and level_match='g') OR
                            (level<=:level and level_match='ge') OR
                            (level>:level and level_match='l') OR
                            (level>=:level and level_match='le')
                            )
                            """),
                                            a=a.addr,
                                            location=a.location,
                                            tag=a.tag,
                                            sender=a.sender,
                                            level=level):
                    send(row.plugin_name,
                         config=json.loads(row.config)
                         if is_parse_db_json() else row.config,
                         event_id=event_id,
                         addr=a.addr,
                         addr_id=row.addr_id,
                         msg=a.msg,
                         subject=a.subject,
                         formatted_subject=formatted_subject,
                         level=level,
                         level_name=level_name,
                         location=a.location,
                         tag=a.tag,
                         sender=a.sender,
                         media=media,
                         media_encoded=a.media,
                         media_fname=a.media_fname)
                return _response_accepted()
            except:
                log_traceback()
                return '', 503

    # v2 (RESTful)
    app.add_url_rule(f'{api_uri_rest}/core', 'test', test, methods=['GET'])
    app.add_url_rule(f'{api_uri_rest}/core',
                     'core.cmd',
                     r_core_cmd,
                     methods=['POST'])

    app.add_url_rule(f'{api_uri_rest}/plugin',
                     'plugin.list',
                     r_plugin_list,
                     methods=['GET'])

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

    app.add_url_rule(f'{api_uri_rest}/addr/<a>/endpoint/<ep>/subscription',
                     'subscription.list',
                     r_subscription_list,
                     methods=['GET'])
    app.add_url_rule(f'{api_uri_rest}/addr/<a>/endpoint/<ep>/subscription/<s>',
                     'subscription.post',
                     r_subscription_cmd,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri_rest}/addr/<a>/endpoint/<ep>/subscription/<s>',
                     'subscription.get',
                     r_subscription_get,
                     methods=['GET'])
    app.add_url_rule(f'{api_uri_rest}/addr/<a>/endpoint/<ep>/subscription',
                     'subscription.create',
                     r_subscription_create,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri_rest}/addr/<a>/endpoint/<ep>/subscription/<s>',
                     'subscription.modify',
                     r_subscription_modify,
                     methods=['PATCH'])
    app.add_url_rule(f'{api_uri_rest}/addr/<a>/endpoint/<ep>/subscription/<s>',
                     'subscription.delete',
                     r_subscription_delete,
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

    app.add_url_rule(f'{api_uri}/subscription_list',
                     'm_subscription_list',
                     m_subscription_list,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/subscription_create',
                     'm_subscription_create',
                     m_subscription_create,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/subscription_enable',
                     'm_subscription_enable',
                     m_subscription_enable,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/subscription_disable',
                     'm_subscription_disable',
                     m_subscription_disable,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/subscription_set_active',
                     'm_subscription_set_active',
                     m_subscription_set_active,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/subscription_location',
                     'm_subscription_location',
                     m_subscription_location,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/subscription_keywords',
                     'm_subscription_keywords',
                     m_subscription_keywords,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/subscription_senders',
                     'm_subscription_senders',
                     m_subscription_senders,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/subscription_level',
                     'm_subscription_level',
                     m_subscription_level,
                     methods=['POST'])
    app.add_url_rule(f'{api_uri}/subscription_delete',
                     'm_subscription_delete',
                     m_subscription_delete,
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
    except:
        return (None, a if isinstance(a, str) else None)


@admin_method
def test(**kwargs):
    result = success.copy()
    result.update({'version': product.version, 'build': product.build})
    return jsonify(result)


@admin_method
def r_core_cmd(cmd=None):
    if cmd == 'reset-addr-limits':
        reset_addr_limits()
    elif cmd == 'cleanup':
        core_cleanup()
    elif cmd == 'delete-everything':
        delete_everything()
    else:
        abort(405)
    return _response_empty()


@admin_method
def r_plugin_list():
    result = []
    for k, v in plugin_list().items():
        result.append({
            'plugin_name': k,
            'version': getattr(v, '__version__', None),
            'description': getattr(v, '__description__', None),
            'url': getattr(v, '__url__', None)
        })
    return jsonify(sorted(result, key=lambda k: k['plugin_name']))


@admin_method
def r_addr_list():
    return jsonify(addr_list())


@admin_method
def r_addr_get(a):
    addr_id, addr = _process_addr(a)
    try:
        return jsonify(addr_get(addr_id=addr_id, addr=addr))
    except LookupError:
        return _response_not_found(f'addr {a} not found')


@admin_method
def r_addr_cmd(a, cmd, to=None):
    addr_id, addr = _process_addr(a)
    try:
        if cmd == 'change':
            if to is not None and len(to) != 64:
                return Response('addr size should be 64 symbols', status=400)
            try:
                new_addr = addr_change(addr_id=addr_id, addr=addr, to=to)
                return _response_moved(None, new_addr, 'addr')
            except ValueError:
                return _response_conflict()
    except LookupError:
        return _response_not_found(f'addr {a} not found')


@admin_method
def r_addr_create():
    result = addr_get(addr_create())
    return _response_created(
        result if _accept_resource('roboger.addr') else None, result['a'],
        'addr')


@admin_method
def r_addr_modify(a, active=None, lim_c=None, lim_s=None):
    addr_id, addr = _process_addr(a)
    try:
        if active is not None:
            addr_set_active(addr_id=addr_id, addr=addr, active=int(active))
        if lim_c is not None or lim_s is not None:
            addr_set_limit(addr_id=addr_id,
                           addr=addr,
                           lim_c=int(lim_c),
                           lim_s=int(lim_s))
        return jsonify(addr_get(addr_id=addr_id,
                                addr=addr)) if _accept_resource(
                                    'roboger.addr') else _response_empty()
    except LookupError:
        return _response_not_found(f'addr {a} not found')


@admin_method
def r_addr_delete(a):
    addr_id, addr = _process_addr(a)
    try:
        addr_delete(addr_id=addr_id, addr=addr)
        return _response_empty()
    except LookupError:
        return _response_not_found(f'addr {a} not found')


def _get_object_verify_addr(obj_id, a, getfunc, **kwargs):
    # TODO: move addr verification to get SQL (after removing legacy API)
    addr_id, addr = _process_addr(a)
    obj = getfunc(obj_id, **kwargs)
    addr = addr_get(addr_id=addr_id, addr=addr)
    if obj['addr_id'] == addr['id']:
        return obj
    else:
        raise LookupError


@admin_method
def r_endpoint_list(a):
    addr_id, addr = _process_addr(a)
    try:
        addr = addr_get(addr_id=addr_id, addr=addr)
        return jsonify(endpoint_list(addr_id=addr['id']))
    except LookupError:
        return _response_not_found(f'addr {a} not found')


@admin_method
def r_endpoint_get(a, ep):
    try:
        endpoint = _get_object_verify_addr(ep, a, endpoint_get)
        return jsonify(endpoint)
    except LookupError:
        return _response_not_found(f'endpoint {a}/{ep} not found')


@admin_method
def r_endpoint_cmd(a, ep, cmd, **kwargs):
    try:
        endpoint = _get_object_verify_addr(ep, a, endpoint_get)
        if cmd == 'copysub':
            try:
                target = int(kwargs['target'])
                target_endpoint = _get_object_verify_addr(
                    target, a, endpoint_get)
            except:
                return _response_not_found(
                    f'target endpoint {a}/{target} not found')
            subscriptions = subscription_list(endpoint['id'])
            if kwargs.get('replace'):
                endpoint_delete_subscriptions(target)
            for s in subscriptions:
                del s['id']
                del s['addr_id']
                del s['active']
                del s['endpoint_id']
                subscription_create(target, **s)
            return _response_empty()
        abort(405)
    except LookupError:
        return _response_not_found(f'endpoint {a}/{ep} not found')


@admin_method
def r_endpoint_create(a, plugin_name, **kwargs):
    addr_id, addr = _process_addr(a)
    try:
        addr_get(addr_id=addr_id, addr=addr)
    except LookupError:
        return _response_not_found(f'addr {a} not found')
    try:
        result = endpoint_get(
            endpoint_create(plugin_name,
                            addr_id=addr_id,
                            addr=addr,
                            validate_config=True,
                            **kwargs))
    except LookupError as e:
        return _response_not_found(str(e))
    except ValueError as e:
        return Response(str(e), status=400)
    return _response_created(
        result if _accept_resource('roboger.endpoint') else None, result['id'],
        f'addr/{a}/endpoint')


@admin_method
def r_endpoint_modify(a, ep, **kwargs):
    try:
        endpoint = _get_object_verify_addr(ep, a, endpoint_get)
    except LookupError:
        return _response_not_found(f'endpoint {a}/{ep} not found')
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
            log_traceback()
            return Response(str(e), status=400)
    return jsonify(endpoint_get(ep)) if _accept_resource(
        'roboger.endpoint') else _response_empty()


@admin_method
def r_endpoint_delete(a, ep):
    try:
        endpoint = _get_object_verify_addr(ep, a, endpoint_get)
        endpoint_delete(endpoint_id=ep)
        return _response_empty()
    except LookupError:
        return _response_not_found(f'endpoint {a}/{ep} not found')


@admin_method
def r_subscription_list(a, ep):
    try:
        endpoint = _get_object_verify_addr(ep, a, endpoint_get)
        return jsonify(subscription_list(ep))
    except LookupError:
        return _response_not_found(f'endpoint {a}/{ep} not found')


@admin_method
def r_subscription_get(a, ep, s):
    try:
        subscription = _get_object_verify_addr(s,
                                               a,
                                               subscription_get,
                                               endpoint_id=ep)
        if subscription['endpoint_id'] != int(ep):
            raise LookupError
        else:
            return jsonify(subscription)
    except LookupError:
        return _response_not_found(f'subscription {a}/{ep}/{s} not found')


@admin_method
def r_subscription_cmd(a, ep, s, cmd):
    try:
        subscription = _get_object_verify_addr(s,
                                               a,
                                               subscription_get,
                                               endpoint_id=ep)
        if subscription['endpoint_id'] != int(ep):
            raise LookupError
        else:
            pass
        abort(405)
    except LookupError:
        return _response_not_found(f'subscription {a}/{ep}/{s} not found')


@admin_method
def r_subscription_create(a, ep, **kwargs):
    addr_id, addr = _process_addr(a)
    try:
        endpoint = _get_object_verify_addr(ep, a, endpoint_get)
        kwargs['level'] = convert_level(kwargs['level'])
        result = subscription_get(subscription_create(ep, **kwargs))
    except LookupError:
        return _response_not_found(f'endpoint {a}/{ep} not found')
    except ValueError as e:
        return Response(str(e), status=400)
    return _response_created(
        result if _accept_resource('roboger.subscription') else None,
        result['id'], f'addr/{a}/subscription')


@admin_method
def r_subscription_modify(a, ep, s, **kwargs):
    try:
        subscription = _get_object_verify_addr(s, a, subscription_get)
        if subscription['endpoint_id'] != int(ep):
            raise LookupError
    except LookupError:
        return _response_not_found(f'subscription {a}/{ep}/{s} not found')
    if kwargs:
        for field in ['id', 'endpoint_id', 'addr_id']:
            if field in kwargs:
                return Response(f'Field "{field}" is protected', status=405)
        try:
            if 'level' in kwargs:
                kwargs['level'] = convert_level(kwargs['level'])
            subscription_update(s, kwargs)
        except ValueError as e:
            return Response(str(e), status=400)
    return jsonify(subscription_get(s)) if _accept_resource(
        'roboger.subscription') else _response_empty()


@admin_method
def r_subscription_delete(a, ep, s):
    try:
        subscription = _get_object_verify_addr(s, a, subscription_get)
        if subscription['endpoint_id'] != int(ep):
            raise LookupError
        else:
            subscription_delete(subscription_id=s)
            return _response_empty()
    except LookupError:
        return _response_not_found(f'subscription {a}/{ep}/{s} not found')


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


def _format_legacy_subscription(subscription):
    subscription['keywords'] = [
        subscription['tag'] if subscription['tag'] is not None else ''
    ]
    subscription['senders'] = [
        subscription['sender'] if subscription['sender'] is not None else ''
    ]
    subscription['level_id'] = subscription['level']
    subscription['level'] = logging.getLevelName(subscription['level_id'])
    if subscription['location'] is None:
        subscription['location'] = ''
    del subscription['tag']
    del subscription['sender']
    return subscription


@admin_method
def m_subscription_create(endpoint_id, addr_id=None, addr=None, **kwargs):
    logger.warning('API DEPRECATED subscription_create')
    if is_secure_mode():
        endpoint = endpoint_get(endpoint_id)
        try:
            addr = addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
        if addr['id'] != endpoint['addr_id']:
            abort(403)
    if 'senders' in kwargs:
        senders = kwargs['senders']
        if isinstance(senders, list):
            senders = ''.join(senders)
        elif isinstance(senders, str):
            senders = senders.split(',', 1)[0]
        kwargs['sender'] = senders
        del kwargs['senders']
    if 'keywords' in kwargs:
        keywords = kwargs['keywords']
        if isinstance(keywords, list):
            keywords = ''.join(keywords)
        elif isinstance(keywords, str):
            keywords = keywords.split(',', 1)[0]
        kwargs['tag'] = keywords
        del kwargs['keywords']
    del kwargs['k']
    return jsonify(
        _format_legacy_subscription(
            subscription_get(subscription_create(endpoint_id, **kwargs))))


@admin_method
def m_subscription_list(subscription_id=None,
                        endpoint_id=None,
                        addr_id=None,
                        addr=None,
                        **kwargs):
    logger.warning('API DEPRECATED endpoint_list')
    if is_secure_mode():
        try:
            addr = addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
    if subscription_id:
        try:
            subscription = subscription_get(subscription_id=subscription_id)
            if is_secure_mode():
                if addr['id'] != subscription['addr_id']:
                    abort(403)
            return jsonify(_format_legacy_subscription(subscription))
        except LookupError:
            abort(404)
    else:
        return jsonify([
            _format_legacy_subscription(subscription)
            for subscription in subscription_list(
                endpoint_id, addr_id=addr['id'] if is_secure_mode() else None)
        ])


@admin_method
def m_subscription_delete(subscription_id, addr_id=None, addr=None, **kwargs):
    logger.warning('API DEPRECATED subscription_delete')
    if is_secure_mode():
        subscription = subscription_get(subscription_id)
        try:
            addr = addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
        if addr['id'] != subscription['addr_id']:
            abort(403)
    try:
        subscription_delete(subscription_id)
    except LookupError:
        abort(404)
    return jsonify(success)


@admin_method
def m_subscription_enable(subscription_id, addr_id=None, addr=None, **kwargs):
    logger.warning('API DEPRECATED subscription_enable')
    if is_secure_mode():
        subscription = subscription_get(subscription_id)
        try:
            addr = addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
        if addr['id'] != subscription['addr_id']:
            abort(403)
    try:
        subscription_update(subscription_id, data={'active': 1})
    except LookupError:
        abort(404)
    subscription['active'] = 1
    return jsonify(_format_legacy_subscription(subscription))


@admin_method
def m_subscription_disable(subscription_id, addr_id=None, addr=None, **kwargs):
    logger.warning('API DEPRECATED subscription_disable')
    if is_secure_mode():
        subscription = subscription_get(subscription_id)
        try:
            addr = addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
        if addr['id'] != subscription['addr_id']:
            abort(403)
    try:
        subscription_update(subscription_id, data={'active': 0})
    except LookupError:
        abort(404)
    subscription['active'] = 0
    return jsonify(_format_legacy_subscription(subscription))


@admin_method
def m_subscription_set_active(subscription_id,
                              addr_id=None,
                              addr=None,
                              active=1,
                              **kwargs):
    logger.warning('API DEPRECATED subscription_set_active')
    active = int(active)
    if is_secure_mode():
        subscription = subscription_get(subscription_id)
        try:
            addr = addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
        if addr['id'] != subscription['addr_id']:
            abort(403)
    try:
        subscription_update(subscription_id, data={'active': active})
    except LookupError:
        abort(404)
    subscription['active'] = active
    return jsonify(_format_legacy_subscription(subscription))


@admin_method
def m_subscription_location(subscription_id,
                            addr_id=None,
                            addr=None,
                            location='',
                            **kwargs):
    logger.warning('API DEPRECATED subscription_location')
    if is_secure_mode():
        subscription = subscription_get(subscription_id)
        try:
            addr = addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
        if addr['id'] != subscription['addr_id']:
            abort(403)
    try:
        subscription_update(subscription_id, data={'location': location})
    except LookupError:
        abort(404)
    subscription['location'] = location
    return jsonify(_format_legacy_subscription(subscription))


@admin_method
def m_subscription_keywords(subscription_id,
                            addr_id=None,
                            addr=None,
                            keywords='',
                            **kwargs):
    logger.warning('API DEPRECATED subscription_keywords')
    if is_secure_mode():
        subscription = subscription_get(subscription_id)
        try:
            addr = addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
        if addr['id'] != subscription['addr_id']:
            abort(403)
    if isinstance(keywords, list):
        keywords = ''.join(keywords)
    elif isinstance(keywords, str):
        keywords = keywords.split(',', 1)[0]
    try:
        subscription_update(subscription_id, data={'tag': keywords})
    except LookupError:
        abort(404)
    subscription['tag'] = keywords
    return jsonify(_format_legacy_subscription(subscription))


@admin_method
def m_subscription_senders(subscription_id,
                           addr_id=None,
                           addr=None,
                           senders='',
                           **kwargs):
    logger.warning('API DEPRECATED subscription_set_active')
    if is_secure_mode():
        subscription = subscription_get(subscription_id)
        try:
            addr = addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
        if addr['id'] != subscription['addr_id']:
            abort(403)
    if isinstance(senders, list):
        senders = ''.join(senders)
    elif isinstance(senders, str):
        senders = senders.split(',', 1)[0]
    try:
        subscription_update(subscription_id, data={'sender': senders})
    except LookupError:
        abort(404)
    subscription['sender'] = senders
    return jsonify(_format_legacy_subscription(subscription))


@admin_method
def m_subscription_level(subscription_id, addr_id=None, addr=None, **kwargs):
    logger.warning('API DEPRECATED subscription_level')
    if is_secure_mode():
        subscription = subscription_get(subscription_id)
        try:
            addr = addr_get(addr_id=addr_id, addr=addr)
        except LookupError:
            abort(404)
        if addr['id'] != subscription['addr_id']:
            abort(403)
    level_id = kwargs.get('level_id')
    if not level_id:
        level_id = convert_level(kwargs.get('level'))
    level_match = kwargs.get('level_match', 'ge')
    try:
        subscription_update(subscription_id,
                            data={
                                'level': level_id,
                                'level_match': level_match
                            })
    except LookupError:
        abort(404)
    subscription['level'] = level_id
    subscription['level_match'] = level_match
    return jsonify(_format_legacy_subscription(subscription))
