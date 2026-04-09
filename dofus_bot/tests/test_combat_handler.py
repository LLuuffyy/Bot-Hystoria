"""Unit tests for :mod:`dofus_bot.handlers.combat_handler`.

The turn-detection bug that prompted this whole iteration is covered
by :meth:`CombatHandlerTurnDetectionTests.test_turn_start_matches_character_id`.
"""

from __future__ import annotations

import asyncio
import unittest

from dofus_bot.game.state import GameState
from dofus_bot.handlers.combat_handler import CombatHandler
from dofus_bot.scripting.events import EventBus


class CombatHandlerTurnDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState()
        self.state.character.character_id = 4242
        self.state.character.max_hp = 250
        self.bus = EventBus()
        self.handler = CombatHandler(self.state, event_bus=self.bus)

    def test_fight_join_resets_state_and_emits(self) -> None:
        received: list[dict] = []

        async def on_fs(data: dict) -> None:
            received.append(data)

        self.bus.on("fight_start", on_fs)

        self.state.fight_entities[99] = None  # type: ignore[assignment]
        asyncio.run(self.handler.on_fight_join("GJK1"))
        self.assertTrue(self.state.in_fight)
        self.assertFalse(self.state.fight_entities)
        self.assertEqual(len(received), 1)

    def test_turn_start_matches_character_id(self) -> None:
        """With character_id set, our turn is detected and the event fires."""
        received: list[dict] = []

        async def on_ts(data: dict) -> None:
            received.append(data)

        self.bus.on("turn_start", on_ts)

        asyncio.run(self.handler.on_fight_join("GJK1"))
        asyncio.run(self.handler.on_turn_start("GTS4242|30000"))
        self.assertTrue(self.state.my_turn)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["turn"], 1)
        self.assertEqual(received[0]["entity_id"], 4242)

    def test_turn_start_for_another_entity_does_not_emit(self) -> None:
        received: list[dict] = []

        async def on_ts(data: dict) -> None:
            received.append(data)

        self.bus.on("turn_start", on_ts)
        asyncio.run(self.handler.on_fight_join("GJK1"))
        asyncio.run(self.handler.on_turn_start("GTS9999|30000"))
        self.assertFalse(self.state.my_turn)
        self.assertEqual(received, [])

    def test_turn_mid_updates_own_character_and_fires_hp_low(self) -> None:
        low_events: list[dict] = []

        async def on_low(data: dict) -> None:
            low_events.append(data)

        self.bus.on("hp_low", on_low)

        asyncio.run(self.handler.on_fight_join("GJK1"))
        # 80/250 -> below 40% threshold.
        asyncio.run(self.handler.on_turn_mid("GTM4242;80;5;3"))
        self.assertEqual(self.state.character.hp, 80)
        self.assertEqual(self.state.character.ap, 5)
        self.assertEqual(self.state.character.mp, 3)
        self.assertEqual(len(low_events), 1)
        self.assertEqual(low_events[0]["hp"], 80)
        self.assertEqual(low_events[0]["max_hp"], 250)

    def test_turn_mid_above_threshold_does_not_fire_hp_low(self) -> None:
        low_events: list[dict] = []

        async def on_low(data: dict) -> None:
            low_events.append(data)

        self.bus.on("hp_low", on_low)

        asyncio.run(self.handler.on_fight_join("GJK1"))
        asyncio.run(self.handler.on_turn_mid("GTM4242;200;5;3"))
        self.assertEqual(self.state.character.hp, 200)
        self.assertEqual(low_events, [])

    def test_turn_end_only_clears_my_turn_for_self(self) -> None:
        asyncio.run(self.handler.on_fight_join("GJK1"))
        asyncio.run(self.handler.on_turn_start("GTS4242|30000"))
        asyncio.run(self.handler.on_turn_end("GTE9999"))
        self.assertTrue(self.state.my_turn)
        asyncio.run(self.handler.on_turn_end("GTE4242"))
        self.assertFalse(self.state.my_turn)

    def test_fight_end_resets_state(self) -> None:
        asyncio.run(self.handler.on_fight_join("GJK1"))
        asyncio.run(self.handler.on_fight_end("GE0|1"))
        self.assertFalse(self.state.in_fight)
        self.assertFalse(self.state.fight_entities)


if __name__ == "__main__":
    unittest.main()
