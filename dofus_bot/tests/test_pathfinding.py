"""Unit tests for :mod:`dofus_bot.game.pathfinding`."""

from __future__ import annotations

import unittest

from dofus_bot.game.map_data import DofusMap
from dofus_bot.game.pathfinding import astar, path_cost


class AStarTests(unittest.TestCase):
    def setUp(self) -> None:
        self.m = DofusMap()

    def test_same_start_and_goal_returns_single_cell(self) -> None:
        self.assertEqual(astar(self.m, 42, 42), [42])

    def test_adjacent_cells_return_two_step_path(self) -> None:
        neighbor, _ = self.m.neighbors(200)[0]
        path = astar(self.m, 200, neighbor)
        self.assertEqual(path, [200, neighbor])
        self.assertEqual(path_cost(path), 1)

    def test_path_endpoints_are_correct(self) -> None:
        start = self.m.xy_to_cell(0, 0)
        goal = self.m.xy_to_cell(5, 10)
        path = astar(self.m, start, goal)
        self.assertTrue(path)
        self.assertEqual(path[0], start)
        self.assertEqual(path[-1], goal)

    def test_path_only_uses_adjacent_steps(self) -> None:
        start = self.m.xy_to_cell(2, 3)
        goal = self.m.xy_to_cell(7, 15)
        path = astar(self.m, start, goal)
        self.assertTrue(path)
        for i in range(1, len(path)):
            neighbors = {nc for nc, _ in self.m.neighbors(path[i - 1])}
            self.assertIn(
                path[i],
                neighbors,
                f"step {path[i - 1]} -> {path[i]} is not adjacent",
            )

    def test_unreachable_goal_returns_empty(self) -> None:
        # Box cell 200 in by blocking all four neighbours.
        neighbors = [nc for nc, _ in self.m.neighbors(200)]
        self.m.block(neighbors)
        path = astar(self.m, 200, self.m.xy_to_cell(10, 10))
        self.assertEqual(path, [])

    def test_blocked_goal_returns_empty(self) -> None:
        goal = self.m.xy_to_cell(5, 5)
        self.m.block([goal])
        self.assertEqual(astar(self.m, 0, goal), [])

    def test_path_cost_bounded_below_by_chebyshev(self) -> None:
        # Chebyshev distance is an admissible heuristic, so the real
        # path cost is always >= Chebyshev. Equality holds only on a
        # grid that allows 8-direction moves; our diamond grid only
        # allows 4 diagonal walks, so the real cost can be strictly
        # larger (parity constraints on x-drift per step).
        start = self.m.xy_to_cell(1, 2)
        goal = self.m.xy_to_cell(6, 9)
        path = astar(self.m, start, goal)
        self.assertTrue(path)
        self.assertGreaterEqual(
            path_cost(path), self.m.distance(start, goal)
        )

    def test_pure_diagonal_path_has_minimum_cost(self) -> None:
        # Going from (0, 0) to (0, 4) along the same column is a pure
        # alternating SE/SW walk: cost == y diff == 4.
        start = self.m.xy_to_cell(0, 0)
        goal = self.m.xy_to_cell(0, 4)
        path = astar(self.m, start, goal)
        self.assertEqual(path_cost(path), 4)

    def test_invalid_cell_returns_empty(self) -> None:
        self.assertEqual(astar(self.m, -1, 10), [])
        self.assertEqual(astar(self.m, 0, 999_999), [])


if __name__ == "__main__":
    unittest.main()
