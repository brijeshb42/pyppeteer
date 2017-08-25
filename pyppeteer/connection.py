import asyncio
import json

import websockets.client as wsclient
from websockets.exceptions import ConnectionClosed

from pyppeteer.emitter import EventEmitter
from pyppeteer.loop import loop as asyncio_loop


class Connection(EventEmitter):

    @staticmethod
    async def create(url, delay=0, loop=asyncio_loop):
        future = asyncio.Future()
        try:
            ws = await wsclient.connect(url)
            future.set_result(Connection(url, ws, delay, loop=loop))
        except Exception as e:
            future.set_exception(e)
        return await future

    def __init__(self, url, ws, delay=0, loop=asyncio_loop):
        super().__init__()
        self._url = url
        self._last_id = 0
        self._callbacks = {}
        self._delay = delay/1000
        self._ws = ws
        self._sessions = {}
        self._loop = loop

        asyncio.async(self._listen_for_msg())
        # print('Got it')

    async def _listen_for_msg(self):
        while True:
            try:
                message = await self._ws.recv()
            except ConnectionClosed:
                await self._on_message(message)
                break
            if message is None:
                self._on_closed()
                break
            await self._on_message(message)

    def url(self):
        return self._url

    async def send(self, method, params={}):
        self._last_id += 1
        _id = self._last_id
        message = json.dumps({
            'id': _id,
            'method': method,
            'params': params
        })
        # print('SEND ►', message)
        await self._ws.send(message)
        future = asyncio.Future()
        self._callbacks[_id] = {
            'method': method,
            'resolve': future
        }
        return await future

    async def _on_message(self, message):
        if self._delay:
            await asyncio.sleep(self._delay)
        # print('◀ RECV', message)
        data = json.loads(message)
        if 'id' in data and data['id'] and data['id'] in self._callbacks:
            callback = self._callbacks[data['id']]
            future = callback['resolve']
            del self._callbacks[data['id']]
            if 'error' in data:
                future.set_exception(
                    Exception('Protocol error: {}'.format(callback['method']))
                )
            else:
                future.set_result(data['result'])
            # return future
        else:
            if 'id' in data:
                assert not data['id']
            method = data['method'] if 'method' in data else ''
            if method == 'Target.receivedMessageFromTarget':
                session = self._sessions.get(data['params']['sessionId'], None)
                if session:
                    session._on_message(data['params']['message'])
            elif method == 'Target.detachedFromTarget':
                session = self._sessions.get(data['params']['sessionId'], None)
                if session:
                    session._on_closed()
                del self._sessions[data['params']['sessionId']]
            else:
                # print('---------Emitting------------{}'.format(data['method']))
                self.emit(data['method'], data['params'])

    def _on_closed(self):
        for key in self._callbacks:
            cb = self._callbacks[key]
            future = cb['resolve']
            future.set_exception(
                Exception('Protocol error ({}): Target closed.'.format(
                    cb['method']
                ))
            )
        self._callbacks.clear()
        for session in self._sessions.values():
            session._on_closed()
        self._sessions.clear()

    def dispose(self):
        self._on_closed()
        self._ws.close()

    async def create_session(self, target_id):
        res = await self.send('Target.attachToTarget', {
            'targetId': target_id
        })
        session_id = res['sessionId']
        session = Session(self, target_id, session_id)
        self._sessions[session_id] = session
        return session


class Session(EventEmitter):

    def __init__(self, connection, target_id, session_id):
        super().__init__()
        self._last_id = 0
        self._callbacks = {}
        self._connection = connection
        self._target_id = target_id
        self._session_id = session_id

    def target_id(self):
        return self._target_id

    async def send(self, method, params={}):
        if not self._connection:
            future = asyncio.Future()
            future.set_exception(Exception(
                'Protocol error ({}): Session closed'
                '. Most likely the page has been closed.'.format(method)
            ))
            return await future
        self._last_id += 1
        _id = self._last_id
        message = json.dumps({
            'id': _id,
            'method': method,
            'params': params
        })
        # print('Debug Session: SEND ► ', message)
        future = asyncio.Future()
        self._callbacks[_id] = {
            'method': method,
            'resolve': future
        }
        try:
            res = await self._connection.send('Target.sendMessageToTarget', {
                'sessionId': self._session_id,
                'message': message
            })
        except Exception as e:
            if _id in self._callbacks:
                callback = self._callbacks[_id]
                del self._callbacks[_id]
                fut = callback['resolve']
                fut.set_exception(e)
        return await future

    def _on_message(self, message):
        # print('Debug Session: ◀ RECV ', message)
        data = json.loads(message)
        if 'id' in data and data['id'] in self._callbacks:
            # print('id {} in data'.format(data['id']))
            callback = self._callbacks[data['id']]
            future = callback['resolve']
            del self._callbacks[data['id']]
            if 'error' in data:
                future.set_exception(Exception(
                    'Protocol error ({}): {} {}'.format(
                        callback['method'],
                        data['error']['message'],
                        data['error']['data']
                    )
                ))
            else:
                future.set_result(data['result'])
        else:
            if 'method' in data:
                self.emit(data['method'], data['params'])

    async def dispose(self):
        await self._connection.send('Target.closeTarget', {
            'targetId': self._target_id
        })

    def _on_closed(self):
        for callback in self._callbacks.values():
            callback['resolve'].set_exception(
                Exception(
                    'Protocol error ({}): Target closed.'.format(
                        callback['method'])
                )
            )
        self._callbacks.clear()
        self._connection = None
