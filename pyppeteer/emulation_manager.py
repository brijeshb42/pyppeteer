source = '''
function injectedTouchEventsFunction() {
    const touchEvents = ['ontouchstart', 'ontouchend', 'ontouchmove', 'ontouchcancel'];
    const recepients = [window.__proto__, document.__proto__];
    for (let i = 0; i < touchEvents.length; ++i) {
        for (let j = 0; j < recepients.length; ++j) {
          if (!(touchEvents[i] in recepients[j])) {
            Object.defineProperty(recepients[j], touchEvents[i], {
              value: null, writable: true, configurable: true, enumerable: true
            });
          }
        }
    }
    }
'''


class EmulationManager(object):

    def __init__(self, client):
        self._client = client
        self._emulating_mobile = False
        self._injected_touch_script_id = None

    async def emulate_viewport(self, client, viewport={}):
        viewport = {**{
            'isMobile': False,
            'deviceScaleFactor': 1,
            'isLandscape': True,
            'hasTouch': False
        }, **viewport}
        if 'isLandscape' in viewport and viewport['isLandscape']:
            screen_orientation = {'angle': 90, 'type': 'landscapePrimary'}
        else:
            screen_orientation = {'angle': 0, 'type': 'portraitPrimary'}

        await self._client.send('Emulation.setDeviceMetricsOverride', {
            'mobile': viewport['isMobile'],
            'width': viewport['width'],
            'height': viewport['height'],
            'deviceScaleFactor': viewport['deviceScaleFactor'],
            'screenOrientation': screen_orientation
        })
        await self._client.send('Emulation.setTouchEmulationEnabled', {
            'enabled': viewport['hasTouch'],
            'configuration': 'mobile' if viewport['isMobile'] else 'desktop'
        })

        reload_needed = False
        if viewport['hasTouch'] and not self._injected_touch_script_id:
            _source = '({})()'.format(source)
            res = await self._client.send(
                'Page.addScriptToEvaluateOnNewDocument', {
                    'source': _source
                }
            )
            self._injected_touch_script_id = res['identifier']
            reload_needed = True
        elif not viewport['hasTouch'] and self._injected_touch_script_id:
            await self._client.send(
                'Page.removeScriptToEvaluateOnNewDocument', {
                    'identifier': self._injected_touch_script_id
                }
            )
            self._injected_touch_script_id = None
            reload_needed = True
        if self._emulating_mobile != viewport['isMobile']:
            reload_needed = True
        self._emulating_mobile = viewport['isMobile']
        return reload_needed
