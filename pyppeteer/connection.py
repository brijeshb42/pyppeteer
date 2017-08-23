import json
import asyncio

import websockets.client as wsclient
from websockets.exceptions import ConnectionClosed

from pyppeteer.emitter import EventEmitter
from pyppeteer.loop import loop as asyncio_loop


class Connection(EventEmitter):

    @staticmethod
    async def create(url, delay=0, loop=asyncio_loop):
        ws = await wsclient.connect(url)
        connection = Connection(url, ws, loop=loop)
        return connection

    def __init__(self, url, ws, delay=0, loop=None):
        super().__init__()
        self._url = url
        self._last_id = 0
        self._callbacks = {}
        self._loop = loop
        self._delay = delay/1000

        self._ws = ws
        self._sessions = {}

        ws_message_read_task = self._loop.create_task(self._add_listeners())

        def bye(task):
            pass
            # print(task)
            # print('Connection closed')
        ws_message_read_task.add_done_callback(bye)
        # loop.run_until_complete(ws_message_read_task)

    async def _add_listeners(self):
        while True:
            try:
                message = await self._ws.recv()
                await self.on_message(message)
            except ConnectionClosed:
                # print('Exit')
                await self.on_closed()
                break

    def url(self):
        return self._url

    def _future_cb(self, future):
        self

    async def send(self, method, params={}):
        self._last_id += 1
        _id = self._last_id
        message = json.dumps({'id': _id, 'method': method, 'params': params})
        # print('SEND ► ' + message)
        await self._ws.send(message)

        # self._callbacks[_id] = {'method': method}
        # message = await self._ws.recv()
        # res = await self.on_message(message)
        # return res
        # return asyncio.Task()
        future = asyncio.Future()
        self._callbacks[_id] = {'method': method, 'resolve': future}
        return await future

    def _resolve_future(self, future, result):
        # print('Future result - ', future, result)
        future.set_result(result)

    async def on_message(self, message):
        if self._delay:
            await asyncio.sleep(self._delay)
        print('◀ RECV ' + message)
        data = json.loads(message)
        if 'id' in data and data['id'] and data['id'] in self._callbacks:
            callback = self._callbacks[data['id']]
            del self._callbacks[data['id']]
            if 'error' in data:
                callback['resolve'].set_exception(
                    Exception(
                        'Protocol error ({}): {} {}'.format(
                            callback['method'],
                            data['error']['message'],
                            data['error']['data']
                        )
                    )
                )
                return callback['resolve']
            else:
                self._loop.call_soon(
                    self._resolve_future,
                    callback['resolve'],
                    data['result']
                )
                return callback['resolve']
        else:
            assert 'id' not in data or not data['id']
            # print('not id data')
            if data['method'] == 'Target.receivedMessageFromTarget':
                session = self._sessions.get(data['params']['sessionId'], None)
                if session:
                    return await session._on_message(data['params']['message'])
            elif data['method'] == 'Target.detachedFromTarget':
                session = self._sessions.get(data['params']['sessionId'], None)
                if session:
                    session.on_closed()
                    del self._sessions[data['params']['sessionId']]
            else:
                # print(data)
                self.emit(data['method'], data['params'])
                return None

    async def on_closed(self):
        # removeAllListeners
        for callback in self._callbacks.values():
            callback['resolve'].set_exception(
                Exception(
                    'Protocol error ({}): Target closed.'.format(
                        callback['method']))
            )
        self._callbacks.clear()
        for session in self._sessions.values():
            session.on_closed()
        self._sessions.clear()

    async def dispose(self):
        await self.on_closed()
        self._ws.close()

    async def create_session(self, target_id):
        data = await self.send(
            'Target.attachToTarget', {'targetId': target_id})
        # print('Data', data)
        session_id = data['sessionId']
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
            return asyncio.Future().set_exception(
                Exception((
                    'Protocol error ({}): Session closed.'
                    'Most likely the page has been closed.').format(
                        method
                    )
                )
            )
        self._last_id += 1
        _id = self._last_id
        message = json.dumps({'id': _id, 'method': method, 'params': params})
        # print('Session - SEND ► ' + message)
        res = await self._connection.send('Target.sendMessageToTarget', {
            'sessionId': self._session_id,
            'message': message
        })
        if hasattr(res, 'exception') and res.exception():
            if _id in self._callbacks:
                callback = self._callbacks[_id]
                del self._callbacks[_id]
                callback['resolve'].set_exception(res.exception())
                return await callback['resolve']
            else:
                return await res
        future = asyncio.Future()
        self._callbacks[_id] = {'method': method, 'resolve': future}
        return await future

    async def _on_message(self, message):
        # print('◀ RECV ' + message)
        data = json.loads(message)
        if 'id' in data and data['id'] and data['id'] in self._callbacks:
            callback = self._callbacks.get(data['id'])
            del self._callbacks[data['id']]
            if 'error' in data:
                callback['resolve'].set_exception(
                    Exception(
                        'Protocol error ({}): {} {}'.format(
                            callback['method'],
                            data['error']['message'],
                            data['error']['data']
                        )
                    )
                )
                return callback['resolve']
            else:
                callback['resolve'].set_result(data['result'])
                return callback['resolve']
        else:
            # assert 'id' in data or not data['id']
            if 'method' in data:
                self.emit(data['method'], data['params'])
            return asyncio.Future().set_result({})

    async def dispose(self):
        await self._connection.send(
            'Target.closeTarget', {'targetId': self._target_id})

    def on_closed(self):
        for callback in self._callbacks.values():
            callback['resolve'].set_exception(
                Exception(
                    'Protocol error ({}): Target closed.'.format(
                        callback['method']))
            )
        self._callbacks.clear()
        self._connection = None

if __name__ == '__main__':
    Connection.run()
