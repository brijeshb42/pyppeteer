import json
import math

_api_coverage = None


class Helper(object):

    @staticmethod
    def evaluation_string(fun, *args):
        if Helper.is_string(fun):
            try:
                assert len(args) == 0
                return fun
            except AssertionError:
                raise AssertionError(
                    'Cannot evaluate a string with arguments')
        return '({})({})'.format(
            fun,
            ','.join([json.dumps(x) for x in args])
        )

    @staticmethod
    def get_exception_message(exception):
        return exception.message

    @staticmethod
    async def serialize_remote_object(client, remote_object):
        if 'unserializableValue' in remote_object:
            val = remote_object['unserializableValue']
            if val == '-0':
                return -0
            elif val == 'NaN':
                return math.nan
            elif val == 'Infinity':
                return math.inf
            elif val == '-Infinity':
                return -math.inf
            else:
                raise Exception(
                    'Unsupported unserializable value: {}'.format(val))
        if 'objectId' not in remote_object or not remote_object['objectId']:
            return remote_object['value']
        if remote_object['subtype'] == 'promise':
            return remote_object['description']
        try:
            response = await client.send('Runtime.callFunctionOn', {
                'objectId': remote_object['objectId'],
                'functionDeclaration': 'function() { return this; }',
                'returnByValue': True
            })
            return response['result']['value']
        except Exception as e:
            return remote_object['description']
        finally:
            Helper.release_object(client, remote_object)

    @staticmethod
    async def release_object(client, remote_object):
        if 'objectId' not in remote_object or not remote_object['objectId']:
            return
        try:
            await client.send('Runtime.releaseObject', {
                'objectId': remote_object['objectId']
            })
        except Exception:
            pass

    @staticmethod
    def trace_public_api(class_type):
        pass
        # Implement when necessary
        # print('Tracing API not implemented')

    @staticmethod
    def stringify_argument(arg):
        # Implement when necessary
        pass

    @staticmethod
    def add_event_listener(emitter, event_name, handler):
        emitter.on(event_name, handler)
        return {
            'emitter': emitter,
            'event_name': event_name,
            'handler': handler
        }

    @staticmethod
    def remove_event_listeners(listeners):
        for listener in listeners:
            listener['emitter'].remove_listener(
                listener['event_name'],
                listener['handler'])
        listeners = listeners[0:]

    @staticmethod
    def public_api_coverage():
        return _api_coverage

    @staticmethod
    def record_public_api_coverage():
        _api_coverage = {}

    @staticmethod
    def is_string(var):
        return isinstance(var, (str, unicode))

    @staticmethod
    def is_number(var):
        return isinstance(var, (int, long, float, complex))
