"""Movement packet observation.

Whenever an entity walks on the current map, the server broadcasts a
``GA0;1;<charId>;<encodedPath>`` packet to every client that can see
it. When the entity is *our* character, we extract the final cell of
the path and update :attr:`GameState.character.cell_id` so the
scripting layer knows where the bot ended up.

We also update the position of other actors (monsters / players) so
``bot.map.actors`` reflects live movement.

The handler deliberately does not try to simulate the walk locally -
path interpolation is the server's job, and we only care about the
destination.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..game.state import GameState
from ..protocol.path import decode_path
from ..scripting.events import EventBus

logger = logging.getLogger(__name__)


class MovementHandler:
    def __init__(
        self,
        state: GameState,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.state = state
        self._bus = event_bus

    async def on_game_action(self, message: str) -> None:
        """Handle every ``GA`` message, filter for movement (action 0).

        ``GA`` is the Dofus action channel used for a wide range of
        things (movement, cast, fight request, ...). We only react to
        action id ``0`` (walk) here; the other actions go through
        dedicated handlers.

        Format: ``GA0;1;<entityId>;<encodedPath>`` where:

        - ``GA`` is the 2-char prefix
        - ``0`` is the action id (walk)
        - ``1`` is a sub-id (move confirmation)
        - ``<entityId>`` is the character / actor doing the move
        - ``<encodedPath>`` is the hash-encoded path list
        """
        # Strip the "GA" prefix and split the semicolon payload.
        payload = message[2:]
        parts = payload.split(";")
        if len(parts) < 4:
            return
        try:
            action_id = int(parts[0])
        except ValueError:
            return
        if action_id != 0:
            return  # not a movement

        try:
            entity_id = int(parts[2])
        except ValueError:
            return

        encoded_path = parts[3]
        try:
            cells = decode_path(encoded_path)
        except ValueError:
            logger.debug("Malformed movement path: %s", message[:120])
            return

        if not cells:
            return
        destination = cells[-1]

        if entity_id == self.state.character.character_id:
            previous = self.state.character.cell_id
            self.state.character.cell_id = destination
            logger.debug(
                "Character walked %s -> %s (%d cells)",
                previous, destination, len(cells),
            )
            if self._bus is not None:
                await self._bus.emit(
                    "character_moved",
                    {
                        "from": previous,
                        "to": destination,
                        "path": cells,
                    },
                )
            return

        # Update another actor's cell if we know about it.
        actor = self.state.actors.get(entity_id)
        if actor is not None:
            actor.cell_id = destination
