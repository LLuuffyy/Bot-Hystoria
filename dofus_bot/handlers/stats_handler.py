"""Character identification + live stat updates.

Two messages matter for keeping :class:`Character` in sync with what
the real Dofus 1.29 Retro server tells the client:

``ASK<id>|<name>|<level>|...``
    Sent after the client picks a character at the selection screen.
    The payload contains the character id, name, level and a long
    tail of cosmetic fields (skin, colours, equipment, ...). We only
    care about the first three.

``As<xp>|<kamas>|<stat>|<spell>|<align>|<hp>,<maxHp>|<ap>,<maxAp>|<mp>,<maxMp>|...``
    Stats payload, sent at login and after every level-up / damage
    event out of combat. The exact field order is stable across 1.29
    private servers but the tail varies, so we walk the groups we
    know about and silently tolerate anything extra.

Both parsers are deliberately lenient: if a field is missing or
unparseable we leave the current value alone rather than reset it to
zero (the bot would lose its head between two updates otherwise).
"""

from __future__ import annotations

import logging
from typing import List, Optional

from ..game.state import GameState
from ..scripting.events import EventBus

logger = logging.getLogger(__name__)


def _safe_int(value: str, fallback: int = 0) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return fallback


def _split_pair(value: str) -> tuple[int, int]:
    """Parse ``"<cur>,<max>"`` and return ``(cur, max)``.

    Missing pieces default to ``0``.
    """
    parts = value.split(",")
    cur = _safe_int(parts[0]) if len(parts) > 0 else 0
    mx = _safe_int(parts[1]) if len(parts) > 1 else 0
    return cur, mx


class StatsHandler:
    """Maintains :class:`Character` fields from ``ASK`` / ``As`` packets."""

    def __init__(
        self,
        state: GameState,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.state = state
        self._bus = event_bus

    # ------------------------------------------------------------------ #
    # ASK - "Account Selected character Known/Konfirmed"
    # ------------------------------------------------------------------ #

    async def on_character_selected(self, message: str) -> None:
        """``ASK<id>|<name>|<level>|...`` handler.

        After this runs, :attr:`GameState.character.character_id` is
        populated and combat turn detection finally works.
        """
        payload = message[3:]
        if not payload:
            return
        fields: List[str] = payload.split("|")

        char_id = _safe_int(fields[0])
        if char_id <= 0:
            logger.debug("ASK with no numeric id: %s", message[:120])
            return

        self.state.character.character_id = char_id
        if len(fields) > 1 and fields[1]:
            self.state.character.name = fields[1]
        if len(fields) > 2:
            level = _safe_int(fields[2])
            if level > 0:
                self.state.character.level = level

        logger.info(
            "Character selected: id=%d name=%r level=%d",
            self.state.character.character_id,
            self.state.character.name,
            self.state.character.level,
        )

        if self._bus is not None:
            await self._bus.emit(
                "character_ready",
                {
                    "id": self.state.character.character_id,
                    "name": self.state.character.name,
                    "level": self.state.character.level,
                },
            )

    # ------------------------------------------------------------------ #
    # As - full stats push
    # ------------------------------------------------------------------ #

    async def on_stats(self, message: str) -> None:
        """``As<xp>|<kamas>|<stat>|<spell>|<align>|<hp>,<max>|<ap>,<max>|<mp>,<max>|...``.

        Only fields we actually use are extracted; the rest is left
        alone so we don't trash already-correct state.
        """
        payload = message[2:]
        if not payload:
            return
        groups: List[str] = payload.split("|")

        # Group index layout (1.29 Retro, confirmed by retroproto + shivas):
        #   0: xp (low,current,next) - we skip
        #   1: kamas
        #   2: statPointsAvailable   - we skip
        #   3: spellPointsAvailable  - we skip
        #   4: alignment stuff        - we skip
        #   5: hp,maxHp
        #   6: energy,maxEnergy       - we skip
        #   7: ap,maxAp
        #   8: mp,maxMp
        #   9+: primary stats (strength, intel, ...)

        if len(groups) > 1:
            kamas = _safe_int(groups[1])
            if kamas >= 0:
                self.state.character.kamas = kamas

        if len(groups) > 5:
            hp, max_hp = _split_pair(groups[5])
            if max_hp > 0:
                self.state.character.max_hp = max_hp
            if hp > 0 or max_hp > 0:
                self.state.character.hp = hp

        if len(groups) > 7:
            _, max_ap = _split_pair(groups[7])
            if max_ap > 0:
                self.state.character.ap = max_ap

        if len(groups) > 8:
            _, max_mp = _split_pair(groups[8])
            if max_mp > 0:
                self.state.character.mp = max_mp

        logger.debug(
            "Stats update: hp=%d/%d ap=%d mp=%d kamas=%d",
            self.state.character.hp,
            self.state.character.max_hp,
            self.state.character.ap,
            self.state.character.mp,
            self.state.character.kamas,
        )
