import os
import shutil
import sys
import subprocess
import random
import signal
import asyncio
import re

from pyppeteer.connection import Connection
from pyppeteer.browser import Browser
from pyppeteer.loop import loop as asyncio_loop

regex = r"^DevTools listening on (ws:\/\/.*)$"

CHROME_PROFILE_PATH = os.getcwd()
browser_id = 0

DEFAULT_ARGS = [
  '--disable-background-networking',
  '--disable-background-timer-throttling',
  '--disable-client-side-phishing-detection',
  '--disable-default-apps',
  '--disable-hang-monitor',
  '--disable-popup-blocking',
  '--disable-prompt-on-repost',
  '--disable-sync',
  '--enable-automation',
  '--metrics-recording-only',
  '--no-first-run',
  '--password-store=basic',
  '--remote-debugging-port=0',
  '--safebrowsing-disable-auto-update',
  '--use-mock-keychain',
]


def randbytes(n):
    for _ in range(n):
        yield random.getrandbits(8)


async def wait_for_ws_endpoint(chrome_process):
    while True:
        line = await chrome_process.stderr.readline()
        match = re.search(regex, line.decode('utf-8'))
        if match:
            return match.groups()[0]


class Launcher(object):

    @staticmethod
    async def launch(options={}, loop=asyncio_loop):
        global browser_id
        browser_id += 1
        user_data_dir = '-'.join((
            CHROME_PROFILE_PATH,
            str(os.getpid()),
            str(browser_id),
            str(bytearray(randbytes(4)).hex())
        ))
        chrome_arguments = list(DEFAULT_ARGS)
        chrome_arguments.append(
            '--user-data-dir={}'.format(user_data_dir)
        )
        chrome_executable = (
            '/Users/brijesh/projects/cms/frontend/'
            'node_modules/puppeteer/.local-chromium/'
            'mac-494755/chrome-mac/Chromium.app/Contents/'
            'MacOS/Chromium'
        )
        if 'headless' not in options or options['headless']:
            chrome_arguments.append('--headless')
            chrome_arguments.append('--disable-gpu')
            chrome_arguments.append('--hide-scrollbars')
            chrome_arguments.append('--mute-audio')
        if 'args' in options and isinstance(options['args'], (list, tuple)):
            chrome_arguments = chrome_arguments + options['args']
        # if 'executablePath' in options and \
        #     isinstance(options['executablePath'], (str, unicode)):
        # if 'dumpio' in options and options.dumpio:
        #     chrome_process = subprocess.Popen(
        #         [chrome_executable, *chrome_arguments],
        #         # stdin=sys.stdin,
        #         # stdout=sys.stdout,
        #         # stderr=sys.stderr,
        #         stdin=subprocess.PIPE,
        #         stdout=subprocess.PIPE,
        #         stderr=subprocess.PIPE,
        #         shell=True
        #     )
        # else:
        #     chrome_process = subprocess.Popen(
        #         [chrome_executable, *chrome_arguments],
        #         stderr=sys.stderr,
        #         shell=True
        #     )

        async def get_process(exe, args):
            process = await asyncio.create_subprocess_exec(
                *[exe, *args],
                stderr=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE
            )
            return process
        chrome_process = await get_process(chrome_executable, chrome_arguments)

        proc_list = [chrome_process]

        def chrome_kill():
            print('Killing chrome')
            proc_list[0].kill()
            shutil.rmtree(user_data_dir)

        signal.signal(signal.SIGTERM, chrome_kill)
        terminated = False

        browser_ws_endpoint = await wait_for_ws_endpoint(chrome_process)
        if not browser_ws_endpoint:
            chrome_process.kill()
            shutil.rmtree(user_data_dir)
            raise Exception('Failed to connect to chrome')

        connection_delay = options['sloMo'] if 'sloMo' in options else 0
        connection = await Connection.create(
            browser_ws_endpoint, connection_delay, loop=asyncio_loop
        )
        ignore_https_errors = True if (
            'ignoreHTTPSErrors' in options and options['ignoreHTTPSErrors']
            ) else False
        return Browser(connection, ignore_https_errors, chrome_kill)

    @staticmethod
    async def connect(browser_ws_endpoint, ignore_https_errors=False):
        connection = await Connection.create(browser_ws_endpoint)
        return Browser(connection, ignore_https_errors)
