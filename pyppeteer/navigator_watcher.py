import asyncio

from pyppeteer.helper import Helper
from pyppeteer.loop import loop as asyncio_loop


class NavigatorWatcher(object):

    def __init__(
            self, client, ignore_https_errors,
            options={}, loop=asyncio_loop):
        self._client = client
        self._ignore_https_errors = ignore_https_errors
        self._timeout = 3
        self._loop = loop
        if 'timeout' in options and isinstance(options['timeout'], int):
            self._timeout = options['timeout']/1000
        self._idle_time = 1
        if 'networkIdleTimeout' in options and \
                isinstance(options['networkIdleTimeout'], int):
            self._idle_time = options['networkIdleTimeout']/1000
        self._idle_timer = None
        self._idle_inflight = 2
        if 'networkIdleInflight' in options and \
                isinstance(options['networkIdleInflight'], int):
            self._idle_inflight = options['networkIdleInflight']
        self._wait_until = 'load'
        if 'waitUntil' in options and \
                isinstance(options['waitUntil'], (str, unicode)):
            self._wait_until = options['waitUntil']
        assert self._wait_until == 'load' or self._wait_until == 'networkidle'

    def _watchdog_cb(self, future):
        if future.cancelled():
            return
        future.set_result(None)

    def _cert_error_cb(self, error):
        # print('SSL Certificate error: {}'.format(error['errorType']))
        if self._cert_future.cancelled():
            return
        self._cert_future.set_result(None)

    def _load_event_cb(self, *args, **kwargs):
        # print('Load event cb')
        # print(args, kwargs)
        # self._cert_future.set_result(None)
        pass

    def _network_idle_cb(self):
        pass

    async def wait_for_navigation(self):
        self._request_ids = set()
        self._event_listeners = []

        watchdog = asyncio.Future()
        self._maximum_timer = watchdog
        # await asyncio.sleep(self._timeout)
        self._loop.call_soon(self._watchdog_cb, watchdog)

        navigation_futures = [watchdog]

        if not self._ignore_https_errors:
            cert_error = asyncio.Future()
            self._cert_future = cert_error
            listener = Helper.add_event_listener(
                self._client,
                'Security.certificateError',
                self._cert_error_cb
            )
            self._event_listeners.append(listener)
            navigation_futures.append(cert_error)

        if self._wait_until == 'load':
            # print('Wait until load')
            load_event_fired = asyncio.Future()
            self._load_event_fired = load_event_fired
            listener = Helper.add_event_listener(
                self._client,
                'Page.loadEventFired',
                self._load_event_cb
            )
            self._event_listeners.append(listener)
            navigation_futures.append(load_event_fired)
        else:
            # print('Wait until else')
            self._event_listeners.extend((
                Helper.add_event_listener(
                    self._client,
                    'Network.requestWillBeSent',
                    self._on_loading_started
                ),
                Helper.add_event_listener(
                    self._client,
                    'Network.loadingFinished',
                    self._on_loading_completed
                ),
                Helper.add_event_listener(
                    self._client,
                    'Network.loadingFailed',
                    self._on_loading_completed
                ),
                Helper.add_event_listener(
                    self._client,
                    'Network.webSocketCreated',
                    self._on_loading_started
                ),
                Helper.add_event_listener(
                    self._client,
                    'Network.webSocketClosed',
                    self._on_loading_completed
                )
            ))
            network_idle = asyncio.Future()
            self._network_idle_future = network_idle
            navigation_futures.append(network_idle)
        try:
            res = self._add_nav_futures_to_loop(navigation_futures)
            await res
        except Exception as e:
            raise e
        finally:
            self._cleanup()

    def _add_nav_futures_to_loop(self, futures):
        # print('Add nav future list to loop')
        main_future = asyncio.Future()
        asyncio.async(
            self._start_nav_futures_loop(futures, main_future)
        )
        return main_future

    async def _start_nav_futures_loop(self, futures, main_future):
        # print('Started inf loop')
        while True:
            for future in futures:
                if future.done():
                    if future.exception():
                        main_future.set_exception(future.exception())
                    else:
                        main_future.set_result(future.result())
                    return main_future

    def cancel(self):
        self._cleanup()

    def _on_loading_started(self, event):
        self._request_ids.add(event['requestId'])
        if len(self._request_ids) > self._idle_inflight:
            if not self._idle_timer:
                self._idle_timer.cancel()
            self._idle_timer = None

    def _on_loading_completed(self, event):
        self._request_ids.remove(event['requestId'])
        if len(self._request_ids) <= self._idle_inflight and \
                not self._idle_timer:
            self._idle_timer = asyncio.Future()
            self._loop.call_later(self._idle_time, self._network_idle_cb)

    def _cleanup(self):
        Helper.remove_event_listeners(self._event_listeners)
        if self._idle_timer:
            self._idle_timer.cancel()
        if self._maximum_timer:
            self._maximum_timer.cancel()
