from pyppeteer.emitter import EventEmitter
from pyppeteer.helper import Helper
from pyppeteer.input import Keyboard, Mouse
from pyppeteer.frame_manager import FrameManager
from pyppeteer.network_manager import NetworkManager
from pyppeteer.navigator_watcher import NavigatorWatcher
from pyppeteer.emulation_manager import EmulationManager


class Page(EventEmitter):

    Events = {
        'Console': 'console',
        'Dialog': 'dialog',
        'Error': 'error',
        'PageError': 'pageerror',
        'Request': 'request',
        'Response': 'response',
        'RequestFailed': 'requestfailed',
        'RequestFinished': 'requestfinished',
        'FrameAttached': 'frameattached',
        'FrameDetached': 'framedetached',
        'FrameNavigated': 'framenavigated',
        'Load': 'load',
    }

    @staticmethod
    async def create(client, ignore_https_errors):
        print('Page.create init')
        await client.send('Network.enable', {})
        print('Page.create Network enable')
        await client.send('Page.enable', {})
        print('Page.create Page enable')
        await client.send('Runtime.enable', {})
        print('Page.create Runtime enable')
        # await client.send('Security.enable', {})
        print('Page.create Security enable')
        if ignore_https_errors:
            await client.send('Security.setOverrideCertificateErrors', {
                'override': True
            })
        print('Page.create')
        page = Page(client, ignore_https_errors)
        await page.goto('about:blank')
        print(page)
        await page.set_viewport({'width': 800, 'height': 600})
        return page

    def __init__(self, client, ignore_https_errors=True):
        super().__init__()
        self._client = client
        self._keyborad = Keyboard(client)
        self._mouse = Mouse(client, self._keyborad)
        self._frame_manager = FrameManager(client, self._mouse)
        self._network_manager = NetworkManager(client)
        self._emulation_manager = EmulationManager(client)

        self._page_bindings = {}
        self._ignore_https_errors = ignore_https_errors

        self._frame_manager.on(
            FrameManager.Events['FrameAttached'],
            lambda ev: self.emit(Page.Events['FrameAttached'], ev)
        )
        self._frame_manager.on(
            FrameManager.Events['FrameDetached'],
            lambda ev: self.emit(Page.Events['FrameDetached'], ev)
        )
        self._frame_manager.on(
            FrameManager.Events['FrameNavigated'],
            lambda ev: self.emit(Page.Events['FrameNavigated'], ev)
        )

        self._network_manager.on(
            NetworkManager.Events['Request'],
            lambda ev: self.emit(Page.Events['Request'], ev)
        )
        self._network_manager.on(
            NetworkManager.Events['Response'],
            lambda ev: self.emit(Page.Events['Response'], ev)
        )
        self._network_manager.on(
            NetworkManager.Events['RequestFailed'],
            lambda ev: self.emit(Page.Events['RequestFailed'], ev)
        )
        self._network_manager.on(
            NetworkManager.Events['RequestFinished'],
            lambda ev: self.emit(Page.Events['RequestFinished'], ev)
        )

        client.on(
            'Page.loadEventFired',
            lambda event: self.emit(Page.Events['Load'])
        )
        # client.on(
        #     'Runtime.consoleAPICalled', event => this._onConsoleAPI(event));
        # client.on(
        #     'Page.javascriptDialogOpening', event => this._onDialog(event));
        # client.on(
        #     'Runtime.exceptionThrown', exception => this._handleException(exception.exceptionDetails));
        # client.on(
        #     'Security.certificateError', event => this._onCertificateError(event));
        # client.on(
        #     'Inspector.targetCrashed', event => this._onTargetCrashed());

    def main_frame(self):
        return self._frame_manager.main_frame()

    async def goto(self, url, options={}):
        print('goto')
        watcher = NavigatorWatcher(
            self._client, self._ignore_https_errors, options)
        responses = {}

        def set_resp(response):
            print(response)
            global responses
            responses[response['url']] = response
        listener = Helper.add_event_listener(
            self._network_manager,
            NetworkManager.Events['Response'],
            set_resp
        )
        result = watcher.wait_for_navigation()
        print(result)

        referrer = self._network_manager.extra_http_headers().get(
            'referer', '')
        try:
            print('Sending navigate')
            res = await self._client.send('Page.navigate', {
                'url': url,
                'referrer': referrer
            })
            print('Done navigate', res)
        except Exception as e:
            watcher.cancel()
            raise e
        await result
        Helper.remove_event_listeners([listener])
        if self._frame_manager.is_main_frame_loading_failed():
            raise Exception('Failed to navigate: {}'.format(url))
        return responses.get(self.main_frame().url(), None)

    async def set_viewport(self, viewport={}):
        needs_reload = await self._emulation_manager.emulate_viewport(
            self._client, viewport)
        self._viewport = viewport
        if needs_reload:
            await self.reload()

    def viewport():
        return self._viewport

    async def reload(options):
        await self._client.send('Page.reload')
        return self.wait_for_navigation(options)

    async def wait_for_navigation(self, options):
        watcher = NavigatorWatcher(
            self._client, self.ignore_https_errors, options)
        responses = {}

        def set_resp(response):
            global responses
            responses[response['url']] = response
        listener = Helper.add_event_listener(
            self._network_manager,
            NetworkManager.Events['Response'],
            set_resp
        )
        await watcher.wait_for_naviagtion()
        Helper.remove_event_listeners([listener])
        return responses.get(self.main_frame().url(), None)

    async def title(self):
        return await self.main_frame().title()

    @property
    def mouse(self):
        return self._mouse

    async def close(self):
        await self._client.dispose()
