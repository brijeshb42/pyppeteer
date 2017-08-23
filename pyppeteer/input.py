import asyncio

keys = {
  'Cancel': 3,
  'Help': 6,
  'Backspace': 8,
  'Tab': 9,
  'Clear': 12,
  'Enter': 13,
  'Shift': 16,
  'Control': 17,
  'Alt': 18,
  'Pause': 19,
  'CapsLock': 20,
  'Escape': 27,
  'Convert': 28,
  'NonConvert': 29,
  'Accept': 30,
  'ModeChange': 31,
  'PageUp': 33,
  'PageDown': 34,
  'End': 35,
  'Home': 36,
  'ArrowLeft': 37,
  'ArrowUp': 38,
  'ArrowRight': 39,
  'ArrowDown': 40,
  'Select': 41,
  'Print': 42,
  'Execute': 43,
  'PrintScreen': 44,
  'Insert': 45,
  'Delete': 46,
  ')': 48,
  '!': 49,
  '@': 50,
  '#': 51,
  '$': 52,
  '%': 53,
  '^': 54,
  '&': 55,
  '*': 56,
  '(': 57,
  'Meta': 91,
  'ContextMenu': 93,
  'F1': 112,
  'F2': 113,
  'F3': 114,
  'F4': 115,
  'F5': 116,
  'F6': 117,
  'F7': 118,
  'F8': 119,
  'F9': 120,
  'F10': 121,
  'F11': 122,
  'F12': 123,
  'F13': 124,
  'F14': 125,
  'F15': 126,
  'F16': 127,
  'F17': 128,
  'F18': 129,
  'F19': 130,
  'F20': 131,
  'F21': 132,
  'F22': 133,
  'F23': 134,
  'F24': 135,
  'NumLock': 144,
  'ScrollLock': 145,
  'AudioVolumeMute': 173,
  'AudioVolumeDown': 174,
  'AudioVolumeUp': 175,
  'MediaTrackNext': 176,
  'MediaTrackPrevious': 177,
  'MediaStop': 178,
  'MediaPlayPause': 179,
  ';': 186,
  ':': 186,
  '=': 187,
  '+': 187,
  ',': 188,
  '<': 188,
  '-': 189,
  '_': 189,
  '.': 190,
  '>': 190,
  '/': 191,
  '?': 191,
  '`': 192,
  '~': 192,
  '[': 219,
  '{': 219,
  '\\': 220,
  '|': 220,
  ']': 221,
  '}': 221,
  '\'': 222,
  '"': 222,
  'AltGraph': 225,
  'Attn': 246,
  'CrSel': 247,
  'ExSel': 248,
  'EraseEof': 249,
  'Play': 250,
  'ZoomOut': 251
}


def code_for_key(key):
    if key in keys:
        return keys[key]
    if len(key) == 1:
        return ord(key.upper())
    return 0


class Keyboard(object):

    def __init__(self, client):
        self._client = client
        self._modifiers = 0
        self._pressed_keys = set()

    async def down(self, key, options={}):
        text = options['text'] if 'text' in options else None
        auto_repeat = key in self._pressed_keys
        self._pressed_keys.add(key)
        self._modifiers |= self._modifier_bit(key)
        await self._client.send('Input.dispatchKeyEvent', {
            'type': 'keyDown' if text else 'rawKeyDown',
            'modifiers': self._modifiers,
            'windowsVirtualKeyCode': code_for_key(key),
            'key': key,
            'text': text,
            'unmodifiedText': text,
            'autoRepeat': auto_repeat
        })

    def _modifier_bit(self, key):
        if key == 'Alt':
            return 1
        if key == 'Control':
            return 2
        if key == 'Meta':
            return 4
        if key == 'Shift':
            return 8
        return 0

    async def up(self, key):
        self._modifiers &= ~self._modifier_bit(key)
        self._pressed_keys.remove(key)
        await self._client.send('Input.dispatchKeyEvent', {
            'type': 'keyUp',
            'modifiers': self._modifiers,
            'key': key,
            'windowsVirtualKeyCode': code_for_key(key),
        })

    async def send_characters(self, char):
        await this._client.send('Input.dispatchKeyEvent', {
            'type': 'char',
            'modifiers': self._modifiers,
            'text': char,
            'key': char,
            'unmodifiedText': char
        })


class Mouse(object):

    def __init__(self, client, keyboard):
        self._client = client
        self._keyboard = keyboard
        self._x = 0
        self._y = 0
        self._button = 'none'

    async def move(self, x, y):
        self._x = x
        self._y = y
        await self._client.send('Input.dispatchMouseEvent', {
            'type': 'mouseMoved',
            'button': self._button,
            'x': x,
            'y': y,
            'modifiers': self._keyboard._modifiers
        })

    async def click(self, x, y, options):
        self.move(x, y)
        self.down(options)
        if options and 'delay' in options:
            await asyncio.sleep(options['delay']/1000)
        await self.up(options)

    async def down(self, opt={}):
        self._button = opt['button'] if 'button' in opt else 'left'
        await self._client.send('Input.dispatchMouseEvent', {
            'type': 'mousePressed',
            'button': self._button,
            'x': self._x,
            'y': self._y,
            'modifiers': self._keyboard._modifiers,
            'clickCount': opt['clickCount'] if 'clickCount' in opt else 1
        })

    async def up(self, opt={}):
        self._button = 'none'
        await self._client.send('Input.dispatchMouseEvent', {
            'type': 'mouseReleased',
            'button': opt['button'] if 'button' in opt else 'left',
            'x': self._x,
            'y': self._y,
            'modifiers': self._keyboard._modifiers,
            'clickCount': opt['clickCount'] if 'clickCount' in opt else 1
        })
