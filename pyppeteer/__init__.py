from pyppeteer.launcher import Launcher


async def launch(options={}):
    return await Launcher.launch(options)


async def connect(options={}):
    return await Launcher.connect(options)
