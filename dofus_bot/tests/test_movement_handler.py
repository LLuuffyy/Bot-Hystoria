"""Unit tests for :mod:`dofus_bot.handlers.movement_handler`."""

from __future__ import annotations

import asyncio
import unittest

from dofus_bot.game.map_data import DofusMap
from dofus_bot.game.pathfinding import astar
from dofus_bot.game.state import Actor, GameState
from dofus_bot.handlers.movement_handler import MovementHandler
from dofus_bot.protocol.path import encode_path
from dofus_bot.scripting.events import EventBus


def _walk_packet(entity_id: int, path: list[int], dmap: DofusMap) -> str:
    encoded = encode_path(path, dmap)
    return f"GA0;1;{entity_id};{encoded}"


class MovementHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState()
        self.state.character.character_id = 4242
        self.state.character.cell_id = 100
        self.bus = EventBus()
        self.handler = MovementHandler(self.state, event_bus=self.bus)
        self.m = DofusMap()

    def test_own_walk_updates_cell_and_emits(self) -> None:
        start = self.state.character.cell_id
        goal = self.m.xy_to_cell(10, 12)
        path = astar(self.m, start, goal)
        self.assertTrue(path)

        events: list[dict] = []

        async def listener(data: dict) -> None:
            events.append(data)

        self.bus.on("character_moved", listener)

        asyncio.run(self.handler.on_game_action(_walk_packet(4242, path, self.m)))
        self.assertEqual(self.state.character.cell_id, goal)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["from"], start)
        self.assertEqual(events[0]["to"], goal)

    def test_other_actor_walk_updates_only_that_actor(self) -> None:
        # Register another actor on the map.
        self.state.actors[999] = Actor(actor_id=999, cell_id=50)
        path = astar(self.m, 50, self.m.xy_to_cell(6, 6))
        self.assertTrue(path)

        asyncio.run(self.handler.on_game_action(_walk_packet(999, path, self.m)))
        self.assertEqual(self.state.actors[999].cell_id, path[-1])
        # Our own character should be untouched.
        self.assertEqual(self.state.character.cell_id, 100)

    def test_non_movement_ga_is_ignored(self) -> None:
        # GA300 (cast spell) must NOT touch the character cell.
        asyncio.run(self.handler.on_game_action("GA300;161;234"))
        self.assertEqual(self.state.character.cell_id, 100)

    def test_malformed_packet_does_not_raise(self) -> None:
        # Missing fields, garbage path - the handler must swallow them.
        asyncio.run(self.handler.on_game_action("GA0;1"))
        asyncio.run(self.handler.on_game_action("GA0;1;4242;!!!"))
        self.assertEqual(self.state.character.cell_id, 100)


if __name__ == "__main__":
    unittest.main()
