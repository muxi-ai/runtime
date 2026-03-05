"""
Drop-in replacement for stdlib json backed by orjson for speed.

Usage:
    from muxi.runtime.utils.fastjson import json

Supported functions: dumps, loads, dump, load, JSONDecodeError.

Limitations vs stdlib json:
- indent is always 2-space when truthy (orjson only supports OPT_INDENT_2).
  Any non-None indent value (e.g. indent=4) is coerced to 2-space output.
- separators is accepted but ignored. orjson always produces compact output
  (no trailing spaces) by default, or 2-space indented output with OPT_INDENT_2.
- Parsing hooks (object_hook, parse_float, parse_int, parse_constant, cls)
  and formatting options (skipkeys, ensure_ascii, check_circular, allow_nan)
  are accepted via **kwargs but silently ignored.
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
