"""Lua scripting layer for the Dofus MITM bot.

The scripting layer lets the user drive the bot (spell rotations, farm
routes, auto-heal, ...) from Lua files in ``dofus_bot/data/scripts/``
without touching the Python engine.

Architecture:

- :class:`EventBus` receives events from the packet handlers
  (``fight_start``, ``turn_start``, ``map_change``, ...) and forwards
  them to the active :class:`LuaEngine`.
- :class:`BotAPI` wraps the shared :class:`GameState` and the proxy
  injection methods. Its attributes and methods are exposed to Lua as
  the global ``bot`` object.
- :class:`LuaEngine` owns a :mod:`lupa` runtime running in a background
  thread, loads a ``.lua`` file, dispatches events from the bus to
  registered Lua callbacks and transparently hot-reloads the script
  when the file changes on disk.
"""

from .api import BotAPI
from .engine import LuaEngine, LuaUnavailableError
from .events import EventBus

__all__ = ["BotAPI", "EventBus", "LuaEngine", "LuaUnavailableError"]
