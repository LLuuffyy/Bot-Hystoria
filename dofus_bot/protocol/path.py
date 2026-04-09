"""Cell and path encoding for Dofus 1.29.

The Dofus Retro wire protocol packs cell ids and movement paths into
a custom base-64-like encoding that uses :data:`HASH_CHARS` as its
alphabet. Two low-level helpers do the heavy lifting:

``encode_cell(cell)``
    Encode a cell id (0..4095) as a fixed 2-character string, most
    significant nibble first.

``encode_direction(direction)``
    Encode a direction id (0..7) as a single character.

A full movement path injected into a ``GA0;1;<charId>;<encoded>``
packet is a chain of ``<cell><direction><cell><direction>...<cell>``
where each ``<cell>`` is the encoded destination of a segment and
each ``<direction>`` is the direction used to enter that segment.
The client sends all intermediate points, not just the endpoints,
to keep the server's path validation happy.

We use :func:`encode_path` (which takes the raw cell list plus a
:class:`DofusMap` for direction computation) when building the
packet from an A* result.

Reference implementations:
- https://github.com/kralamoure/retroproto (Go)
- https://github.com/jomisoac/Bot-Dofus-1.29.1 (C#)
"""

from __future__ import annotations

from typing import List, TYPE_CHECKING

from .constants import HASH_CHARS

if TYPE_CHECKING:
    from ..game.map_data import DofusMap


# 64 characters means each char encodes 6 bits. A cell id fits in 12
# bits (0..4095) so we always emit exactly 2 chars per cell.
_BASE = len(HASH_CHARS)  # 64
_CHAR_TO_INDEX = {c: i for i, c in enumerate(HASH_CHARS)}


def encode_cell(cell: int) -> str:
    """Encode a cell id as exactly 2 :data:`HASH_CHARS` characters."""
    if cell < 0 or cell >= _BASE * _BASE:
        raise ValueError(f"cell {cell} out of range for 2-char encoding")
    hi = cell // _BASE
    lo = cell % _BASE
    return HASH_CHARS[hi] + HASH_CHARS[lo]


def decode_cell(token: str) -> int:
    """Inverse of :func:`encode_cell`. ``token`` must be 2 chars."""
    if len(token) != 2:
        raise ValueError(f"expected 2-char cell token, got {token!r}")
    try:
        hi = _CHAR_TO_INDEX[token[0]]
        lo = _CHAR_TO_INDEX[token[1]]
    except KeyError as exc:
        raise ValueError(f"invalid HASH_CHARS token: {token!r}") from exc
    return hi * _BASE + lo


def encode_direction(direction: int) -> str:
    """Encode a direction id (0..7) as a single character."""
    if direction < 0 or direction >= _BASE:
        raise ValueError(f"direction {direction} out of range")
    return HASH_CHARS[direction]


def decode_direction(token: str) -> int:
    """Inverse of :func:`encode_direction`. ``token`` must be 1 char."""
    if len(token) != 1:
        raise ValueError(f"expected 1-char direction token, got {token!r}")
    try:
        return _CHAR_TO_INDEX[token]
    except KeyError as exc:
        raise ValueError(f"invalid HASH_CHARS direction: {token!r}") from exc


def encode_path(path: List[int], dmap: "DofusMap") -> str:
    """Encode a cell path (start..goal) for a ``GA0;1`` injection.

    The returned string starts with the encoded origin cell and is
    followed by pairs of ``<direction><cell>`` for every subsequent
    step in *path*. All cells must be walking-adjacent to the
    previous one; non-adjacent transitions raise :class:`ValueError`.

    ``path`` must contain at least one cell. A single-cell path is a
    no-op and encodes to just the cell id.
    """
    if not path:
        raise ValueError("encode_path requires at least one cell")

    out: List[str] = [encode_cell(path[0])]
    for i in range(1, len(path)):
        direction = dmap.direction_between(path[i - 1], path[i])
        out.append(encode_direction(direction))
        out.append(encode_cell(path[i]))
    return "".join(out)


def decode_path(encoded: str) -> List[int]:
    """Decode a ``GA0;1`` path string into a list of cell ids.

    This is the inverse of :func:`encode_path` up to the intermediate
    direction bytes, which it drops (direction is implied by the
    consecutive cell pair). Useful for parsing server-side movement
    echoes in the MITM proxy.
    """
    if not encoded:
        return []
    # 2 chars cell, then repeat (1 char dir + 2 chars cell).
    if len(encoded) < 2 or (len(encoded) - 2) % 3 != 0:
        raise ValueError(f"malformed encoded path: {encoded!r}")
    cells: List[int] = [decode_cell(encoded[0:2])]
    i = 2
    while i < len(encoded):
        # Skip the direction char at index i, read the 2-char cell
        # that follows.
        cells.append(decode_cell(encoded[i + 1:i + 3]))
        i += 3
    return cells
