"""Test bootstrap: make src/entry.py importable under plain CPython.

entry.py does `from pyodide.ffi import to_js` and `from js import ...` at module
top (Cloudflare Python Workers runtime). We insert lightweight stub modules into
sys.modules before importing so the pure-Python logic can be unit tested.
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest


def _install_stubs() -> None:
    if "js" not in sys.modules:
        js = types.ModuleType("js")

        class _Placeholder:  # stands in for Response / Headers / Object / JSON
            @staticmethod
            def new(*args, **kwargs):
                return (args, kwargs)

            @staticmethod
            def fromEntries(x):
                return x

            @staticmethod
            def stringify(x):
                import json
                return json.dumps(x, default=str)

        js.Response = _Placeholder
        js.Headers = _Placeholder
        js.Object = _Placeholder
        js.JSON = _Placeholder
        js.TextDecoder = _Placeholder

        async def _fetch(*args, **kwargs):  # never called in unit tests
            raise RuntimeError("js.fetch stub called")

        js.fetch = _fetch
        sys.modules["js"] = js

    if "pyodide" not in sys.modules:
        pyodide = types.ModuleType("pyodide")
        ffi = types.ModuleType("pyodide.ffi")

        def to_js(obj, **kwargs):  # identity
            return obj

        ffi.to_js = to_js
        pyodide.ffi = ffi
        sys.modules["pyodide"] = pyodide
        sys.modules["pyodide.ffi"] = ffi


_install_stubs()

_ENTRY_PATH = Path(__file__).resolve().parent.parent / "src" / "entry.py"
_spec = importlib.util.spec_from_file_location("entry", _ENTRY_PATH)
entry = importlib.util.module_from_spec(_spec)
sys.modules["entry"] = entry
_spec.loader.exec_module(entry)


@pytest.fixture
def entry_module():
    return entry
