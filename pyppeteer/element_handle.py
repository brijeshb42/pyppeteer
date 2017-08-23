import json

from pyppeteer.helper import Helper


class ElementHandle(object):

    def __init__(self, client, remote_object, mouse):
        self._client = client
        self._remote_object = remote_object
        self._mouse = mouse
        self._disposed = False

    async def dispose(self):
        if self._disposed:
            return
        self._disposed = True
        await Helper.release_object(self._client, self._remote_object)

    async def evaluate(self, page_function, *args):
        assert not self._disposed
        assert isinstance(page_function, (str, unicode))

        stringified_args = ['this']
        stringified_args.extend([json.dumps(x) for x in args])
        func_declaration = (
            'function() { return ({})'
            '({}) }').format(page_function, ','.join(stringified_args))
        object_id = self._remote_object['objectId']
        res = await self._client.send(
            'Runtime.callFunctionOn', {
                'objectId': object_id,
                'functionDeclaration': func_declaration,
                'returnByValue': False,
                'awaitPromise': True
            }
        )
        if 'exceptionDetails' in res:
            exception_details = res['exceptionDetails']
        else:
            exception_details = None
        if exception_details:
            # print(exception_details)
            raise Exception('Evaluation failed: ')
        return await Helper.serialize_remote_object(
            self._client, res['result'])

    async def _visible_center(self):
        center = await self.evaluate('''
            (element) => {
              if (!element.ownerDocument.contains(element))
                return null;
              element.scrollIntoViewIfNeeded();
              let rect = element.getBoundingClientRect();
              return {
                x: (Math.max(rect.left, 0) + Math.min(rect.right, window.innerWidth)) / 2,
                y: (Math.max(rect.top, 0) + Math.min(rect.bottom, window.innerHeight)) / 2
              };
            }
        ''')
        if not center:
            raise Exception('No node found for selector: center')
        return center

    async def hover(self):
        res = await self._visible_center()
        await self._mouse.move(res['x'], res['y'])

    async def click(self, options):
        res = await self._visible_center()
        await self._mouse.click(res['x'], res['y'], options)

    async def upload_files(self):
        # print('Not implemented')
        pass
