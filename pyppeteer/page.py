import asyncio
import math
import base64
import mimetypes

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
    async def create(client, ignore_https_errors, screenshot_task_queue):
        await asyncio.gather(
            client.send('Network.enable', {}),
            client.send('Page.enable', {}),
            client.send('Runtime.enable', {}),
            client.send('Security.enable', {})
        )
        if ignore_https_errors:
            await client.send('Security.setOverrideCertificateErrors', {
                'override': True
            })
        page = Page(client, ignore_https_errors, screenshot_task_queue)
        await page.goto('about:blank')
        await page.set_viewport({'width': 800, 'height': 600})
        return page

    def __init__(
            self, client,
            ignore_https_errors=True,
            screenshot_task_queue=None):
        super().__init__()
        self._client = client
        self._keyborad = Keyboard(client)
        self._mouse = Mouse(client, self._keyborad)
        self._frame_manager = FrameManager(client, self._mouse)
        self._network_manager = NetworkManager(client)
        self._emulation_manager = EmulationManager(client)

        self._tracing = None

        self._page_bindings = {}
        self._ignore_https_errors = ignore_https_errors

        self._screenshot_task_queue = screenshot_task_queue

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
        #     'Runtime.consoleAPICalled',
        #     self._on_console_api
        # )
        # client.on(
        #     'Page.javascriptDialogOpening',
        #     self.on_dialog
        # )
        # client.on(
        #     'Runtime.exceptionThrown',
        #     self._handle_exception
        # )
        client.on(
            'Security.certificateError',
            self._on_certificate_error
        )
        client.on(
            'Inspector.targetCrashed',
            self._on_target_crashed
        )

    def _get_scope(self, responses):
        def _tmp(response):
            print('Resp cb----------')
            responses[response.url] = response
        return _tmp

    def _on_target_crashed(self):
        self.emit('error', Exception('Page crashed!'))

    def main_frame(self):
        return self._frame_manager.main_frame()

    @property
    def keyboard(self):
        return self._keyborad

    @property
    def tracing(self):
        return self._tracing

    def frames(self):
        return self._frame_manager.frames()

    async def set_request_interception_enabled(self, value):
        return await self._network_manager.set_request_interception_enabled(
            value)

    def _on_certificate_error(self, event):
        print(event)

    async def S(selector):
        return self.main_frame().S(selector)

    async def SS(selector):
        return self.main_frame().SS(selector)

    async def goto(self, url, options={}):
        watcher = NavigatorWatcher(
            self._client, self._ignore_https_errors, options)
        responses = {}

        listener = Helper.add_event_listener(
            self._network_manager,
            NetworkManager.Events['Response'],
            self._get_scope(responses)
        )
        result = watcher.wait_for_navigation()

        referrer = self._network_manager.extra_http_headers().get(
            'referer', '')
        try:
            await self._client.send('Page.navigate', {
                'url': url,
                'referrer': referrer
            })
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
        return await self.wait_for_navigation(options)

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
        fut = await watcher.wait_for_navigation()
        Helper.remove_event_listeners([listener])
        return responses.get(self.main_frame().url(), None)

    async def screenshot(self, options={}):
        screenshot_type = None
        print(options)
        if 'path' in options and options['path']:
            mime_type, enc = mimetypes.guess_type(options['path'])
            if mime_type == 'image/png':
                screenshot_type = 'png'
            elif mime_type == 'image/jpeg':
                screenshot_type = 'jpeg'
            assert screenshot_type
        if 'type' in options and options['type']:
            assert not screenshot_type or options['type'] == screenshot_type
            assert options['type'] in ['png', 'jpeg']
            screenshot_type = options['type']
        if not screenshot_type:
            screenshot_type = 'png'

        if 'quality' in options and options['quality']:
            assert screenshot_type == 'jpeg'
            assert isinstance(options['quality'], int)
            assert options['quality'] >= 0 and options['quality'] <= 100
        if 'clip' in options and options['clip']:
            assert isinstance(options['clip']['x'], (int, float))
            assert isinstance(options['clip']['y'], (int, float))
            assert isinstance(options['clip']['height'], (int, float))
            assert isinstance(options['clip']['width'], (int, float))
        # return await self._screenshot_task_queue.post_task(
        #     self._screenshot_task(
        #         screenshot_type,
        #         options
        #     )
        # )
        res = await self._screenshot_task(screenshot_type, options)
        return res

    async def _screenshot_task(self, _format, options={}):
        await self._client.send('Target.activateTarget', {
            'targetId': self._client.target_id()
        })
        clip = options['clip'] if 'clip' in options else None
        if clip:
            clip['scale'] = 1

        if 'fullPage' in options and options['fullPage']:
            metrics = await self._client.send('Page.getLayoutMetrics')
            width = math.ceil(metrics['contentSize']['width'])
            height = math.ceil(metrics['contentSize']['height'])

            clip = {
                'x': 0,
                'y': 0,
                'width': width,
                'height': height,
                'scale': 1
            }
            mobile = self._viewport['isMobile'] \
                if 'isMobile' in self._viewport else False
            device_scale_factor = self._viewport['deviceScaleFactor'] \
                if 'deviceScaleFactor' in self._viewport else 1
            landscape = self._viewport['isLandscape'] \
                if 'isLandscape' in self._viewport else False
            screen_orientation = {'angle': 90, 'type': 'landscapePrimary'} \
                if landscape else {'angle': 0, 'type': 'portraitPrimary'}
            await self._client.send('Emulation.setDeviceMetricsOverride', {
                'mobile': mobile,
                'width': width,
                'height': height,
                'deviceScaleFactor': device_scale_factor,
                'screenOrientation': screen_orientation
            })
        if 'omitBackground' in options and options['omitBackground']:
            await self._client.send(
                'Emulation.setDefaultBackgroundColorOverride', {
                    'color': {'r': 0, 'g': 0, 'b': 0, 'a': 0}
                }
            )
        screenshot_data = {
            'format': _format
        }
        if 'quality' in options:
            screenshot_data['quality'] = options['quality']
        if clip:
            screenshot_data['clip'] = clip
        result = await self._client.send(
            'Page.captureScreenshot', screenshot_data
        )
        print(result)
        if 'omitBackground' in options and options['omitBackground']:
            await self._client.send(
                'Emulation.setDefaultBackgroundColorOverride'
            )
        if 'fullPage' in options and options['fullPage']:
            await self.set_viewport(self._viewport)
        print(type(result['data']))
        buffr = base64.decodebytes(bytes(result['data'], 'utf-8'))
        if 'path' in options and options['path']:
            with open(options['path'], 'wb') as fl:
                fl.write(buffr)
        return buffr

    async def title(self):
        return await self.main_frame().title()

    @property
    def mouse(self):
        return self._mouse

    async def close(self):
        await self._client.dispose()
