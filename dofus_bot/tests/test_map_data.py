"""Unit tests for :mod:`dofus_bot.game.map_data`."""

from __future__ import annotations

import unittest

from dofus_bot.game.map_data import (
    DIRECTION_NORTH_EAST,
    DIRECTION_NORTH_WEST,
    DIRECTION_SOUTH_EAST,
    DIRECTION_SOUTH_WEST,
    DofusMap,
)


class CoordinateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.m = DofusMap()  # default 14 x 40

    def test_cell_count_matches_formula(self) -> None:
        self.assertEqual(self.m.cell_count, 14 * 40 * 2)

    def test_cell_xy_roundtrip(self) -> None:
        for cell in (0, 1, 13, 14, 27, 28, 100, 559, 1119):
            x, y = self.m.cell_to_xy(cell)
            self.assertEqual(self.m.xy_to_cell(x, y), cell)

    def test_top_left_cell_is_origin(self) -> None:
        self.assertEqual(self.m.cell_to_xy(0), (0, 0))

    def test_row_boundary(self) -> None:
        # cell 14 is the first cell of the second half-row.
        self.assertEqual(self.m.cell_to_xy(14), (0, 1))
        self.assertEqual(self.m.cell_to_xy(15), (1, 1))


class NeighborTests(unittest.TestCase):
    def setUp(self) -> None:
        self.m = DofusMap()

    def _neighbor_dict(self, cell: int) -> dict[int, int]:
        """Return {neighbor_cell: direction_id} for easy lookups."""
        return {nc: d for nc, d in self.m.neighbors(cell)}

    def test_interior_cell_has_four_walking_neighbors(self) -> None:
        # Cell 200 is safely in the middle of a 14x40 map.
        neighbors = self._neighbor_dict(200)
        self.assertEqual(len(neighbors), 4)
        # The four directions must all be walking directions.
        self.assertEqual(
            set(neighbors.values()),
            {
                DIRECTION_NORTH_EAST,
                DIRECTION_NORTH_WEST,
                DIRECTION_SOUTH_EAST,
                DIRECTION_SOUTH_WEST,
            },
        )

    def test_top_left_corner_has_only_south_neighbors(self) -> None:
        neighbors = self._neighbor_dict(0)
        # Cell 0 is (0, 0) - even row, corner. Can only go south-east
        # (same x, y+1) because south-west would need x = -1.
        self.assertEqual(
            set(neighbors.values()),
            {DIRECTION_SOUTH_EAST},
        )

    def test_neighbors_are_symmetric(self) -> None:
        # If B is a neighbour of A in direction D, A must be a
        # neighbour of B in the opposite direction.
        opposite = {
            DIRECTION_SOUTH_EAST: DIRECTION_NORTH_WEST,
            DIRECTION_NORTH_WEST: DIRECTION_SOUTH_EAST,
            DIRECTION_SOUTH_WEST: DIRECTION_NORTH_EAST,
            DIRECTION_NORTH_EAST: DIRECTION_SOUTH_WEST,
        }
        for cell in (100, 150, 200, 333, 400):
            for neighbor, direction in self.m.neighbors(cell):
                reverse = self._neighbor_dict(neighbor)
                self.assertIn(cell, reverse)
                self.assertEqual(reverse[cell], opposite[direction])

    def test_direction_between_adjacent_cells(self) -> None:
        for cell in (100, 150, 200):
            for neighbor, direction in self.m.neighbors(cell):
                self.assertEqual(
                    self.m.direction_between(cell, neighbor),
                    direction,
                )

    def test_direction_between_non_adjacent_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.m.direction_between(0, 500)

    def test_blocked_cell_is_not_returned_as_neighbor(self) -> None:
        # Block one of the interior cell's neighbours.
        neighbors_before = self._neighbor_dict(200)
        target = next(iter(neighbors_before))
        self.m.block([target])
        neighbors_after = self._neighbor_dict(200)
        self.assertNotIn(target, neighbors_after)


class DistanceTests(unittest.TestCase):
    def test_distance_is_zero_for_same_cell(self) -> None:
        self.assertEqual(DofusMap().distance(100, 100), 0)

    def test_distance_is_chebyshev(self) -> None:
        m = DofusMap()
        # Cells (0, 0) and (3, 3): Chebyshev distance = 3.
        self.assertEqual(m.distance(0, m.xy_to_cell(3, 3)), 3)
        # (0, 0) and (10, 5): Chebyshev distance = 10.
        self.assertEqual(m.distance(0, m.xy_to_cell(10, 5)), 10)


if __name__ == "__main__":
    unittest.main()
