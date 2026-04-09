"""Python-side API exposed to Lua scripts as the ``bot`` global.

The class is intentionally small: every method maps to either a read
from the shared :class:`GameState` or a packet injection via the MITM
proxy. Higher-level helpers (fight rotations, farm loops) are built
in Lua on top of these primitives.

Thread-safety note
------------------

Lua scripts run in a dedicated worker thread created by
:class:`dofus_bot.scripting.engine.LuaEngine`. The asyncio event loop
where :class:`DofusProxy` lives runs on the main thread. All methods
here that need to touch asyncio (packet injection, ``wait``) must
schedule the work on the main loop via
``asyncio.run_coroutine_threadsafe``. They do NOT call ``.result()``
with an indefinite timeout - a reasonable upper bound avoids wedging
the script if the proxy closes while Lua is mid-call.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..game.map_data import DofusMap
from ..game.pathfinding import astar
from ..game.state import GameState
from ..protocol.path import encode_path

if TYPE_CHECKING:  # avoid circular + optional imports
    from ..network.proxy import DofusProxy

logger = logging.getLogger(__name__)

# Upper bound (seconds) for any single injection scheduled on the
# asyncio loop. The proxy is normally idle and these return almost
# instantly, but we want to make sure we never wedge the Lua thread
# indefinitely if the proxy gets stuck.
_INJECT_TIMEOUT = 5.0


class _CharacterView:
    """Read-only view over :class:`Character` exposed to Lua."""

    def __init__(self, state: GameState) -> None:
        self._state = state

    # lupa maps ``obj.foo`` on Lua side to Python attribute lookup,
    # so every field just delegates to the underlying Character.
    @property
    def id(self) -> int:
        return self._state.character.character_id

    @property
    def name(self) -> str:
        return self._state.character.name

    @property
    def level(self) -> int:
        return self._state.character.level

    @property
    def hp(self) -> int:
        return self._state.character.hp

    @property
    def max_hp(self) -> int:
        return self._state.character.max_hp

    @property
    def ap(self) -> int:
        return self._state.character.ap

    @property
    def mp(self) -> int:
        return self._state.character.mp

    @property
    def cell(self) -> int:
        return self._state.character.cell_id

    @property
    def map_id(self) -> int:
        return self._state.current_map_id

    @property
    def kamas(self) -> int:
        return self._state.character.kamas


class _FightView:
    """Read-only view over the current fight exposed to Lua."""

    def __init__(self, state: GameState) -> None:
        self._state = state

    @property
    def is_active(self) -> bool:
        return self._state.in_fight

    @property
    def my_turn(self) -> bool:
        return self._state.my_turn

    @property
    def fight_id(self) -> int:
        return self._state.fight_id

    @property
    def enemies(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": e.entity_id,
                "cell": e.cell_id,
                "hp": e.hp,
                "max_hp": e.max_hp,
                "ap": e.ap,
                "mp": e.mp,
            }
            for e in self._state.enemies()
        ]

    @property
    def allies(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": e.entity_id,
                "cell": e.cell_id,
                "hp": e.hp,
                "max_hp": e.max_hp,
                "ap": e.ap,
                "mp": e.mp,
            }
            for e in self._state.allies()
        ]


class _MapView:
    """Read-only view over the current map exposed to Lua."""

    def __init__(self, state: GameState) -> None:
        self._state = state

    @property
    def id(self) -> int:
        return self._state.current_map_id

    @property
    def actors(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": a.actor_id,
                "cell": a.cell_id,
                "name": a.name,
                "level": a.level,
                "is_monster": a.is_monster,
                "is_player": a.is_player,
            }
            for a in self._state.actors.values()
        ]

    @property
    def monsters(self) -> List[Dict[str, Any]]:
        return [
            {"id": a.actor_id, "cell": a.cell_id, "name": a.name}
            for a in self._state.actors.values()
            if a.is_monster
        ]

    @property
    def players(self) -> List[Dict[str, Any]]:
        return [
            {"id": a.actor_id, "cell": a.cell_id, "name": a.name}
            for a in self._state.actors.values()
            if a.is_player
        ]


class BotAPI:
    """Façade presented to Lua as the global ``bot``.

    A single instance is created per :class:`LuaEngine`. The object
    holds references to the shared :class:`GameState` and the
    :class:`DofusProxy`, so state reads are always live and packet
    injections land in the current session.
    """

    def __init__(
        self,
        state: GameState,
        proxy: "DofusProxy",
        loop: asyncio.AbstractEventLoop,
        engine: Any,  # LuaEngine (avoid circular import)
        dmap: Optional[DofusMap] = None,
    ) -> None:
        self._state = state
        self._proxy = proxy
        self._loop = loop
        self._engine = engine

        # Shared topology used by the pathfinder. Can be swapped at
        # runtime by scripts that know a map has unusual dimensions.
        self._dmap: DofusMap = dmap or DofusMap()

        # Lua-visible nested objects. Lupa exposes ``bot.character.hp``
        # as Python attribute access, so the script can write the usual
        # OO-style chain without extra glue.
        self.character = _CharacterView(state)
        self.fight = _FightView(state)
        self.map = _MapView(state)

    # ------------------------------------------------------------------ #
    # Control flow helpers
    # ------------------------------------------------------------------ #

    def log(self, message: Any) -> None:
        """``bot:log(msg)`` - write a line to logs/dofus_bot.log."""
        logger.info("[lua] %s", message)

    def wait(self, seconds: float) -> None:
        """``bot:wait(sec)`` - sleep the Lua worker thread.

        The call happens entirely in the Lua worker thread so the
        asyncio loop keeps running while we sleep. We cap sleeps at
        short chunks so that stop requests from :class:`LuaEngine`
        are honoured quickly.
        """
        if seconds <= 0:
            return
        chunk = 0.2
        remaining = float(seconds)
        while remaining > 0:
            if self._engine.should_stop():
                raise RuntimeError("bot stopped")
            time.sleep(min(chunk, remaining))
            remaining -= chunk

    def on(self, event: str, callback: Any) -> None:
        """``bot:on(event, function() ... end)`` - subscribe to an event."""
        self._engine.register_event(event, callback)

    # ------------------------------------------------------------------ #
    # Raw / low level packet injection
    # ------------------------------------------------------------------ #

    def send(self, message: str) -> None:
        """``bot:send("GA903")`` - inject a raw packet toward the server."""
        self._dispatch(self._proxy.send_to_server(str(message)))

    def send_client(self, message: str) -> None:
        """Inject a raw packet toward the local Dofus client (rare)."""
        self._dispatch(self._proxy.send_to_client(str(message)))

    # ------------------------------------------------------------------ #
    # High-level combat primitives
    # ------------------------------------------------------------------ #

    def cast(self, spell_id: int, target_cell: int) -> None:
        """``bot:cast(spellId, targetCell)`` - cast a spell on a cell.

        Sends ``GA300;<spellId>;<targetCell>``. The cell may be the
        caster's own cell (self buff) or any reachable tile.
        """
        packet = f"GA300;{int(spell_id)};{int(target_cell)}"
        self.send(packet)

    def cast_on_enemy(self, spell_id: int, enemy_id: int) -> bool:
        """Resolve an enemy's current cell and cast on it.

        Returns ``True`` on success, ``False`` if the enemy is unknown.
        """
        enemy = self._state.fight_entities.get(int(enemy_id))
        if enemy is None or enemy.cell_id < 0:
            return False
        self.cast(spell_id, enemy.cell_id)
        return True

    def end_turn(self) -> None:
        """``bot:end_turn()`` - pass the turn (GA903)."""
        self.send("GA903")

    def engage(self, monster_group_id: int) -> None:
        """``bot:engage(groupId)`` - request a fight against a monster group.

        Sends ``GA900;<groupId>``. The ``groupId`` is the actor id of
        a monster group sitting on the current map.
        """
        self.send(f"GA900;{int(monster_group_id)}")

    # ------------------------------------------------------------------ #
    # Movement primitives
    # ------------------------------------------------------------------ #

    def set_map_size(self, width: int, height: int) -> None:
        """Override the default 14x40 grid used by the pathfinder.

        Most Amakna maps fit the default. Call this from a script if
        you know the current map has a custom layout (Incarnam
        tutorial rooms, some dungeons, ...).
        """
        self._dmap = DofusMap(width=int(width), height=int(height))

    def block_cells(self, cells: Any) -> None:
        """Mark one or more cells as non-walkable for the pathfinder.

        ``cells`` may be a single integer or a Lua table of integers.
        """
        self._dmap.block(_iter_cells(cells))

    def unblock_cells(self, cells: Any) -> None:
        """Opposite of :meth:`block_cells`."""
        self._dmap.unblock(_iter_cells(cells))

    def path_to(self, target_cell: int) -> List[int]:
        """Compute an A* path from the current cell to *target_cell*.

        Returns a list of cell ids (start included, goal included)
        or an empty list if no path is found.
        """
        start = self._state.character.cell_id
        if start < 0:
            return []
        return astar(self._dmap, start, int(target_cell))

    def move_to(self, target_cell: int) -> bool:
        """``bot:move_to(cellId)`` - walk to *target_cell* on the current map.

        Computes a path with A* and injects a single ``GA0;1`` packet
        with the full encoded path. Returns ``True`` if the packet was
        dispatched, ``False`` if the bot has no known position, no
        character id, or if no path exists.

        This method does NOT wait for the server to confirm the walk.
        Use ``bot:wait(seconds)`` or the ``character_moved`` event to
        synchronise follow-up actions.
        """
        target = int(target_cell)
        char_id = self._state.character.character_id
        if char_id <= 0:
            logger.debug("move_to: character id unknown yet")
            return False
        path = self.path_to(target)
        if not path or len(path) < 2:
            logger.debug(
                "move_to: no path from %d to %d",
                self._state.character.cell_id, target,
            )
            return False
        try:
            encoded = encode_path(path, self._dmap)
        except ValueError as exc:
            logger.debug("move_to: could not encode path: %s", exc)
            return False
        packet = f"GA0;1;{char_id};{encoded}"
        self.send(packet)
        return True

    def move_to_xy(self, x: int, y: int) -> bool:
        """``bot:move_to_xy(x, y)`` - same as :meth:`move_to` but by coords."""
        return self.move_to(self._dmap.xy_to_cell(int(x), int(y)))

    def distance(self, cell_a: int, cell_b: int) -> int:
        """``bot:distance(a, b)`` - Chebyshev distance on the grid."""
        return self._dmap.distance(int(cell_a), int(cell_b))

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def closest_enemy(self) -> Optional[Dict[str, Any]]:
        """Return the enemy closest (by cell id difference) to us, or nil."""
        enemies = self._state.enemies()
        if not enemies:
            return None
        my_cell = self._state.character.cell_id
        enemies_with_cell = [e for e in enemies if e.cell_id >= 0]
        if not enemies_with_cell:
            return None
        closest = min(
            enemies_with_cell,
            key=lambda e: abs(e.cell_id - my_cell),
        )
        return {
            "id": closest.entity_id,
            "cell": closest.cell_id,
            "hp": closest.hp,
            "ap": closest.ap,
            "mp": closest.mp,
        }

    def weakest_enemy(self) -> Optional[Dict[str, Any]]:
        """Return the enemy with the lowest HP, or nil."""
        enemies = [e for e in self._state.enemies() if e.hp > 0]
        if not enemies:
            return None
        weakest = min(enemies, key=lambda e: e.hp)
        return {
            "id": weakest.entity_id,
            "cell": weakest.cell_id,
            "hp": weakest.hp,
            "ap": weakest.ap,
            "mp": weakest.mp,
        }

    # ------------------------------------------------------------------ #
    # Internal: schedule a coroutine on the main asyncio loop
    # ------------------------------------------------------------------ #

    def _dispatch(self, coro) -> None:
        """Run an asyncio coroutine on the main loop and block until done.

        Only used by packet injection helpers. If the proxy is closed
        the underlying coroutine returns quickly, so the timeout is
        just a safety net.
        """
        try:
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
            future.result(timeout=_INJECT_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning("Packet injection timed out")
        except Exception:
            logger.exception("Packet injection failed")


def _iter_cells(cells: Any):
    """Accept an int or a Lua/Python iterable of ints and yield ints."""
    if isinstance(cells, (int, float)):
        yield int(cells)
        return
    # Lua tables come through lupa as objects with ``values()``.
    values = getattr(cells, "values", None)
    if callable(values):
        for v in values():
            try:
                yield int(v)
            except (TypeError, ValueError):
                continue
        return
    try:
        for v in cells:  # plain iterable / list
            try:
                yield int(v)
            except (TypeError, ValueError):
                continue
    except TypeError:
        return
