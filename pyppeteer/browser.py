import asyncio
from pyppeteer.page import Page


class TaskQueue(object):

    def __init__(self):
        self.chain = asyncio.Queue()
        # asyncio.async(self._start_consumer())

    async def _start_consumer(self):
        print('Started ss tq')
        while True:
            future = await self.chain.get()
            await future

    async def post_task(self, task):
        print(task)
        await self.chain.put(task)


class Browser(object):

    def __init__(self, connection, ignore_https_errors, close_cb):
        self._ignore_https_errors = ignore_https_errors
        self._screenshot_task_queue = TaskQueue()
        self._connection = connection

        def cb():
            pass
        self._close_cb = close_cb or cb

    def ws_endpoint(self):
        return self._connection.url()

    async def new_page(self):
        result = await self._connection.send('Target.createTarget', {
            'url': 'about:blank'
        })
        client = await self._connection.create_session(result['targetId'])
        return await Page.create(
            client, self._ignore_https_errors,
            self._screenshot_task_queue
        )

    async def version(self):
        version = await self._connection.send('Browser.getVersion')
        return version['product']

    async def close(self):
        self._connection.dispose()
        self._close_cb()
