class Dialog(object):

    Type = {
        'Alert': 'alert',
        'BeforeUnload': 'beforeunload',
        'Confirm': 'confirm',
        'Prompt': 'prompt'
    }

    def __init__(self, client, _type, message, default_value=''):
        self._client = client
        self.type = _type
        self._message = message
        self._handled = False
        self._default_value = default_value

    def message(self):
        return self._message

    def default_value(self):
        return self._default_value

    async def accept(self, prompt_text):
        assert not self._handled
        self._handled = True
        await self._client.send('Page.handleJavaScriptDialog', {
            'accept': True,
            'promptText': prompt_text
        })

    async def dismiss(self):
        assert not self._handled
        self._handled = True
        await self._client.send('Page.handleJavaScriptDialog', {
            'accept': False
        })
