__author__ = "Altertech Group, http://www.altertech.com/"
__copyright__ = "Copyright (C) 2018 Altertech Group"
__license__ = "See https://www.roboger.com/"
__version__ = "1.0.0"

import cherrypy
import jsonpickle
import roboger.core
import roboger.events
import roboger.endpoints
import logging
import base64

from netaddr import IPNetwork

from roboger.core import format_json
from roboger import db

host = None
default_port = 7719
ssl_host = None
ssl_port = None
ssl_module = 'builtin'
ssl_cert = None
ssl_key = None
ssl_chain = None
thread_pool = 15

check_ownership = False

masterkey = None
master_allow = None


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


def check_db():
    try:
        if not roboger.db.check(cherrypy.thread_data.db):
            cherrypy.thread_data.db = roboger.db.connect()
    except:
        cherrypy.thread_data.db = roboger.db.connect()


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
        value, minimal=not roboger.core.development).encode('utf-8')


def update_config(cfg):
    global host, port, ssl_host, ssl_port
    global ssl_module, ssl_cert, ssl_key, ssl_chain
    global thread_pool, masterkey, master_allow, check_ownership
    try:
        host, port = roboger.core.parse_host_port(cfg.get('api', 'listen'))
        if not port:
            port = default_port
        logging.debug('api.listen = %s:%u' % (host, port))
    except:
        roboger.core.log_traceback()
        return False
    try:
        ssl_host, ssl_port = parse_host_port(cfg.get('api', 'ssl_listen'))
        if not ssl_port:
            ssl_port = default_ssl_port
        try:
            ssl_module = cfg.get('api', 'ssl_module')
        except:
            ssl_module = 'builtin'
        ssl_cert = cfg.get('api', 'ssl_cert')
        if ssl_cert[0] != '/': ssl_cert = roboger.core.dir_etc + '/' + ssl_cert
        ssl_key = cfg.get('api', 'ssl_key')
        if ssl_key[0] != '/': ssl_key = roboger.core.dir_etc + '/' + ssl_key
        logging.debug('api.ssl_listen = %s:%u' % (ssl_host, ssl_port))
        ssl_chain = cfg.get('api', 'ssl_chain')
        if ssl_chain[0] != '/':
            ssl_chain = roboger.core.dir_etc + '/' + ssl_chain
    except:
        pass
    try:
        thread_pool = int(cfg.get('api', 'thread_pool'))
    except:
        pass
    logging.debug('api.thread_pool = %u' % thread_pool)
    try:
        masterkey = cfg.get('api', 'masterkey')
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
        master_allow = [IPNetwork(h) for h in _hosts_allow]
    except:
        logging.error('roboger bad master host acl!')
        roboger.core.log_traceback()
        return None
    logging.debug('api.master_allow = %s' % \
            ', '.join([ str(h) for h in master_allow ]))
    try:
        check_ownership = (cfg.get('api', 'check_ownership') == 'yes')
    except:
        check_ownership = False
    logging.debug('api.check_ownership = %s' % check_ownership)
    return True


def start():
    if not host: return False
    cherrypy.tree.mount(PushAPI(), '/')
    cherrypy.tree.mount(MasterAPI(), '/manage')
    cherrypy.server.unsubscribe()
    logging.info('HTTP API listening at at %s:%s' % \
            (host, port))
    server1 = cherrypy._cpserver.Server()
    server1.socket_port = port
    server1._socket_host = host
    server1.thread_pool = thread_pool
    server1.subscribe()
    if ssl_host and ssl_module and ssl_cert and ssl_key:
        logging.info('HTTP API SSL listening at %s:%s' % \
                (ssl_host, ssl_port))
        server_ssl = cherrypy._cpserver.Server()
        server_ssl.socket_port = ssl_port
        server_ssl._socket_host = ssl_host
        server_ssl.thread_pool = thread_pool
        server_ssl.ssl_certificate = ssl_cert
        server_ssl.ssl_private_key = ssl_key
        if ssl_chain:
            server_ssl.ssl_certificate_chain = ssl_chain
        if ssl_module:
            server_ssl.ssl_module = ssl_module
        server_ssl.subscribe()
    if not roboger.core.development:
        cherrypy.config.update({'environment': 'production'})
        cherrypy.log.access_log.propagate = False
        cherrypy.log.error_log.propagate = False
    else:
        cherrypy.config.update({'global': {'engine.autoreload.on': False}})
    roboger.core.append_stop_func(stop)
    cherrypy.engine.start()


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
            'before_handler', self.cp_check_perm, priority=60)

    def cp_check_perm(self):
        if roboger.core.netacl_match(http_real_ip(), master_allow):
            if 'k' in cherrypy.serving.request.params:
                k = cherrypy.serving.request.params.get('k')
                if 'data' in cherrypy.serving.request.params:
                    try:
                        cherrypy.serving.request.params['data'] = \
                    jsonpickle.decode(cherrypy.serving.request.params['data'])
                    except:
                        api_invalid_json_data()
            else:
                try:
                    if 'data' in cherrypy.serving.request.params:
                        try:
                            d = \
                    jsonpickle.decode(cherrypy.serving.request.params['data'])
                        except:
                            api_invalid_json_data()
                    else:
                        cl = cl = cherrypy.request.headers['Content-Length']
                        rawbody = cherrypy.request.body.read(int(cl))
                        try:
                            d = jsonpickle.decode(rawbody.decode())
                        except:
                            api_invalid_json_data()
                    k = d.get('k')
                    cherrypy.serving.request.params['data'] = d
                except:
                    api_forbidden()
            if k == masterkey:
                check_db()
                return
        api_forbidden()

    @cherrypy.expose
    def test(self, data):
        d = {}
        d['version'] = roboger.core.version
        d['build'] = roboger.core.product_build
        return d

    @cherrypy.expose
    def ls_addr(self, data):
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
    def mk_addr(self, data):
        addr = roboger.addr.append_addr(dbconn=cherrypy.thread_data.db)
        return addr.serialize()

    @cherrypy.expose
    def ch_addr(self, data):
        addr = roboger.addr.change_addr(
            data.get('addr_id'),
            data.get('addr'),
            dbconn=cherrypy.thread_data.db)
        if not addr:
            api_404('address')
        return addr.serialize()

    @cherrypy.expose
    def set_addr_active(self, data):
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if not addr:
            api_404('address')
        try:
            _active = int(data['active'])
        except:
            _active = 1
        addr.set_active(_active, dbconn=cherrypy.thread_data.db)
        return addr.serialize()

    @cherrypy.expose
    def rm_addr(self, data):
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if not addr:
            api_404('address')
        addr.destroy(dbconn=cherrypy.thread_data.db)
        return api_result()

    @cherrypy.expose
    def ls_endpoint_types(self, data):
        r = []
        try:
            c = db.query('select id, name from endpoint_type order by id')
            while True:
                row = c.fetchone()
                if row is None: break
                r.append({'id': row[0], 'name': row[1]})
            c.close()
        except:
            roboger.core.log_traceback()
            api_internal_error()
        return sorted(r, key=lambda k: k['id'])

    @cherrypy.expose
    def ls_endpoints(self, data):
        r = []
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if 'endpoint_id' in data:
            e = roboger.endpoints.get_endpoint(data['endpoint_id'])
            if not e or (check_ownership and e.addr != addr):
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
    def mk_endpoint(self, data):
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if addr is None:
            api_invalid_data('No such address')
        endpoint_type = data.get('et')
        if not endpoint_type: api_invalid_data('Specify endpoint type')
        try:
            if endpoint_type == 2:
                e = roboger.endpoints.EmailEndpoint(
                    addr,
                    data.get('data'),
                    description=data.get('description'),
                    autosave=False)
            elif endpoint_type == 3:
                e = roboger.endpoints.HTTPPostEndpoint(
                    addr,
                    data.get('data'),
                    data.get('data3'),
                    description=data.get('description'),
                    autosave=False)
            elif endpoint_type == 4:
                e = roboger.endpoints.HTTPJSONEndpoint(
                    addr,
                    data.get('data'),
                    data.get('data3'),
                    description=data.get('description'),
                    autosave=False)
            elif endpoint_type == 100:
                e = roboger.endpoints.SlackEndpoint(
                    addr,
                    data.get('data'),
                    data.get('data2'),
                    description=data.get('description'),
                    autosave=False)
            elif endpoint_type == 101:
                e = roboger.endpoints.TelegramEndpoint(
                    addr,
                    data.get('data'),
                    description=data.get('description'),
                    autosave=False)
            else:
                e = None
        except:
            roboger.core.log_traceback()
            api_internal_error()
        if not e:
            api_invalid_data('No such endpoint type')
        try:
            e.save(dbconn=cherrypy.thread_data.db)
        except:
            roboger.core.log_traceback()
            api_internal_error()
        roboger.endpoints.append_endpoint(e)
        return e.serialize()

    @cherrypy.expose
    def set_endpoint_data(self, data):
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        e = roboger.endpoints.get_endpoint(data.get('endpoint_id'))
        if not e or (check_ownership and e.addr != addr):
            api_404('endpoint or wrong address')
        try:
            e.set_data(
                data['data'],
                data.get('data2'),
                data.get('data3'),
                dbconn=cherrypy.thread_data.db)
        except:
            roboger.core.log_traceback()
            api_internal_error()
        return e.serialize()

    @cherrypy.expose
    def set_endpoint_skip_dups(self, data):
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        e = roboger.endpoints.get_endpoint(data.get('endpoint_id'))
        if not e or (check_ownership and e.addr != addr):
            api_404('endpoint or wrong address')
        try:
            e.set_skip_dups(data.get('data'), dbconn=cherrypy.thread_data.db)
        except:
            roboger.core.log_traceback()
            api_internal_error()
        return e.serialize()

    @cherrypy.expose
    def set_endpoint_description(self, data):
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        e = roboger.endpoints.get_endpoint(data.get('endpoint_id'))
        if not e or (check_ownership and e.addr != addr):
            api_404('endpoint or wrong address')
        try:
            e.set_description(
                data.get('description'), dbconn=cherrypy.thread_data.db)
        except:
            roboger.core.log_traceback()
            api_internal_error()
        return e.serialize()

    @cherrypy.expose
    def set_endpoint_active(self, data):
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        e = roboger.endpoints.get_endpoint(data.get('endpoint_id'))
        if not e or (check_ownership and e.addr != addr):
            api_404('endpoint or wrong address')
        try:
            _active = int(data['active'])
        except:
            _active = 1
        e.set_active(_active, dbconn=cherrypy.thread_data.db)
        return e.serialize()

    @cherrypy.expose
    def rm_endpoint(self, data):
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        e = roboger.endpoints.get_endpoint(data.get('endpoint_id'))
        if not e or (check_ownership and e.addr != addr):
            api_404('endpoint or wrong address')
        roboger.endpoints.destroy_endpoint(e, dbconn=cherrypy.thread_data.db)
        return api_result()

    @cherrypy.expose
    def mk_subscription(self, data):
        e = roboger.endpoints.get_endpoint(data.get('endpoint_id'))
        if e and not check_ownership:
            addr = e.addr
        else:
            addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
            if addr is None:
                api_invalid_data('No such address')
        if not e or (check_ownership and \
                e.addr.addr_id != data.get('addr_id')):
            api_invalid_data('No such endpoint or wrong address')
        _lm = data.get('level_match')
        if _lm and _lm not in ['e', 'ge', 'le', 'g', 'l']:
            api_invalid_data('Invalid level match')
        if 'level_id' not in data:
            try:
                data['level_id'] = \
                        roboger.events.level_codes[
                                str(data['level'])[0].lower()]
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
            s.save(dbconn=cherrypy.thread_data.db)
        except:
            roboger.core.log_traceback()
            api_internal_error()
        roboger.events.append_subscription(s)
        return s.serialize()

    @cherrypy.expose
    def ls_subscriptions(self, data):
        r = []
        if 'subscription_id' in data:
            s = roboger.events.get_subscription(data['subscription_id'])
            if not s:
                api_invalid_data('No such subscription or wrong address')
            e = s.endpoint
        else:
            e = roboger.endpoints.get_endpoint(data.get('endpoint_id'))
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if not e or (check_ownership and e.addr != addr):
            api_invalid_data('No such endpoint or wrong address')
        if 'subscription_id' in data:
            s = roboger.events.get_subscription(data['subscription_id'])
            e = s.endpoint
            if not s or (check_ownership and \
                    s.addr.addr_id != data.get('addr_id')):
                api_404('subscription or wrong address')
            return s.serialize()
        else:
            try:
                if e.endpoint_id in \
                        roboger.events.subscriptions_by_endpoint_id:
                    for i, s in \
                            roboger.events.subscriptions_by_endpoint_id[
                                    e.endpoint_id].copy().items():
                        if not s._destroyed:
                            r.append(s.serialize())
            except:
                roboger.core.log_traceback()
                api_internal_error()
        return sorted(r, key=lambda k: k['id'])

    @cherrypy.expose
    def set_subscription_active(self, data):
        s = roboger.events.get_subscription(data.get('subscription_id'))
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if not s or (check_ownership and s.addr != addr):
            api_404('subscription or wrong address')
        try:
            _active = int(data['active'])
        except:
            _active = 1
        s.set_active(_active, dbconn=cherrypy.thread_data.db)
        return s.serialize()

    @cherrypy.expose
    def set_subscription_location(self, data):
        s = roboger.events.get_subscription(data.get('subscription_id'))
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if not s or (check_ownership and s.addr != addr):
            api_404('subscription or wrong address')
        s.set_location(data.get('location'), dbconn=cherrypy.thread_data.db)
        return s.serialize()

    @cherrypy.expose
    def set_subscription_keywords(self, data):
        s = roboger.events.get_subscription(data.get('subscription_id'))
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if not s or (check_ownership and s.addr != addr):
            api_404('subscription or wrong address')
        s.set_keywords(data.get('keywords'), dbconn=cherrypy.thread_data.db)
        return s.serialize()

    @cherrypy.expose
    def set_subscription_senders(self, data):
        s = roboger.events.get_subscription(data.get('subscription_id'))
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if not s or (check_ownership and s.addr != addr):
            api_404('subscription or wrong address')
        s.set_senders(data.get('senders'), dbconn=cherrypy.thread_data.db)
        return s.serialize()

    @cherrypy.expose
    def set_subscription_level(self, data):
        s = roboger.events.get_subscription(data.get('subscription_id'))
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if not s or (check_ownership and s.addr != addr):
            api_404('subscription or wrong address')
        _lm = data.get('level_match')
        if _lm and _lm not in ['e', 'ge', 'le', 'g', 'l']:
            api_invalid_data('Invalid level match')
        if 'level_id' not in data:
            try:
                data['level_id'] = \
                        roboger.events.level_codes[
                                str(data['level'])[0].lower()]
            except:
                data['level_id'] = 20
        s.set_level(data.get('level_id'), _lm, dbconn=cherrypy.thread_data.db)
        return s.serialize()

    @cherrypy.expose
    def rm_subscription(self, data):
        s = roboger.events.get_subscription(data.get('subscription_id'))
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if not s or (check_ownership and s.addr != addr):
            api_404('subscription or wrong address')
        roboger.events.destroy_subscription(s, dbconn=cherrypy.thread_data.db)
        return api_result()

    @cherrypy.expose
    def copy_subscription(self, data):
        s = roboger.events.get_subscription(data.get('subscription_id'))
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        if not s or (check_ownership and s.addr != addr):
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
            s_new.save(dbconn=cherrypy.thread_data.db)
        except:
            roboger.core.log_traceback()
            api_internal_error()
        roboger.events.append_subscription(s_new)
        return s_new.serialize()

    @cherrypy.expose
    def copy_endpoint_subscriptions(self, data):
        addr = roboger.addr.get_addr(data.get('addr_id'), data.get('addr'))
        e = roboger.endpoints.get_endpoint(data.get('endpoint_id'))
        et = roboger.endpoints.get_endpoint(data.get('endpoint_id_t'))
        if not e or (check_ownership and e.addr != addr):
            api_404('source endpoint or wrong address')
        if not et or (check_ownership and et.addr != addr):
            api_404('target endpoint or wrong address')
        if et.endpoint_id in \
                roboger.events.subscriptions_by_endpoint_id:
            for i, s in roboger.events.subscriptions_by_endpoint_id[
                    et.endpoint_id].copy().items():
                roboger.events.destroy_subscription(
                    s, dbconn=cherrypy.thread_data.db)
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
                s_new.save(dbconn=cherrypy.thread_data.db)
            except:
                roboger.core.log_traceback()
                api_internal_error()
            roboger.events.append_subscription(s_new)
        return api_result()

    @cherrypy.expose
    def ls_events(self, data):
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
        q = 'select id, addr_id, d, scheduled,' + \
            ' delivered, location, keywords, sender, level_id, expires,' + \
            'subject, msg, media from event'
        qp = ()
        if addr:
            q += ' where addr_id=%s'
            qp += (addr.addr_id,)
        q += ' order by d desc'
        if limit:
            q += ' limit %u' % limit
        try:
            c = roboger.db.query(q, qp, dbconn=cherrypy.thread_data.db)
            r = []
            while True:
                row = c.fetchone()
                if row is None: break
                u = roboger.addr.get_addr(row[1])
                if not u: continue
                e = roboger.events.Event(u, row[0], row[2], row[3], row[4],
                                         row[5], row[6], row[7], row[8], row[9],
                                         row[10], row[11], row[12])
                ev = e.serialize()
                ev['addr'] = u.a
                r.append(ev)
            c.close()
        except:
            roboger.core.log_traceback()
            api_internal_error()
        return sorted(r, key=lambda k: k['id'])


class PushAPI(object):

    _cp_config = {
        'tools.json_out.on': True,
        'tools.json_out.handler': cp_json_handler,
    }

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
                d = jsonpickle.decode(rawbody.decode())
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
        check_db()
        if d['addr'] is None:
            raise cherrypy.HTTPError('403 Forbidden',
                'Address not specified')
        for x in ['sender','location','keywords','subject','media']:
            if x in d and d[x] is None: d[x] = ''
        result = roboger.events.push_event(
            d.get('addr', ''),
            d.get('level', 20),
            d.get('sender', ''),
            d.get('location', ''),
            d.get('keywords', ''),
            d.get('subject', ''),
            d.get('expires', ''),
            d.get('msg', ''),
            d.get('media', ''),
            dbconn=cherrypy.thread_data.db)
        if result is None:
            api_404('address')
        if result is False:
            api_internal_error()
        if result is True:
            return api_result()
        raise cherrypy.HTTPError('403 Forbidden',
                                 'Address is disabled: %u' % result)
