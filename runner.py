import pyppeteer
from pyppeteer.loop import loop


async def connect(url):
    browser = await pyppeteer.launch({
        'headless': False,
        'dumpio': True
    })
    print(browser)
    version = await browser.version()
    print(version)
    print('Getting Page')
    page = await browser.new_page()
    print('Got Page')
    print(page)
    # await page.set_viewport({'width': 1440, 'height': 900})
    await page.goto(url)
    # await page.setViewport({'width': 1440, 'height': 900})
    # await asyncio.sleep(5)
    await browser.close()


loop.run_until_complete(connect('https://scroll.in'))


# from pyppeteer.connection import Connection
# from pyppeteer.loop import loop

# ws = None

# async def connect():
#     global ws
#     ws = await Connection.create(
#         'ws://127.0.0.1:54074/devtools/browser'
#         '/892520a3-b3d0-4fe9-b99b-71e7b82f54d0')
#     # print(ws)


# async def open_url(url):
#     s = await ws.send('Target.createTarget', {'url': url})
#     # print(s)

# loop.run_until_complete(connect())
# loop.run_until_complete(open_url("http://scroll.in"))


# import asyncio
# import websockets
# from websockets.exceptions import ConnectionClosed
# from pyppeteer.emitter import EventEmitter

# loop = asyncio.get_event_loop()

# ev = EventEmitter()

# async def add_listeners(ws):
#     # print('Listening')
#     while True:
#         try:
#             message = await ws.recv()
#             ev.emit(message, message)
#         except ConnectionClosed:
#             # print('Exit')
#             break


# async def hello():
#     async with websockets.connect(
#             'wss://echo.websocket.org/?encoding=text') as websocket:
#         task = loop.create_task(add_listeners(websocket))
#         task.add_done_callback(lambda task: # print(task))

#         ev.on('h1', lambda msg: # print('Received h1 -> ', msg))
#         ev.on('h2', lambda msg: # print('Received h2 -> ', msg))
#         ev.on('h3', lambda msg: # print('Received h3 -> ', msg))
#         ev.on('h4', lambda msg: # print('Received h4 -> ', msg))
#         ev.on('h1', lambda msg: # print('Received h1 2nd -> ', msg))

#         await websocket.send('h1')
#         await websocket.send('h2')
#         await websocket.send('h3')
#         await websocket.send('h4')
#         await websocket.send('h1')

# loop.run_until_complete(hello())
