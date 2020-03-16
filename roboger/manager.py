import requests
import logging

from types import SimpleNamespace

default_timeout = 10

logger = logging.getLogger('roboger')

use_limits = False

default_api = None


class ManagementAPI:

    def __init__(self, api_uri, api_key, api_version=2,
                 timeout=default_timeout):

        def make_api_method(method):
            return lambda resource, payload=None: self._call(
                resource, method, payload)

        self.__headers = {'X-Auth-Key': api_key, 'Accept': '*/*'}
        self.timeout = timeout
        self.__uri = f'{api_uri}/manage/v{api_version}'
        for method in ['get', 'post', 'patch', 'delete']:
            setattr(self, method, make_api_method(method))

    def test(self):
        result = self.get('/core')
        del result['ok']
        return result

    def reset_addr_limits(self):
        self.post('/core', payload={'cmd': 'reset-addr-limits'})

    def delete_everything(self, confirm=None):
        if confirm == 'YES':
            self.post('/core', payload={'cmd': 'delete-everything'})
        else:
            raise RuntimeError("""not confirm='YES', aborted""")

    def _call(self, resource, method='get', payload=None):
        uri = f'{self.__uri}{resource}'
        logger.debug(f'API call {method} {uri} {payload}')
        result = getattr(requests, method)(f'{uri}',
                                           headers=self.__headers,
                                           timeout=self.timeout,
                                           json=payload)
        if not result.ok:
            if result.status_code == 400:
                raise ValueError(result.text)
            elif result.status_code == 404:
                raise LookupError(result.text)
            elif result.status_code == 403:
                raise RuntimeError('forbidden')
            elif result.status_code == 409:
                raise RuntimeError(result.text)
            else:
                raise RuntimeError(f'API code: {result.status_code}')
        return result.json() if result.status_code not in (202, 204) else {}


class _RobogerObject:

    def __init__(self, **kwargs):

        def make_status_method(status_code):
            return lambda: self._set_active(status_code)

        for k, v in kwargs.items():
            if k == 'api':
                self._api = v
            elif k in self._property_fields:
                if k == 'id':
                    try:
                        v = int(v)
                    except:
                        pass
                setattr(self, k, v)
            else:
                raise ValueError(f'Invalid parameter: {k}')
        if not hasattr(self, '_api'):
            self._api = default_api
        for status, status_code in dict(disable=0, enable=1).items():
            setattr(self, status, make_status_method(status_code))

    def create(self, payload=None):
        self.load(
            self._api.post(
                self._resource_class_uri(),
                payload={
                    k: getattr(self, k, None) for k in self._creation_fields
                }))

    def load(self, data=None, load_protected_fields=True):
        if data:
            for k, v in data.items():
                if load_protected_fields or k not in self._protected_fields:
                    if k == 'id':
                        try:
                            v = int(v)
                        except:
                            pass
                    setattr(self, k, v)
        else:
            data = self._api.get(self._resource_uri())
            for k in self._property_fields:
                if k == 'id':
                    try:
                        v = int(data[k])
                    except:
                        v = data[k]
                else:
                    v = data[k]
                setattr(self, k, v)

    def save(self):
        self._api.patch(self._resource_uri(),
                        payload=self.serialize(include_protected_fields=False))

    def __iter__(self):
        for k, v in self.serialize().items():
            yield (k, v)

    def serialize(self, include_protected_fields=True):
        return {
            k: getattr(self, k, None)
            for k in self._property_fields
            if include_protected_fields or
            not (k == 'id' or k in self._protected_fields)
        }

    def delete(self):
        self._api.delete(self._resource_uri())

    def cmd(self, **kwargs):
        return self._api.post(self._resource_uri(), payload=kwargs)

    def _set_active(self, status):
        if 'active' in self._property_fields:
            self.active = status
            self._api.patch(self._resource_uri(),
                            payload={'active': self.active})
        else:
            raise AttributeError


class Addr(_RobogerObject):

    def __init__(self, **kwargs):
        self._property_fields = ['id', 'a', 'active']
        if use_limits:
            self._property_fields.append('lim_c')
            self._property_fields.append('lim_s')
        self._protected_fields = ['a']
        self._creation_fields = []
        self._resource_class_uri = lambda: '/addr'
        self._resource_uri = lambda: '/addr/{}'.format(self.id
                                                       if self.id else self.a)
        super().__init__(**kwargs)

    def change(self, to=None):
        result = super().cmd(cmd='change', to=to)
        self.a = result['a']
        return self.a

    def list_endpoints(self):
        return [
            Endpoint(api=self._api, **ep)
            for ep in self._api.get(f'{self._resource_uri()}/endpoint')
        ]

    def create_endpoint(self, plugin_name, config={}, **kwargs):
        ep = Endpoint(addr_id=self.id,
                      plugin_name=plugin_name,
                      config=config,
                      api=self._api,
                      **kwargs)
        ep.create()
        return ep


class Endpoint(_RobogerObject):

    def __init__(self, **kwargs):
        self._property_fields = [
            'id', 'addr_id', 'plugin_name', 'config', 'active', 'description'
        ]
        self._protected_fields = ['plugin_name', 'addr_id']
        self._creation_fields = ['plugin_name', 'config', 'description']
        self._resource_class_uri = lambda: f'/addr/{self.addr_id}/endpoint'
        self._resource_uri = lambda: f'/addr/{self.addr_id}/endpoint/{self.id}'
        super().__init__(**kwargs)

    def copysub(self, target, replace=False):
        super().cmd(cmd='copysub',
                    target=target if isinstance(target, int) else target.id,
                    replace=replace)

    def list_subscriptions(self):
        return [
            Subscription(**s)
            for s in self._api.get(f'{self._resource_uri()}/subscription')
        ]

    def create_subscription(self, **kwargs):
        s = Subscription(endpoint_id=self.id,
                         addr_id=self.addr_id,
                         api=self._api,
                         **kwargs)
        s.create()
        return s


class Subscription(_RobogerObject):

    def __init__(self, **kwargs):
        self._property_fields = [
            'id', 'addr_id', 'endpoint_id', 'location', 'tag', 'sender',
            'level', 'level_match', 'active'
        ]
        self._protected_fields = ['id', 'addr_id', 'endpoint_id']
        self._creation_fields = [
            'location', 'tag', 'sender', 'level', 'level_match'
        ]
        self._resource_class_uri = lambda: (f'/addr/{self.addr_id}/endpoint/'
                                            f'{self.endpoint_id}/subscription')
        self._resource_uri = lambda: (
            f'/addr/{self.addr_id}/endpoint/'
            f'{self.endpoint_id}/subscription/{self.id}')
        super().__init__(**kwargs)


def create_addr(api=None):
    addr = Addr(api=api if api else default_api)
    addr.create()
    return addr


def list_addr(api=None):
    api = api if api else default_api
    return api.get('/addr')


def reset_addr_limits(api=None):
    api = api if api else default_api
    return api.reset_addr_limits()


def delete_everything(api=None, confirm=None):
    api = api if api else default_api
    return api.delete_everything(confirm=confirm)
