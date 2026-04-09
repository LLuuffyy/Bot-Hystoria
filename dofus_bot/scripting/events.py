"""Simple async event bus shared by handlers and the Lua engine.

Packet handlers (``MapHandler``, ``CombatHandler``, ...) call
:meth:`EventBus.emit` when something interesting happens. Subscribers
(the :class:`LuaEngine` and, optionally, Python strategy code) register
with :meth:`EventBus.on`.

All emission happens on the asyncio event loop - the bus itself does
not spawn tasks. Subscribers that need to hand work off to another
thread do so explicitly.

Known events (emitted by the current handlers):

``fight_start``    - ``{}``
``fight_end``      - ``{"raw": <GE message>}``
``turn_start``     - ``{"turn": int, "entity_id": int}``
``turn_end``       - ``{"turn": int}``
``map_change``     - ``{"map_id": int}``
``actors_update``  - ``{"count": int}``
``hp_low``         - ``{"hp": int, "max_hp": int}``   (synthetic)
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable, Dict, List

logger = logging.getLogger(__name__)

Listener = Callable[[dict], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._listeners: Dict[str, List[Listener]] = {}

    def on(self, event: str, callback: Listener) -> None:
        self._listeners.setdefault(event, []).append(callback)

    def off(self, event: str, callback: Listener) -> None:
        if event in self._listeners:
            try:
                self._listeners[event].remove(callback)
            except ValueError:
                pass

    async def emit(self, event: str, payload: dict | None = None) -> None:
        data = payload or {}
        for cb in list(self._listeners.get(event, ())):
            try:
                await cb(data)
            except Exception:
                logger.exception("Event listener failed for %s", event)
