"""Combat lifecycle tracking.

Observes the combat-related messages and exposes high-level events
(``fight_start``, ``turn_start``, ``turn_end``, ``fight_end``) that
the scripting layer can subscribe to.

Key message prefixes (Dofus 1.29 Retro):
    GA900;...           - fight start request / confirmation (action 900)
    GJK<state>          - fight joined
    GP<cells>|<timeout> - placement phase
    GT<ids>             - turn order announcement
    GTS<entityId>|<ms>  - a given entity's turn starts
    GTM<...>            - mid-turn state update (HP/PA/PM)
    GTE<entityId>       - a given entity's turn ends
    GE<rewards>         - fight finished
    GF                  - fight result screen closed
"""

from __future__ import annotations

import logging
from typing import Optional

from ..game.state import FightEntity, GameState
from ..scripting.events import EventBus

logger = logging.getLogger(__name__)


class CombatHandler:
    def __init__(
        self,
        state: GameState,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.state = state
        self._bus = event_bus
        self._turn_number = 0

    async def _emit(self, event: str, payload: dict | None = None) -> None:
        if self._bus is not None:
            await self._bus.emit(event, payload or {})

    # ------------------------------------------------------------------ #
    # Packet handlers
    # ------------------------------------------------------------------ #

    async def on_fight_join(self, message: str) -> None:
        """``GJK<state>`` - the player has joined a fight."""
        self.state.reset_fight()
        self.state.in_fight = True
        self._turn_number = 0
        logger.info("Fight joined: %s", message)
        await self._emit("fight_start")

    async def on_turn_list(self, message: str) -> None:
        """``GT<id>|<id>|...`` - turn order for the whole fight."""
        logger.debug("Turn order: %s", message)

    async def on_turn_start(self, message: str) -> None:
        """``GTS<entityId>|<timeoutMs>`` - a turn starts."""
        payload = message[3:]
        parts = payload.split("|")
        try:
            entity_id = int(parts[0])
        except (IndexError, ValueError):
            return
        self._turn_number += 1
        is_self = entity_id == self.state.character.character_id
        self.state.my_turn = is_self
        logger.info(
            "Turn %d start (entity %d, mine=%s)",
            self._turn_number, entity_id, is_self,
        )
        if is_self:
            await self._emit(
                "turn_start",
                {"turn": self._turn_number, "entity_id": entity_id},
            )

    async def on_turn_mid(self, message: str) -> None:
        """``GTM<entityId>;<hp>;<ap>;<mp>;...`` - mid-turn state update."""
        payload = message[3:]
        # Multiple entities may be updated in one message, separated by |.
        for entity_chunk in payload.split("|"):
            fields = entity_chunk.split(";")
            try:
                entity_id = int(fields[0])
            except (ValueError, IndexError):
                continue
            entity = self.state.fight_entities.setdefault(
                entity_id, FightEntity(entity_id=entity_id)
            )
            if len(fields) > 1:
                try:
                    entity.hp = int(fields[1])
                except ValueError:
                    pass
            if len(fields) > 2:
                try:
                    entity.ap = int(fields[2])
                except ValueError:
                    pass
            if len(fields) > 3:
                try:
                    entity.mp = int(fields[3])
                except ValueError:
                    pass

            # If this update is for our own character, keep Character.hp
            # in sync and fire hp_low below a 40% threshold. Scripts can
            # use that hook for kite/heal decisions.
            if entity_id == self.state.character.character_id:
                self.state.character.hp = entity.hp
                self.state.character.ap = entity.ap
                self.state.character.mp = entity.mp
                self.state.character.cell_id = entity.cell_id if entity.cell_id >= 0 else self.state.character.cell_id
                max_hp = self.state.character.max_hp
                if max_hp > 0 and entity.hp <= max_hp * 0.4:
                    await self._emit(
                        "hp_low",
                        {"hp": entity.hp, "max_hp": max_hp},
                    )

    async def on_turn_end(self, message: str) -> None:
        """``GTE<entityId>``"""
        payload = message[3:]
        try:
            entity_id = int(payload.split("|", 1)[0])
        except ValueError:
            return
        is_self = entity_id == self.state.character.character_id
        if is_self:
            self.state.my_turn = False
            await self._emit("turn_end", {"turn": self._turn_number})

    async def on_fight_end(self, message: str) -> None:
        """``GE<timestamp>|<winner>|...`` - fight finished (rewards follow)."""
        logger.info("Fight ended: %s", message[:120])
        await self._emit("fight_end", {"raw": message})
        self.state.reset_fight()
