class Multimap(object):

    def __init__(self):
        self._map = {}

    def set(self, key, value):
        val = self._map.get(key, None)
        if not val:
            val = set()
            self._map[key] = val
        val.add(value)

    def get(self, key):
        result = self._map.get(key, None)
        if not result:
            return set()
        return result

    def has(self, key):
        return key in self._map

    def has_value(self, key, value):
        _set = self._map.get(key, None)
        if not _set:
            return False
        return value in _set

    @property
    def size(self):
        return len(self._map)

    def delete(self, key, value):
        values = self.get(key)
        try:
            values.remove(value)
            if len(values) == 0:
                del self._map[key]
            return True
        except KeyError:
            return False

    def delete_all(self, key):
        try:
            del self._map[key]
        except KeyError:
            pass

    def first_value(self, key):
        _set = self._map.get(key, None)
        if not _set:
            return None
        vals = list(_set)
        if len(vals):
            return vals[0]
        return None

    def first_key(self):
        _keys = self._map.keys()
        if len(_keys):
            return _keys[0]
        return None

    def values_array(self):
        result = []
        for key in self._map:
            result.append(list(self._map[key]))
        return result

    def clear(self):
        self._map.clear()
