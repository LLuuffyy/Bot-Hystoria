"""Unit tests for :mod:`dofus_bot.protocol.path`.

These cover the base-64 cell/direction encoding AND the full path
encoder that joins cells with their direction characters.
"""

from __future__ import annotations

import unittest

from dofus_bot.game.map_data import DofusMap
from dofus_bot.game.pathfinding import astar
from dofus_bot.protocol.constants import HASH_CHARS
from dofus_bot.protocol.path import (
    decode_cell,
    decode_direction,
    decode_path,
    encode_cell,
    encode_direction,
    encode_path,
)


class HashCharsTests(unittest.TestCase):
    def test_canonical_order(self) -> None:
        self.assertEqual(HASH_CHARS[0], "-")
        self.assertEqual(HASH_CHARS[1], "_")
        self.assertEqual(HASH_CHARS[2], "a")
        self.assertEqual(HASH_CHARS[27], "z")
        self.assertEqual(HASH_CHARS[28], "A")
        self.assertEqual(HASH_CHARS[53], "Z")
        self.assertEqual(HASH_CHARS[54], "0")
        self.assertEqual(HASH_CHARS[63], "9")
        self.assertEqual(len(HASH_CHARS), 64)


class CellEncodingTests(unittest.TestCase):
    def test_cell_zero_is_two_hyphens(self) -> None:
        # Cell 0 = hi 0, lo 0 = '-' + '-'
        self.assertEqual(encode_cell(0), "--")

    def test_cell_one_is_hyphen_underscore(self) -> None:
        self.assertEqual(encode_cell(1), "-_")

    def test_cell_64_is_underscore_hyphen(self) -> None:
        self.assertEqual(encode_cell(64), "_-")

    def test_roundtrip_on_full_range(self) -> None:
        for cell in (0, 1, 63, 64, 100, 255, 559, 1000, 4095):
            encoded = encode_cell(cell)
            self.assertEqual(len(encoded), 2)
            self.assertEqual(decode_cell(encoded), cell)

    def test_out_of_range_raises(self) -> None:
        with self.assertRaises(ValueError):
            encode_cell(-1)
        with self.assertRaises(ValueError):
            encode_cell(4096)

    def test_decode_rejects_bad_length(self) -> None:
        with self.assertRaises(ValueError):
            decode_cell("a")
        with self.assertRaises(ValueError):
            decode_cell("abc")

    def test_decode_rejects_unknown_chars(self) -> None:
        with self.assertRaises(ValueError):
            decode_cell("a!")


class DirectionEncodingTests(unittest.TestCase):
    def test_direction_range(self) -> None:
        for d in range(8):
            self.assertEqual(decode_direction(encode_direction(d)), d)

    def test_direction_out_of_range_raises(self) -> None:
        with self.assertRaises(ValueError):
            encode_direction(-1)
        with self.assertRaises(ValueError):
            encode_direction(64)


class PathEncodingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.m = DofusMap()

    def test_single_cell_path(self) -> None:
        self.assertEqual(encode_path([42], self.m), encode_cell(42))

    def test_path_length_matches_formula(self) -> None:
        start = self.m.xy_to_cell(2, 3)
        goal = self.m.xy_to_cell(5, 7)
        path = astar(self.m, start, goal)
        encoded = encode_path(path, self.m)
        # Expected length: 2 chars for start + (1 dir + 2 cell) per step
        self.assertEqual(len(encoded), 2 + 3 * (len(path) - 1))

    def test_path_roundtrip_preserves_cells(self) -> None:
        start = self.m.xy_to_cell(0, 0)
        goal = self.m.xy_to_cell(8, 12)
        path = astar(self.m, start, goal)
        encoded = encode_path(path, self.m)
        self.assertEqual(decode_path(encoded), path)

    def test_non_adjacent_path_raises(self) -> None:
        with self.assertRaises(ValueError):
            encode_path([0, 500], self.m)

    def test_decode_rejects_malformed(self) -> None:
        with self.assertRaises(ValueError):
            decode_path("abcd")  # 4 chars: 2 cell + 2 trailing = invalid
        with self.assertRaises(ValueError):
            decode_path("a")

    def test_decode_empty_returns_empty(self) -> None:
        self.assertEqual(decode_path(""), [])


if __name__ == "__main__":
    unittest.main()
