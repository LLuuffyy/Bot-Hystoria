"""Map and actor tracking.

Observes ``GDM`` (map data) and ``GM`` (actors list / additions /
removals) messages coming from the server and keeps the shared
:class:`GameState` in sync.

Parsing here is intentionally lenient: Dofus 1.29 private servers
sometimes tweak the exact field layout, and this handler has to
tolerate fragments it doesn't fully understand without crashing.
The goal is to extract the pieces the scripting layer actually needs
(current map, known actors, cell positions) and log the rest.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..game.state import Actor, GameState
from ..scripting.events import EventBus

logger = logging.getLogger(__name__)


class MapHandler:
    def __init__(
        self,
        state: GameState,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.state = state
        self._bus = event_bus

    async def on_map_data(self, message: str) -> None:
        """``GDM|<mapId>|<createDate>|<dataKey>``.

        Sent whenever the character enters a new map. We only track the
        map id; the raw cell data lives in a SWF asset we never load.
        """
        # Strip "GDM" and an optional leading "|" separator.
        payload = message[3:].lstrip("|")
        parts = payload.split("|")
        try:
            map_id = int(parts[0])
        except (IndexError, ValueError):
            logger.debug("Unparseable GDM: %s", message[:120])
            return
        self.state.reset_map(map_id)
        logger.info("Entered map %d", map_id)
        if self._bus is not None:
            await self._bus.emit("map_change", {"map_id": map_id})

    async def on_map_actors(self, message: str) -> None:
        """``GM|+<actor>|+<actor>|...``  (additions / initial listing)
        or ``GM|-<id>``                  (removal).

        The actor payload itself is pipe-delimited but uses different
        schemas depending on the entity type (player / monster /
        NPC / resource). This skeleton just extracts the cell id and
        a numeric entity id when possible.
        """
        payload = message[2:].lstrip("|")
        for chunk in payload.split("|"):
            if not chunk:
                continue
            if chunk.startswith("-"):
                # Removal: GM|-<id>
                try:
                    actor_id = int(chunk[1:])
                except ValueError:
                    continue
                self.state.actors.pop(actor_id, None)
                continue
            if chunk.startswith("+"):
                chunk = chunk[1:]

            fields = chunk.split(";")
            # Typical layout (varies by entity type):
            # fields[0] = cell_id
            # fields[3] = entity id
            # fields[4] = name / monster template
            try:
                cell_id = int(fields[0])
            except (ValueError, IndexError):
                continue
            try:
                actor_id = int(fields[3])
            except (ValueError, IndexError):
                actor_id = -len(self.state.actors) - 1  # synthetic

            name = fields[4] if len(fields) > 4 else ""
            is_monster = actor_id < 0 or (name and name.isdigit())

            self.state.actors[actor_id] = Actor(
                actor_id=actor_id,
                cell_id=cell_id,
                name=name,
                is_monster=is_monster,
            )
        if self._bus is not None:
            await self._bus.emit(
                "actors_update",
                {"count": len(self.state.actors)},
            )
