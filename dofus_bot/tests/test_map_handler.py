"""Unit tests for :mod:`dofus_bot.handlers.map_handler`."""

from __future__ import annotations

import asyncio
import unittest

from dofus_bot.game.state import GameState
from dofus_bot.handlers.map_handler import MapHandler
from dofus_bot.scripting.events import EventBus


class MapHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState()
        self.bus = EventBus()
        self.handler = MapHandler(self.state, event_bus=self.bus)

    def test_map_data_parses_id_and_emits_event(self) -> None:
        received: list[dict] = []

        async def listener(data: dict) -> None:
            received.append(data)

        self.bus.on("map_change", listener)

        asyncio.run(self.handler.on_map_data("GDM|7411|12345|abcd"))
        self.assertEqual(self.state.current_map_id, 7411)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["map_id"], 7411)

    def test_map_data_resets_actors(self) -> None:
        asyncio.run(self.handler.on_map_data("GDM|1|x|y"))
        self.state.actors[10] = None  # type: ignore[assignment]
        asyncio.run(self.handler.on_map_data("GDM|2|x|y"))
        self.assertFalse(self.state.actors)
        self.assertEqual(self.state.current_map_id, 2)

    def test_map_data_ignores_garbage(self) -> None:
        received: list[dict] = []

        async def listener(data: dict) -> None:
            received.append(data)

        self.bus.on("map_change", listener)
        asyncio.run(self.handler.on_map_data("GDMinvalid"))
        self.assertEqual(self.state.current_map_id, 0)
        self.assertEqual(received, [])

    def test_map_actors_parses_additions(self) -> None:
        asyncio.run(self.handler.on_map_data("GDM|1|x|y"))
        # GM with two additions: cell|???|???|id|name
        asyncio.run(
            self.handler.on_map_actors(
                "GM|+123;0;0;5001;Joe;1|+456;0;0;5002;7411"
            )
        )
        self.assertEqual(len(self.state.actors), 2)
        self.assertIn(5001, self.state.actors)
        self.assertEqual(self.state.actors[5001].cell_id, 123)
        self.assertIn(5002, self.state.actors)

    def test_map_actors_handles_removal(self) -> None:
        asyncio.run(self.handler.on_map_data("GDM|1|x|y"))
        asyncio.run(
            self.handler.on_map_actors("GM|+42;0;0;7001;Bob")
        )
        self.assertIn(7001, self.state.actors)
        asyncio.run(self.handler.on_map_actors("GM|-7001"))
        self.assertNotIn(7001, self.state.actors)


if __name__ == "__main__":
    unittest.main()
