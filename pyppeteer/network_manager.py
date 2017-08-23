import urllib.parse as urlparse
import json

from pyppeteer.helper import Helper
from pyppeteer.multimap import Multimap
from pyppeteer.emitter import EventEmitter


def remove_url_hash(url):
    scheme, netloc, path, params, query, fragment = urlparse.urlparse(url)
    return urlparse.urlunparse((scheme, netloc, path, params, query, ''))


def generate_request_hash(request):
    _hash = {
        'url': request['url'],
        'method': request['method'],
        'postData': request['postData'],
        'headers': {}
    }
    headers = list(request['headers'].keys())
    headers.sort()
    for header in headers:
        if header in [
                'Accept',
                'Referer',
                'X-DevTools-Emulate-Network-Conditions-Client-Id']:
            continue
        _hash['headers'][header] = request['headers'][header]
    return json.dumps(_hash)


class Request(object):

    def __init__(self, client, request_id, interception_id, url, payload):
        self._client = client
        self._request_id = request_id
        self._interception_id = interception_id
        self._interception_handled = False
        self._response = None

        async def _complete_promise():
            response = await self._client.send('Network.getResponseBody', {
                'requestId': self._request_id
            })
            if 'base64Encoded' in response and response['base64Encoded']:
                import base64
                return base64.decodebytes(response['body'])
            return response['body']
        self._complete_promise = _complete_promise

        self.url = url
        self.method = payload['method']
        self.post_data = payload['postData']
        self.headers = payload['headers']

    def response(self):
        return self._response

    def continu(self, overrides={}):
        if self.url.startswith('data:'):
            return
        assert self._interception_id
        assert self._interception_handled
        self._interception_handled = True
        headers = None
        if 'headers' in overrides:
            headers = overrides['headers']
        has_post_data = 'postData' in overrides
        self._client.send('Network.continueInterceptedRequest', {
            'interceptionId': self._interception_id,
            'url': overrides['url'] if 'url' in overrides else None,
            'method': overrides['method'] if 'method' in overrides else None,
            'postData': overrides['postData'] if has_post_data else None,
            'headers': headers
        })

    def abort(self):
        if self.url.startswith('data:'):
            return
        assert self._interception_id
        assert self._interception_handled
        self._interception_handled = True
        self._client.send('Network.continueInterceptedRequest', {
            'interceptionId': self._interception_id,
            'errorReason': 'Failed'
        })


class Response(object):

    def __init__(self, client, request, status, headers):
        self._client = client
        self._request = request
        self._content_promise = None

        self.headers = headers
        self.status = status
        self.ok = status >= 200 and status < 300
        self.url = request.url

    async def buffer(self):
        if not self._content_promise:
            self._content_promise = await self._request._complete_promise()
        return self._content_promise

    async def text(self):
        content = await self.buffer()
        return str(content, 'utf-8')

    async def json(self):
        content = await self.text()
        return json.loads(content)

    def request(self):
        return self._request


class NetworkManager(EventEmitter):

    Events = {
        'Request': 'request',
        'Response': 'response',
        'RequestFailed': 'requestfailed',
        'RequestFinished': 'requestfinished',
    }

    def __init__(self, client):
        super().__init__()
        self._client = client
        self._request_id_to_request = {}
        self._interception_id_to_request = {}
        self._extra_http_headers = {}

        self._request_interception_enabled = False
        self._request_hash_to_request_ids = Multimap()
        self._request_hash_to_interceptions = Multimap()

        self._client.on(
            'Network.requestWillBeSent',
            self._on_request_will_be_sent)
        self._client.on(
            'Network.requestIntercepted',
            self._on_request_intercepted)
        self._client.on(
            'Network.responseReceived',
            self._on_response_received)
        self._client.on(
            'Network.loadingFinished',
            self._on_loading_finished)
        self._client.on(
            'Network.loadingFailed',
            self._on_loading_failed)

    async def set_extra_http_headers(self, extra_http_headers):
        self._extra_http_headers = extra_http_headers
        await self._client.send(
            'Network.setExtraHTTPHeaders', extra_http_headers)

    def extra_http_headers(self):
        return self._extra_http_headers

    async def set_user_agent(self, user_agent):
        return await self._client.send('Network.setUserAgentOverride', {
            'userAgent': user_agent
        })

    async def set_request_interception_enabled(self, value):
        await self._client.send('Network.setRequestInterceptionEnabled', {
            'enabled': not not value
        })
        self._request_interception_enabled = value

    def _on_request_intercepted(self, event):
        event['request']['url'] = remove_url_hash(event['request']['url'])

        if 'redirectStatusCode' in event and event['redirectStatusCode']:
            request = self._interception_id_to_request.get(
                event['interceptionId'], None)
            if not request:
                raise Exception(
                    'INTERNAL ERROR: failed to find '
                    'request for interception redirect.')
            self._handle_request_redirect(
                request,
                event['redirectStatusCode'],
                event['redirectHeaders'])
            self._handle_request_start(
                request['_requestId'],
                event['interceptionId'],
                event['redirectUrl'],
                event['request'])
            return
        request_hash = generate_request_hash(event['request'])
        self._request_hash_to_interceptions.set(request_hash, event)
        self._maybe_resolve_interception(request_hash)

    def _handle_request_redirect(
            self, request, redirect_status, redirect_headers):
        response = Response(
            self._client, request, redirect_status, redirect_headers)
        request['_response'] = response
        try:
            del self._request_id_to_request[request['_requestId']]
            del self._interception_id_to_request[request['_interceptionId']]
        except KeyError:
            pass
        self.emit(NetworkManager.Events['Response'], response)
        self.emit(NetworkManager.Events['RequestFinished'], request)

    def _handle_request_start(
            self, request_id, interception_id, url, request_payload):
        request = Request(
            self._client, request_id, interception_id, url, request_payload)
        self._request_id_to_request[request_id] = request
        self._interception_id_to_request[interception_id] = request
        self.emit(NetworkManager.Events['Request'], request)

    def _on_request_will_be_sent(self, event):
        if self._request_interception_enabled and \
                not event['request']['url'].startswith('data:'):
            if 'redirectResponse' in event and event['redirectResponse']:
                return
            request_hash = generate_request_hash(event['request'])
            self._request_hash_to_request_ids.set(
                request_hash, event['requestId'])
            self._maybe_resolve_interception(request_hash)
            return
        if 'redirectResponse' in event and event['redirectResponse']:
            request = self._request_id_to_request.get(event['requestId'])
            self._handle_request_redirect(
                request,
                event['redirectResponse']['status'],
                event['redirectResponse']['headers'])
        self._handle_request_start(
            event['requestId'],
            None,
            event['request']['url'],
            event['request'])

    def _maybe_resolve_interception(self, request_hash):
        request_id = self._request_hash_to_request_ids.first_value(
            request_hash)
        interception = self._request_hash_to_interceptions.first_value(
            request_hash)
        if not request_id or not interception:
            return
        self._request_hash_to_request_ids.delete(request_hash, request_id)
        self._request_hash_to_interceptions.delete(request_hash, interception)
        self._handle_request_start(
            request_id,
            interception['interceptionId'],
            interception['request']['url'],
            interception['request'])

    def _on_response_received(self, event):
        request = self._request_id_to_request.get(event['requestId'], None)
        if not request:
            return
        response = Response(
            self._client, request,
            event['response']['status'],
            event['response']['headers'])
        request['_reponse'] = response
        self.emit(NetworkManager.Events['Response'], response)

    async def _on_loading_finished(self, event):
        request = self._request_id_to_request.get(event['requestId'], None)
        if not request:
            return
        await request._complete_promise()
        try:
            del self._request_id_to_request[event['requestId']]
            del self._interception_id_to_request[event['interceptionId']]
        except KeyError:
            pass
        self.emit(NetworkManager.Events['RequestFinished'], request)

    async def _on_loading_failed(self, event):
        request = self._request_id_to_request.get(event['requestId'], None)
        if not request:
            return
        await request._complete_promise()
        try:
            del self._request_id_to_request[event['requestId']]
            del self._interception_id_to_request[event['interceptionId']]
        except KeyError:
            pass
        self.emit(NetworkManager.Events['RequestFailed'], request)
