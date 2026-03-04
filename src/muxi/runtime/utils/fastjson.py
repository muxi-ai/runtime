"""
Drop-in replacement for stdlib json backed by orjson for speed.

Usage:
    from muxi.runtime.utils.fastjson import json

All stdlib json functions are supported: dumps, loads, dump, load, JSONDecodeError.
"""

import orjson

JSONDecodeError = orjson.JSONDecodeError


def dumps(obj, *, indent=None, separators=None, sort_keys=False, default=None, **kwargs) -> str:
    opts = 0
    if indent:
        opts |= orjson.OPT_INDENT_2
    if sort_keys:
        opts |= orjson.OPT_SORT_KEYS
    return orjson.dumps(obj, option=opts or None, default=default).decode()


def loads(s, **kwargs):
    return orjson.loads(s)


def dump(obj, fp, *, indent=None, separators=None, sort_keys=False, default=None, **kwargs):
    opts = 0
    if indent:
        opts |= orjson.OPT_INDENT_2
    if sort_keys:
        opts |= orjson.OPT_SORT_KEYS
    data = orjson.dumps(obj, option=opts or None, default=default).decode()
    fp.write(data)


def load(fp, **kwargs):
    return orjson.loads(fp.read())


class _FastJsonModule:
    """Mimics the stdlib json module interface so `import fastjson as json` works."""

    dumps = staticmethod(dumps)
    loads = staticmethod(loads)
    dump = staticmethod(dump)
    load = staticmethod(load)
    JSONDecodeError = JSONDecodeError


json = _FastJsonModule()
