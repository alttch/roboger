import requests
import logging

default_timeout = 10

logger = logging.getLogger('roboger')


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
        result = self._call('/core')
        del result['ok']
        return result

    def _call(self, resource, method='get', payload=None):
        uri = f'{self.__uri}{resource}'
        logger.debug(f'API call {method} {uri} {payload}')
        result = getattr(requests, method)(f'{uri}',
                                           headers=self.__headers,
                                           timeout=self.timeout,
                                           json=payload)
        if not result.ok:
            raise LookupError(result.text) if \
                    result.status_code == 404 else \
                    RuntimeError(f'API code: {result.status_code}')
        return result.json() if result.status_code not in (202, 204) else {}


class _RobogerObject:

    def __init__(self, **kwargs):

        def make_status_method(status_code):
            return lambda: self._set_active(status_code)

        for k, v in kwargs.items():
            if k == 'api':
                self._api = v
            elif k in self._property_fields:
                setattr(self, k, v)
            else:
                raise ValueError(f'Invalid parameter: {k}')
        for status, status_code in dict(disable=0, enable=1).items():
            setattr(self, status, make_status_method(status_code))

    def create(self):
        self.load(self._api.post(self._resource_class_uri()))

    def load(self, data=None):
        if not data:
            data = self._api.get(self._resource_uri())
        for k in self._property_fields:
            setattr(self, k, data[k])

    def save(self):
        self._api.patch(self._resource_uri(),
                        payload=self.serialize(include_protected_fields=False))

    def __iter__(self):
        for k, v in self.serialize().items():
            yield (k, v)

    def serialize(self, include_protected_fields=True):
        return {
            k: getattr(self, k)
            for k in self._property_fields
            if not (k.endswith('_id') or k == 'id' or
                    k in self._protected_fields) or include_protected_fields
        }

    def delete(self):
        self._api.delete(self._resource_uri())

    def cmd(self, **kwargs):
        return self._api.post(self._resource_uri(), payload=kwargs)

    def _set_active(self, status):
        if hasattr(self, 'active'):
            self.active = status
            self.save()
        else:
            raise AttributeError


class Addr(_RobogerObject):

    def __init__(self, **kwargs):
        self._property_fields = ['id', 'a', 'active', 'lim']
        self._protected_fields = ['a']
        self._resource_class_uri = lambda: '/addr'
        self._resource_uri = lambda: '/addr/{}'.format(self.id
                                                       if self.id else self.a)
        super().__init__(**kwargs)

    def change(self):
        result = super().cmd(cmd='change')
        self.a = result['a']
        return self.a
