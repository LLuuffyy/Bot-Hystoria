"""Unit tests for :mod:`dofus_bot.handlers.stats_handler`."""

from __future__ import annotations

import asyncio
import unittest

from dofus_bot.game.state import GameState
from dofus_bot.handlers.stats_handler import StatsHandler
from dofus_bot.scripting.events import EventBus


class StatsHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState()
        self.bus = EventBus()
        self.handler = StatsHandler(self.state, event_bus=self.bus)

    # ------------------------------------------------------------------ #
    # ASK
    # ------------------------------------------------------------------ #

    def test_ask_populates_character_identity(self) -> None:
        asyncio.run(
            self.handler.on_character_selected(
                "ASK4242|Bouftou|156|0|1|1|2|3||"
            )
        )
        self.assertEqual(self.state.character.character_id, 4242)
        self.assertEqual(self.state.character.name, "Bouftou")
        self.assertEqual(self.state.character.level, 156)

    def test_ask_without_numeric_id_is_ignored(self) -> None:
        asyncio.run(self.handler.on_character_selected("ASK"))
        self.assertEqual(self.state.character.character_id, 0)

    def test_ask_emits_character_ready_event(self) -> None:
        received: list[dict] = []

        async def listener(data: dict) -> None:
            received.append(data)

        self.bus.on("character_ready", listener)
        asyncio.run(self.handler.on_character_selected("ASK1|Joe|3"))
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["id"], 1)
        self.assertEqual(received[0]["name"], "Joe")
        self.assertEqual(received[0]["level"], 3)

    # ------------------------------------------------------------------ #
    # As
    # ------------------------------------------------------------------ #

    def test_as_populates_hp_and_max_hp(self) -> None:
        # Layout: xp|kamas|statPts|spellPts|align|hp,maxHp|energy|ap,maxAp|mp,maxMp|...
        asyncio.run(
            self.handler.on_stats(
                "As0,0,100|12345|3|2|0,0,0,0,0,0|180,250|10000,10000|6,7|3,4|"
            )
        )
        self.assertEqual(self.state.character.hp, 180)
        self.assertEqual(self.state.character.max_hp, 250)
        self.assertEqual(self.state.character.ap, 7)
        self.assertEqual(self.state.character.mp, 4)
        self.assertEqual(self.state.character.kamas, 12345)

    def test_as_partial_payload_does_not_reset_previous_values(self) -> None:
        # First, a full update.
        asyncio.run(
            self.handler.on_stats(
                "As0|500|0|0|0|100,100|0|6,6|3,3|"
            )
        )
        # Second, a truncated one (kamas only).
        asyncio.run(self.handler.on_stats("As0|777|"))
        self.assertEqual(self.state.character.kamas, 777)
        self.assertEqual(self.state.character.max_hp, 100)
        self.assertEqual(self.state.character.ap, 6)

    def test_as_handles_zero_values_gracefully(self) -> None:
        # A stats push with empty fields must not crash.
        asyncio.run(self.handler.on_stats("As|||||"))
        self.assertEqual(self.state.character.max_hp, 0)
        self.assertEqual(self.state.character.hp, 0)


if __name__ == "__main__":
    unittest.main()
