class Tracing(object):

    def __init__(self, client):
        self._client = client
        self._recording = False
        self._path = ''
