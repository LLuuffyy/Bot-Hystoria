"""Dofus 1.29 map topology.

A Dofus Retro map is an isometric diamond. Cells are numbered 0..N-1
row by row. What the client calls a "row" is really a pair of
half-rows offset by half a cell, so every two half-rows form one
"brick row" of the diamond:

    half-row 0  (y=0):  cell 0   cell 1   ...  cell 13
      half-row 1 (y=1):   cell 14  cell 15  ...  cell 27
    half-row 2  (y=2):  cell 28  cell 29  ...  cell 41
      half-row 3 (y=3):   cell 42  cell 43  ...  cell 55
    ...

The offset means that two cells in the same half-row are NOT physically
adjacent (there is a diamond tile between them); physical adjacency
happens diagonally between consecutive half-rows.

For the bot we only need:

- ``cell_to_xy`` / ``xy_to_cell``: convert between a cell id and a
  (x, y) coordinate where y is the half-row index and x the column.
- ``neighbors``: the 4 diagonal walking neighbors of a cell, with
  their Dofus-encoded direction id.

We do NOT parse the SWF map assets, so every cell is considered
walkable by default. Scripts can override :attr:`DofusMap.blocked`
(a ``set[int]``) at runtime if they know a cell is not walkable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Set, Tuple

# Standard Dofus 1.29 Retro map dimensions. A handful of special maps
# (Incarnam tutorial rooms) use different sizes but 14 x 40 covers
# 99 pct of Amakna / Bonta / Brakmar / Sufokia.
DEFAULT_WIDTH = 14
DEFAULT_HEIGHT = 40

# Direction id -> (dx, dy) delta in the (x, y = half-row) coordinate
# system used by :class:`DofusMap`. These follow the Dofus direction
# encoding (0 = E, 1 = SE, 2 = S, 3 = SW, 4 = W, 5 = NW, 6 = N, 7 = NE).
# Only the four diagonal ones are valid for walking on a diamond grid.
DIRECTION_EAST = 0
DIRECTION_SOUTH_EAST = 1
DIRECTION_SOUTH = 2
DIRECTION_SOUTH_WEST = 3
DIRECTION_WEST = 4
DIRECTION_NORTH_WEST = 5
DIRECTION_NORTH = 6
DIRECTION_NORTH_EAST = 7

# The walking directions. Non-walking ones (N, S, E, W) exist in the
# protocol for facing only.
WALK_DIRECTIONS: Tuple[int, ...] = (
    DIRECTION_SOUTH_EAST,
    DIRECTION_SOUTH_WEST,
    DIRECTION_NORTH_EAST,
    DIRECTION_NORTH_WEST,
)


@dataclass
class DofusMap:
    """Topology helper for a single Dofus 1.29 map."""

    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    blocked: Set[int] = field(default_factory=set)

    @property
    def cell_count(self) -> int:
        """Total number of cells on the map (always ``2 * width * height``)."""
        return 2 * self.width * self.height

    # ------------------------------------------------------------------ #
    # Coordinate conversion
    # ------------------------------------------------------------------ #

    def cell_to_xy(self, cell: int) -> Tuple[int, int]:
        """Return the ``(x, y)`` coordinates of *cell*.

        ``y`` is the half-row index (0 = top half-row) and ``x`` is
        the column within that half-row.
        """
        y, x = divmod(cell, self.width)
        return x, y

    def xy_to_cell(self, x: int, y: int) -> int:
        """Inverse of :meth:`cell_to_xy`."""
        return y * self.width + x

    def is_valid(self, cell: int) -> bool:
        return 0 <= cell < self.cell_count

    def is_walkable(self, cell: int) -> bool:
        return self.is_valid(cell) and cell not in self.blocked

    def block(self, cells: Iterable[int]) -> None:
        for c in cells:
            self.blocked.add(int(c))

    def unblock(self, cells: Iterable[int]) -> None:
        for c in cells:
            self.blocked.discard(int(c))

    # ------------------------------------------------------------------ #
    # Neighbourhood + direction computation
    # ------------------------------------------------------------------ #

    def neighbors(self, cell: int) -> List[Tuple[int, int]]:
        """Return the walking neighbours of *cell*.

        Result is a list of ``(neighbor_cell, direction_id)`` pairs.
        Only cells inside the map and not in :attr:`blocked` are
        returned. The direction id follows the Dofus convention
        (see the module-level ``DIRECTION_*`` constants).
        """
        x, y = self.cell_to_xy(cell)

        # In the "half-row" coordinate system, a diagonal move always
        # changes y by 1 and x by 0 or +-1, depending on the parity
        # of the current row. Odd half-rows are shifted right by half
        # a cell relative to even half-rows.
        is_odd_row = (y % 2) == 1

        candidates: List[Tuple[int, int, int]] = []  # (nx, ny, dir)
        if is_odd_row:
            candidates.append((x + 1, y + 1, DIRECTION_SOUTH_EAST))
            candidates.append((x, y + 1, DIRECTION_SOUTH_WEST))
            candidates.append((x + 1, y - 1, DIRECTION_NORTH_EAST))
            candidates.append((x, y - 1, DIRECTION_NORTH_WEST))
        else:
            candidates.append((x, y + 1, DIRECTION_SOUTH_EAST))
            candidates.append((x - 1, y + 1, DIRECTION_SOUTH_WEST))
            candidates.append((x, y - 1, DIRECTION_NORTH_EAST))
            candidates.append((x - 1, y - 1, DIRECTION_NORTH_WEST))

        out: List[Tuple[int, int]] = []
        for nx, ny, direction in candidates:
            if 0 <= nx < self.width and 0 <= ny < 2 * self.height:
                nc = self.xy_to_cell(nx, ny)
                if self.is_walkable(nc):
                    out.append((nc, direction))
        return out

    def direction_between(self, src: int, dst: int) -> int:
        """Return the direction id used to walk from *src* to *dst*.

        Raises :class:`ValueError` if the two cells are not adjacent
        walking neighbours.
        """
        for nc, direction in self.neighbors(src):
            if nc == dst:
                return direction
        raise ValueError(f"cells {src} and {dst} are not adjacent")

    # ------------------------------------------------------------------ #
    # Heuristic used by the A* pathfinder
    # ------------------------------------------------------------------ #

    def distance(self, a: int, b: int) -> int:
        """Chebyshev distance in ``(x, y)`` space.

        Good enough as an A* heuristic: it is admissible for a grid
        that allows diagonal steps of cost 1, which is our case.
        """
        ax, ay = self.cell_to_xy(a)
        bx, by = self.cell_to_xy(b)
        return max(abs(ax - bx), abs(ay - by))
