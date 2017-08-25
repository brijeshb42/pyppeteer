class EventEmitter(object):

    def __init__(self):
        self._events = {}

    def on(self, event, callback):
        if event not in self._events:
            self._events[event] = []
        self._events[event].append(callback)

    def emit(self, event, *args, **kwargs):
        if event not in self._events:
            return
        for callback in self._events[event]:
            arguments = []
            if args:
                arguments.append(*args)
            if kwargs:
                arguments.append(**kwargs)
            res = callback(*arguments)

    def remove_listener(self, event, cb):
        if event in self._events:
            self._events[event] = [
                ev for ev in self._events[event] if ev != cb]
        self.emit('remove_listener')

    def add_listener(self, event, callback):
        self.on(event, callback)

    def remove_all_listeners(self):
        self._events.clear()
