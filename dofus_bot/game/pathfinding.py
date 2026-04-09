"""A* pathfinding on a :class:`DofusMap`.

Single public function, :func:`astar`, returns the shortest walking
path from a start cell to a destination cell as a list of cell ids
including both endpoints. The algorithm:

- uses the map's diagonal 4-neighbourhood (returned by
  :meth:`DofusMap.neighbors`)
- costs 1 per move (all diagonal moves are the same)
- uses Chebyshev distance as the heuristic (admissible and
  consistent for a uniform grid with diagonal moves of cost 1)

If no path exists :func:`astar` returns an empty list. If start and
destination are equal it returns ``[start]``.

Complexity: O(N log N) on the open set, where N is the number of
reachable cells. On a 14x40 Dofus map (560 cells) this runs in a
fraction of a millisecond so we don't need anything fancier.
"""

from __future__ import annotations

import heapq
from typing import Dict, List, Optional

from .map_data import DofusMap


def astar(
    dmap: DofusMap,
    start: int,
    goal: int,
    max_expansions: int = 20_000,
) -> List[int]:
    """Return the shortest walking path from *start* to *goal*.

    Both endpoints are included in the output. Returns an empty list
    if no path exists or either endpoint is invalid / blocked.

    ``max_expansions`` bounds the search so a pathological map can
    never hang the bot; the default is comfortably above the worst
    case for a 14x40 grid.
    """
    if not dmap.is_valid(start) or not dmap.is_valid(goal):
        return []
    if start == goal:
        return [start]
    if not dmap.is_walkable(goal):
        return []

    came_from: Dict[int, int] = {}
    g_score: Dict[int, int] = {start: 0}

    # The open set entries are (f_score, tiebreaker, cell). The
    # tiebreaker makes the heap ordering deterministic when two
    # cells share the same f-score, which makes tests reproducible.
    open_set: List[tuple[int, int, int]] = []
    counter = 0
    heapq.heappush(open_set, (dmap.distance(start, goal), counter, start))

    expansions = 0
    while open_set and expansions < max_expansions:
        _, _, current = heapq.heappop(open_set)
        if current == goal:
            return _reconstruct(came_from, current)

        expansions += 1
        current_g = g_score[current]
        for neighbor, _direction in dmap.neighbors(current):
            tentative = current_g + 1
            if tentative < g_score.get(neighbor, 1 << 30):
                came_from[neighbor] = current
                g_score[neighbor] = tentative
                counter += 1
                f_score = tentative + dmap.distance(neighbor, goal)
                heapq.heappush(open_set, (f_score, counter, neighbor))

    return []


def _reconstruct(came_from: Dict[int, int], current: int) -> List[int]:
    path: List[int] = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def path_cost(path: List[int]) -> int:
    """Walking cost of a path = number of moves = ``len(path) - 1``."""
    return max(0, len(path) - 1)
