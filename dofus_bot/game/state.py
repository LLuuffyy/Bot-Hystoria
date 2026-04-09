"""Shared mutable game state.

Updated by packet handlers, read by the scripting layer. All mutations
happen from the asyncio event loop, so no explicit locking is needed
(single-threaded cooperative concurrency).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Actor:
    """Something on the current map: player, monster group, NPC, etc."""

    actor_id: int
    cell_id: int = -1
    name: str = ""
    level: int = 0
    is_monster: bool = False
    is_player: bool = False


@dataclass
class FightEntity:
    """An entity inside the current fight (ally or enemy)."""

    entity_id: int
    cell_id: int = -1
    hp: int = 0
    max_hp: int = 0
    ap: int = 0
    mp: int = 0
    is_enemy: bool = True


@dataclass
class Character:
    """The bot's own character. Populated from ASK / Ow / stat packets."""

    character_id: int = 0
    name: str = ""
    level: int = 0
    hp: int = 0
    max_hp: int = 0
    ap: int = 6
    mp: int = 3
    cell_id: int = -1
    kamas: int = 0


@dataclass
class GameState:
    character: Character = field(default_factory=Character)

    # Map
    current_map_id: int = 0
    actors: Dict[int, Actor] = field(default_factory=dict)

    # Fight
    in_fight: bool = False
    my_turn: bool = False
    fight_id: int = 0
    fight_entities: Dict[int, FightEntity] = field(default_factory=dict)

    # Session
    connected: bool = False

    def reset_map(self, new_map_id: int) -> None:
        self.current_map_id = new_map_id
        self.actors.clear()

    def reset_fight(self) -> None:
        self.in_fight = False
        self.my_turn = False
        self.fight_id = 0
        self.fight_entities.clear()

    def enemies(self) -> List[FightEntity]:
        return [e for e in self.fight_entities.values() if e.is_enemy]

    def allies(self) -> List[FightEntity]:
        return [e for e in self.fight_entities.values() if not e.is_enemy]
