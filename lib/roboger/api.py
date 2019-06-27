__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2018-2019 Altertech Group"
__license__ = "Apache License 2.0"
__version__ = "1.0.2"

import cherrypy
import roboger.core
import roboger.events
import roboger.endpoints
import logging
import base64
import json
import shlex

from types import SimpleNamespace

from netaddr import IPNetwork

from roboger.core import format_json
from roboger.core import db
from sqlalchemy import text as sql


# throws exception
def dict_from_str(s, spl=','):
    if not isinstance(s, str): return s
    result = {}
    if not s: return result
    vals = s.split(spl)
    for v in vals:
        print(v)
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


def api_forbidden():
    raise cherrypy.HTTPError('403 Forbidden', 'Invalid API key')


def api_404(obj=None):
    o = obj if obj else 'object'
    raise cherrypy.HTTPError('404 Not Found', 'No such %s' % o)


def api_invalid_json_data():
    raise cherrypy.HTTPError('500 API Error', 'Invalid JSON data')


def api_invalid_data(msg=''):
    raise cherrypy.HTTPError('500 API Error', 'Invalid data. %s' % msg)


def api_internal_error():
    raise cherrypy.HTTPError('500 API Error',
                             'Internal API Error. See logs for details')


def http_real_ip():
    # if cherrypy.request.headers.get('X-Real-IP'):
    # ip = cherrypy.request.headers.get('X-Real-IP')
    # else:
    ip = cherrypy.request.remote.ip
    return ip


def api_result(status='OK', msg=None, data=None):
    result = {'result': status}
    if msg:
        result['message'] = msg
    if data:
        result.update(data)
    return result


def cp_json_handler(*args, **kwargs):
    value = cherrypy.serving.request._json_inner_handler(*args, **kwargs)
    return format_json(
        value, minimal=not roboger.core.is_development()).encode('utf-8')


def update_config(cfg):
    try:
        config.host, config.port = roboger.core.parse_host_port(
            cfg.get('api', 'listen'))
        if not config.port:
            config.port = default_port
        logging.debug('api.listen = %s:%u' % (config.host, config.port))
    except:
        roboger.core.log_traceback()
        return False
    try:
        config.ssl_host, config.ssl_port = parse_host_port(
            cfg.get('api', 'ssl_listen'))
        if not config.ssl_port:
            config.ssl_port = default_ssl_port
        try:
            config.ssl_module = cfg.get('api', 'ssl_module')
        except:
            config.ssl_module = 'builtin'
        config.ssl_cert = cfg.get('api', 'ssl_cert')
        if config.ssl_cert[0] != '/':
            config.ssl_cert = roboger.core.dir_etc + '/' + config.ssl_cert
        config.ssl_key = cfg.get('api', 'ssl_key')
        if config.ssl_key[0] != '/':
            config.ssl_key = roboger.core.dir_etc + '/' + config.ssl_key
        logging.debug(
            'api.ssl_listen = %s:%u' % (config.ssl_host, config.ssl_port))
        config.ssl_chain = cfg.get('api', 'ssl_chain')
        if config.ssl_chain[0] != '/':
            config.ssl_chain = roboger.core.dir_etc + '/' + config.ssl_chain
    except:
        pass
    try:
        config.thread_pool = int(cfg.get('api', 'thread_pool'))
    except:
        pass
    logging.debug('api.thread_pool = %u' % config.thread_pool)
    roboger.core.config.db_pool_size = config.thread_pool
    try:
        config.masterkey = cfg.get('api', 'masterkey')
        logging.debug('api.masterkey loaded')
    except:
        logging.error('masterkey not found in config. Can not continue')
        return None
    try:
        _ha = cfg.get('api', 'master_allow')
    except:
        _ha = '127.0.0.1'
    try:
        _hosts_allow = list(filter(None, [x.strip() for x in _ha.split(',')]))
        config.master_allow = [IPNetwork(h) for h in _hosts_allow]
    except:
        logging.error('invalid master host acl!')
        roboger.core.log_traceback()
        return None
    logging.debug('api.master_allow = %s' % ', '.join(
        [str(h) for h in config.master_allow]))
    try:
        config.check_ownership = (cfg.get('api',
                                          'config.check_ownership') == 'yes')
    except:
        config.check_ownership = False
    logging.debug('api.config.check_ownership = %s' % config.check_ownership)
    return True


def start():
    if not config.host: return False
    cherrypy.tree.mount(PushAPI(), '/')
    cherrypy.tree.mount(MasterAPI(), '/manage')
    cherrypy.server.unsubscribe()
    logging.info('HTTP API listening at at %s:%s' % (config.host, config.port))
    server1 = cherrypy._cpserver.Server()
    server1.socket_port = config.port
    server1._socket_host = config.host
    server1.thread_pool = config.thread_pool
    server1.subscribe()
    if config.ssl_host and config.ssl_module and \
            config.ssl_cert and config.ssl_key:
        logging.info('HTTP API SSL listening at %s:%s' % (config.ssl_host,
                                                          config.ssl_port))
        server_ssl = cherrypy._cpserver.Server()
        server_ssl.socket_port = config.ssl_port
        server_ssl._socket_host = config.ssl_host
        server_ssl.thread_pool = config.thread_pool
        server_ssl.ssl_certificate = config.ssl_cert
        server_ssl.ssl_private_key = config.ssl_key
        if config.ssl_chain:
            server_ssl.ssl_certificate_chain = config.ssl_chain
        if ssl_module:
            server_ssl.ssl_module = config.ssl_module
        server_ssl.subscribe()
    if not roboger.core.is_development():
        cherrypy.config.update({'environment': 'production'})
        cherrypy.log.access_log.propagate = False
        cherrypy.log.error_log.propagate = False
    else:
        cherrypy.config.update({'global': {'engine.autoreload.on': False}})
    cherrypy.engine.start()


@roboger.core.shutdown
def stop():
    cherrypy.engine.exit()


class MasterAPI(object):

    _cp_config = {
        'tools.json_out.on': True,
        'tools.json_out.handler': cp_json_handler,
        'tools.auth.on': True,
    }

    def __init__(self):
        cherrypy.tools.auth = cherrypy.Tool(
            'before_handler', self.cp_pre, priority=60)

    def cp_pre(self):
        if roboger.core.netacl_match(http_real_ip(), config.master_allow):
            k = cherrypy.request.headers.get('X-Auth-Key')
            if not k:
                k = cherrypy.serving.request.params.get('k')
            if 'data' in cherrypy.serving.request.params:
                try:
                    cherrypy.serving.request.params['data'] = json.loads(
                        cherrypy.serving.request.params['data'])
                except:
                    api_invalid_json_data()
            else:
                if 'data' in cherrypy.serving.request.params:
                    try:
                        d = json.loads(cherrypy.serving.request.params['data'])
                    except:
                        api_invalid_json_data()
                else:
                    cl = cherrypy.request.headers['Content-Length']
                    rawbody = cherrypy.request.body.read(int(cl))
                    try:
                        d = json.loads(rawbody.decode())
                    except:
                        api_invalid_json_data()
                if not k: k = d.get('k')
                cherrypy.serving.request.params['data'] = d
            if k == config.masterkey:
                return
        api_forbidden()

    @cherrypy.expose
    def test(self, data):
        d = {}
        d['version'] = roboger.core.product.version
        d['build'] = roboger.core.product.build
        return d

    @cherrypy.expose
    def addr_list(self, data):
        r = []
        if 'addr_id' in data or 'addr' in data:
            addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
            if not addr:
                api_404('address')
            return addr.serialize()
        else:
            for i, addr in roboger.addr.addrs_by_id.copy().items():
                if not addr._destroyed: r.append(addr.serialize())
        return sorted(r, key=lambda k: k['id'])

    @cherrypy.expose
    def addr_create(self, data):
        addr = roboger.addr.append_addr()
        return addr.serialize()

    @cherrypy.expose
    def addr_change(self, data):
        addr = roboger.addr.change_addr(data.get('addr_id'), data.get('addr'))
        if not addr:
            api_404('address')
        return addr.serialize()

    @cherrypy.expose
    def addr_set_active(self, data):
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if not addr:
            api_404('address')
        try:
            _active = int(data['active'])
        except:
            _active = 1
        addr.set_active(_active)
        return addr.serialize()

    @cherrypy.expose
    def addr_enable(self, data):
        data['active'] = 1
        return self.addr_set_active(data)

    @cherrypy.expose
    def addr_disable(self, data):
        data['active'] = 0
        return self.addr_set_active(data)

    @cherrypy.expose
    def addr_delete(self, data):
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if not addr:
            api_404('address')
        addr.destroy()
        return api_result()

    @cherrypy.expose
    def endpoint_types(self, data):
        result = []
        try:
            c = db().execute(
                sql('select id, name from endpoint_type order by id'))
            while True:
                r = c.fetchone()
                if r is None: break
                result.append({'id': r.id, 'name': r.name})
        except:
            roboger.core.log_traceback()
            api_internal_error()
        return sorted(result, key=lambda k: k['id'])

    @cherrypy.expose
    def endpoint_list(self, data):
        r = []
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if 'endpoint_id' in data:
            e = roboger.endpoints.get_endpoint(data['endpoint_id'])
            if not e or (config.check_ownership and e.addr != addr):
                api_404('endpoint or wrong address')
            return e.serialize()
        else:
            try:
                if addr and addr.addr_id in \
                        roboger.endpoints.endpoints_by_addr_id:
                    for i, e in roboger.endpoints.endpoints_by_addr_id[
                            addr.addr_id].copy().items():
                        if not e._destroyed:
                            r.append(e.serialize())
            except:
                roboger.core.log_traceback()
                api_internal_error()
        return sorted(r, key=lambda k: k['id'])

    @cherrypy.expose
    def endpoint_create(self, data):
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if addr is None:
            api_invalid_data('No such address')
        endpoint_type = data.get('et')
        if not endpoint_type:
            endpoint_type = roboger.endpoints.get_endpoint_code(
                data.get('type'))
        if not endpoint_type: api_invalid_data('Specify endpoint type')
        cfg = data.get('config')
        if isinstance(cfg, str):
            cfg = dict_from_str(cfg)
        elif not isinstance(cfg, dict):
            cfg = {}
        try:
            # android app
            if endpoint_type == 1:
                registration_id = cfg.get('registration_id')
                if not registration_id: registration_id = data.get('data')
                e = roboger.endpoints.AndroidEndpoint(
                        addr,
                        registration_id,
                        description=data.get('description'),
                        autosave=False)
            # email
            elif endpoint_type == 2:
                email = cfg.get('rcpt')
                if not email: email = data.get('data')
                e = roboger.endpoints.EmailEndpoint(
                    addr,
                    email,
                    description=data.get('description'),
                    autosave=False)
            # http/post
            elif endpoint_type == 3:
                url = cfg.get('url')
                if not url: url = data.get('data')
                params = cfg.get('params')
                if not params: params = data.get('data3')
                e = roboger.endpoints.HTTPPostEndpoint(
                    addr,
                    url,
                    params,
                    description=data.get('description'),
                    autosave=False)
            # http/json
            elif endpoint_type == 4:
                url = cfg.get('url')
                if not url: url = data.get('data')
                params = cfg.get('params')
                if not params: params = data.get('data3')
                e = roboger.endpoints.HTTPJSONEndpoint(
                    addr,
                    url,
                    params,
                    description=data.get('description'),
                    autosave=False)
            # slack
            elif endpoint_type == 100:
                url = cfg.get('url')
                if not url:
                    url = cfg.get('webhook')
                if not url: url = data.get('data')
                fmt = cfg.get('fmt')
                if not fmt: fmt = data.get('data2')
                e = roboger.endpoints.SlackEndpoint(
                    addr,
                    url,
                    fmt,
                    description=data.get('description'),
                    autosave=False)
            # telegram
            elif endpoint_type == 101:
                chat_id = cfg.get('chat_id')
                if not chat_id: chat_id = data.get('data')
                e = roboger.endpoints.TelegramEndpoint(
                    addr,
                    chat_id,
                    description=data.get('description'),
                    autosave=False)
            else:
                e = None
        except:
            roboger.core.log_traceback()
            api_internal_error()
        skip_dups = data.get('skip_dups')
        if skip_dups:
            try:
                e.set_skip_dups(skip_dups)
            except:
                roboger.core.log_traceback()
                api_internal_error()
        if not e:
            api_invalid_data('No such endpoint type')
        try:
            e.save()
        except:
            roboger.core.log_traceback()
            api_internal_error()
        roboger.endpoints.append_endpoint(e)
        return e.serialize()

    @cherrypy.expose
    def endpoint_data(self, data):
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        e = roboger.endpoints.get_endpoint(data.get('endpoint_id'))
        if not e or (config.check_ownership and e.addr != addr):
            api_404('endpoint or wrong address')
        try:
            e.set_data(data['data'], data.get('data2'), data.get('data3'))
        except:
            roboger.core.log_traceback()
            api_internal_error()
        return e.serialize()

    @cherrypy.expose
    def endpoint_config(self, data):
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        e = roboger.endpoints.get_endpoint(data.get('endpoint_id'))
        if not e or (config.check_ownership and e.addr != addr):
            api_404('endpoint or wrong address')
        cfg = data.get('config')
        if not cfg:
            api_invalid_data('invalid config params')
        if isinstance(cfg, str):
            cfg = dict_from_str(cfg, spl='|')
        try:
            e.set_config(cfg)
        except:
            roboger.core.log_traceback()
            api_internal_error()
        return e.serialize()

    @cherrypy.expose
    def endpoint_skipdups(self, data):
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        e = roboger.endpoints.get_endpoint(data.get('endpoint_id'))
        if not e or (config.check_ownership and e.addr != addr):
            api_404('endpoint or wrong address')
        try:
            e.set_skip_dups(data.get('skip_time'))
        except:
            roboger.core.log_traceback()
            api_internal_error()
        return e.serialize()

    @cherrypy.expose
    def endpoint_description(self, data):
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        e = roboger.endpoints.get_endpoint(data.get('endpoint_id'))
        if not e or (config.check_ownership and e.addr != addr):
            api_404('endpoint or wrong address')
        try:
            e.set_description(data.get('description'))
        except:
            roboger.core.log_traceback()
            api_internal_error()
        return e.serialize()

    @cherrypy.expose
    def endpoint_enable(self, data):
        data['active'] = 1
        return self.endpoint_set_active(data)

    @cherrypy.expose
    def endpoint_disable(self, data):
        data['active'] = 0
        return self.endpoint_set_active(data)

    @cherrypy.expose
    def endpoint_set_active(self, data):
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        e = roboger.endpoints.get_endpoint(data.get('endpoint_id'))
        if not e or (config.check_ownership and e.addr != addr):
            api_404('endpoint or wrong address')
        try:
            _active = int(data['active'])
        except:
            _active = 1
        e.set_active(_active)
        return e.serialize()

    @cherrypy.expose
    def endpoint_delete(self, data):
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        e = roboger.endpoints.get_endpoint(data.get('endpoint_id'))
        if not e or (config.check_ownership and e.addr != addr):
            api_404('endpoint or wrong address')
        roboger.endpoints.destroy_endpoint(e)
        return api_result()

    @cherrypy.expose
    def subscription_create(self, data):
        e = roboger.endpoints.get_endpoint(data.get('endpoint_id'))
        if e and not config.check_ownership:
            addr = e.addr
        else:
            addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
            if addr is None:
                api_invalid_data('No such address')
        if not e or (config.check_ownership and \
                e.addr.addr_id != data.get('addr_id')):
            api_invalid_data('No such endpoint or wrong address')
        _lm = data.get('level_match')
        if _lm and _lm not in ['e', 'ge', 'le', 'g', 'l']:
            api_invalid_data('Invalid level match')
        if 'level_id' not in data:
            try:
                data['level_id'] = roboger.events.level_codes[str(
                    data['level'])[0].lower()]
            except:
                data['level_id'] = 20
        s = roboger.events.EventSubscription(
            addr,
            e,
            location=data.get('location'),
            keywords=data.get('keywords'),
            senders=data.get('senders'),
            level_id=data.get('level_id'),
            level_match=_lm,
            autosave=False)
        try:
            s.save()
        except:
            roboger.core.log_traceback()
            api_internal_error()
        roboger.events.append_subscription(s)
        return s.serialize()

    @cherrypy.expose
    def subscription_list(self, data):
        r = []
        if 'subscription_id' in data:
            s = roboger.events.get_subscription(data['subscription_id'])
            if not s:
                api_404('subscription or wrong address')
            e = s.endpoint
        else:
            e = roboger.endpoints.get_endpoint(data.get('endpoint_id'))
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if not e or (config.check_ownership and e.addr != addr):
            api_404('No such endpoint or wrong address')
        if 'subscription_id' in data:
            s = roboger.events.get_subscription(data['subscription_id'])
            e = s.endpoint
            if not s or (config.check_ownership and \
                    s.addr.addr_id != data.get('addr_id')):
                api_404('subscription or wrong address')
            return s.serialize()
        else:
            try:
                if e.endpoint_id in roboger.events.subscriptions_by_endpoint_id:
                    for i, s in roboger.events.subscriptions_by_endpoint_id[
                            e.endpoint_id].copy().items():
                        if not s._destroyed:
                            r.append(s.serialize())
            except:
                roboger.core.log_traceback()
                api_internal_error()
        return sorted(r, key=lambda k: k['id'])

    @cherrypy.expose
    def subscription_enable(self, data):
        data['active'] = 1
        return self.subscription_set_active(data)

    @cherrypy.expose
    def subscription_disable(self, data):
        data['active'] = 0
        return self.subscription_set_active(data)

    @cherrypy.expose
    def subscription_set_active(self, data):
        s = roboger.events.get_subscription(data.get('subscription_id'))
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if not s or (config.check_ownership and s.addr != addr):
            api_404('subscription or wrong address')
        try:
            _active = int(data['active'])
        except:
            _active = 1
        s.set_active(_active)
        return s.serialize()

    @cherrypy.expose
    def subscription_location(self, data):
        s = roboger.events.get_subscription(data.get('subscription_id'))
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if not s or (config.check_ownership and s.addr != addr):
            api_404('subscription or wrong address')
        s.set_location(data.get('location'))
        return s.serialize()

    @cherrypy.expose
    def subscription_keywords(self, data):
        s = roboger.events.get_subscription(data.get('subscription_id'))
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if not s or (config.check_ownership and s.addr != addr):
            api_404('subscription or wrong address')
        s.set_keywords(data.get('keywords'))
        return s.serialize()

    @cherrypy.expose
    def subscription_senders(self, data):
        s = roboger.events.get_subscription(data.get('subscription_id'))
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if not s or (config.check_ownership and s.addr != addr):
            api_404('subscription or wrong address')
        s.set_senders(data.get('senders'))
        return s.serialize()

    @cherrypy.expose
    def subscription_level(self, data):
        s = roboger.events.get_subscription(data.get('subscription_id'))
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if not s or (config.check_ownership and s.addr != addr):
            api_404('subscription or wrong address')
        _lm = data.get('level_match')
        if _lm and _lm not in ['e', 'ge', 'le', 'g', 'l']:
            api_invalid_data('Invalid level match')
        if 'level_id' not in data:
            try:
                data['level_id'] = roboger.events.level_codes[str(
                    data['level'])[0].lower()]
            except:
                data['level_id'] = 20
        s.set_level(data.get('level_id'), _lm)
        return s.serialize()

    @cherrypy.expose
    def subscription_delete(self, data):
        s = roboger.events.get_subscription(data.get('subscription_id'))
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if not s or (config.check_ownership and s.addr != addr):
            api_404('subscription or wrong address')
        roboger.events.destroy_subscription(s)
        return api_result()

    @cherrypy.expose
    def subscription_duplicate(self, data):
        s = roboger.events.get_subscription(data.get('subscription_id'))
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if not s or (config.check_ownership and s.addr != addr):
            api_404('subscription or wrong address')
        s_new = roboger.events.EventSubscription(
            s.addr,
            s.endpoint,
            active=s.active,
            location=s.location,
            keywords=s.keywords,
            senders=s.senders,
            level_id=s.level_id,
            level_match=s.level_match,
            autosave=False)
        try:
            s_new.save()
        except:
            roboger.core.log_traceback()
            api_internal_error()
        roboger.events.append_subscription(s_new)
        return s_new.serialize()

    @cherrypy.expose
    def endpoint_copysub(self, data):
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        e = roboger.endpoints.get_endpoint(data.get('endpoint_id'))
        et = roboger.endpoints.get_endpoint(data.get('endpoint_id_t'))
        if not e or (config.check_ownership and e.addr != addr):
            api_404('source endpoint or wrong address')
        if not et or (config.check_ownership and et.addr != addr):
            api_404('target endpoint or wrong address')
        if et.endpoint_id in roboger.events.subscriptions_by_endpoint_id:
            for i, s in roboger.events.subscriptions_by_endpoint_id[
                    et.endpoint_id].copy().items():
                roboger.events.destroy_subscription(s)
        for i, s in roboger.events.subscriptions_by_endpoint_id[
                e.endpoint_id].copy().items():
            s_new = roboger.events.EventSubscription(
                s.addr,
                et,
                active=s.active,
                location=s.location,
                keywords=s.keywords,
                senders=s.senders,
                level_id=s.level_id,
                level_match=s.level_match,
                autosave=False)
            try:
                s_new.save()
            except:
                roboger.core.log_traceback()
                api_internal_error()
            roboger.events.append_subscription(s_new)
        return api_result()

    @cherrypy.expose
    def event_list(self, data):
        if 'addr' in data or 'addr_id' in data:
            addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
            if not addr:
                api_404('address')
        else:
            addr = None
        try:
            limit = int(data['limit'])
        except:
            limit = None
        q = ('select id, addr_id, d, scheduled, delivered, location, ' +
             'keywords, sender, level_id, expires, subject, msg, media ' +
             'from event')
        if addr:
            q += ' where addr_id=:id'
        q += ' order by d desc'
        if limit:
            q += ' limit %u' % limit
        try:
            c = db().execute(sql(q), id=addr.addr_id if addr else None)
            result = []
            while True:
                r = c.fetchone()
                if r is None: break
                u = roboger.addr.get_addr(r.addr_id)
                if not u: continue
                e = roboger.events.Event(
                    addr=u,
                    event_id=r.id,
                    d=r.d,
                    scheduled=r.scheduled,
                    delivered=r.delivered,
                    location=r.location,
                    keywords=r.keywords,
                    sender=r.sender,
                    level_id=r.level_id,
                    expires=r.expires,
                    subject=r.subject,
                    msg=r.msg,
                    media=r.media)
                ev = e.serialize()
                ev['addr'] = u.a
                result.append(ev)
        except:
            roboger.core.log_traceback()
            api_internal_error()
        return sorted(result, key=lambda k: k['id'])


class PushAPI(object):

    _cp_config = {
        'tools.json_out.on': True,
        'tools.json_out.handler': cp_json_handler,
    }

    @cherrypy.expose
    def status(self):
        return {'result': 'OK'}

    @cherrypy.expose
    def push(self, r='', x='', n='', k='', l='', s='', e='', m='', a=''):
        _decode_a = False
        if r:
            d = {
                'addr': r,
                'sender': x,
                'location': n,
                'keywords': k,
                'subject': s,
                'expires': e,
                'msg': m,
                'level': l,
                'expires': e,
                'media': a
            }
            _decode_a = True
        else:
            cl = cherrypy.request.headers.get('Content-Length')
            if not cl:
                api_invalid_json_data()
            try:
                rawbody = cherrypy.request.body.read(int(cl))
                d = json.loads(rawbody.decode())
                _decode_a = True
            except:
                roboger.core.log_traceback()
                api_invalid_json_data()
        try:
            d['expires'] = int(d['expires'])
        except:
            d['expires'] = 86400
        try:
            d['level'] = roboger.events.level_codes[str(d['level'])[0].lower()]
        except:
            d['level'] = 20
        try:
            if len(d['msg']) > 4096:
                logging.debug('message too long (max is 4096 bytes)')
                d['msg'] = d['msg'][:4096]
        except:
            d['msg'] = ''
        try:
            if _decode_a and d['media']:
                try:
                    d['media'] = base64.b64decode(d['media'])
                except:
                    d['media'] = ''
            if d['media'] and len(d['media']) > 16777215:
                logging.debug('attached media too large, dropping')
                d['media'] = ''
        except:
            d['media'] = ''
        if d['addr'] is None:
            raise cherrypy.HTTPError('403 Forbidden', 'Address not specified')
        for x in ['sender', 'location', 'keywords', 'subject', 'media']:
            if x in d and d[x] is None: d[x] = ''
        result = roboger.events.push_event(
            d.get('addr', ''), d.get('level', 20), d.get('sender', ''),
            d.get('location', ''), d.get('keywords', ''), d.get('subject', ''),
            d.get('expires', ''), d.get('msg', ''), d.get('media', ''))
        if result is None:
            api_404('address')
        if result is False:
            api_internal_error()
        if result is True:
            return api_result()
        raise cherrypy.HTTPError('403 Forbidden',
                                 'Address is disabled: %u' % result)


default_port = 7719
default_ssl_port = 7720

config = SimpleNamespace(
    host=None,
    port=default_port,
    ssl_host=None,
    ssl_port=default_ssl_port,
    ssl_module='builtin',
    ssl_cert=None,
    ssl_key=None,
    ssl_chain=None,
    thread_pool=15,
    check_ownership=False,
    masterkey=None,
    master_allow=None)
