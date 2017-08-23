from pyppeteer.page import Page


class Browser(object):

    def __init__(self, connection, ignore_https_errors, close_cb):
        self._ignore_https_errors = ignore_https_errors
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
        return await Page.create(client, self._ignore_https_errors)

    async def version(self):
        version = await self._connection.send('Browser.getVersion')
        return version['product']

    async def close(self):
        await self._connection.dispose()
        self._close_cb()
