"""Minimal sandbox for user-provided Lua scripts.

Scripts come from the repo's own ``data/scripts/`` directory so this
is not a security boundary in the strict sense - it's more of a
"foot-gun guard" that blocks the most dangerous Lua standard library
modules (``os``, ``io``, ``package``, ``debug``) and the dynamic
``require``/``dofile``/``loadfile`` family.

The sandbox leaves the following available:

    assert, error, ipairs, pairs, next, pcall, xpcall,
    select, type, tostring, tonumber, unpack, rawequal,
    rawget, rawset, rawlen, print
    math, string, table, coroutine
    bot                          -- the :class:`BotAPI` instance

Scripts that need extra helpers can define them themselves - the aim
here is to prevent a copy-pasted example from suddenly deleting files
if the user puts something weird in ``my_scripts/``.
"""

from __future__ import annotations

from typing import Any

# Names deliberately removed from the globals before running user code.
_BLOCKED_GLOBALS = (
    "os",
    "io",
    "package",
    "debug",
    "dofile",
    "loadfile",
    "load",
    "loadstring",
    "require",
)

# Names we explicitly keep. Anything not in this set is also removed
# to avoid leaking future Lua built-ins we did not review.
_ALLOWED_GLOBALS = {
    "_G",
    "_VERSION",
    "assert",
    "error",
    "ipairs",
    "pairs",
    "next",
    "pcall",
    "xpcall",
    "select",
    "type",
    "tostring",
    "tonumber",
    "unpack",
    "rawequal",
    "rawget",
    "rawset",
    "rawlen",
    "print",
    "setmetatable",
    "getmetatable",
    "math",
    "string",
    "table",
    "coroutine",
    "bot",
}


def apply_sandbox(lua: Any) -> None:
    """Remove dangerous built-ins from the Lua runtime's global table.

    ``lua`` is a :class:`lupa.LuaRuntime`. We first nil out the explicit
    blocklist, then walk ``_G`` and nil anything that is not on the
    allow-list. This second pass catches anything we might have missed.
    """
    globals_table = lua.globals()

    # First pass: explicit blocklist (clearer log story if a user ever
    # digs into what was removed).
    for name in _BLOCKED_GLOBALS:
        try:
            globals_table[name] = None
        except Exception:
            pass

    # Second pass: drop anything that is not on the allow-list.
    to_remove = []
    # Lupa exposes _G as a dict-like object; we can iterate over its
    # keys. Some lupa versions return the underlying LuaTable which
    # requires the ``keys()`` method.
    try:
        keys = list(globals_table.keys())
    except AttributeError:
        # Older lupa: fall back to iterating the lua table via pairs.
        keys = []
        iterator = lua.eval("function(t) local r={} for k,_ in pairs(t) do r[#r+1]=k end return r end")
        for key in iterator(globals_table).values():
            keys.append(key)

    for key in keys:
        if isinstance(key, str) and key not in _ALLOWED_GLOBALS:
            to_remove.append(key)

    for key in to_remove:
        try:
            globals_table[key] = None
        except Exception:
            pass
