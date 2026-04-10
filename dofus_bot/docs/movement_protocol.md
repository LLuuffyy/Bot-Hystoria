# Movement protocol — Dofus 1.29

Consolidated movement findings from the Cadernis scrape. Covers
the isometric grid geometry, the A* pathfinding constraints, the
`GA0` / `GA001` / `GKK0` wire packets, and the critical **GKK0
timing enforcement** that catches naive bots.

This doc is the reference for:

- `dofus_bot/game/pathfinding.py` — A* on the iso grid
- `dofus_bot/protocol/path.py` — cell encoding / decoding
- `dofus_bot/handlers/movement_handler.py` — GA0 parsing
- `dofus_bot/scripting/api.py` — `bot:move_to(cell)` entry point

---

## 1. Grid geometry

A Dofus 1.29 map is a **losange** (diamond) grid:

```
Width  W = 14 cells (typical Amakna map)
Height H = 40 cells
Total  N = W * H * 2 = 560 cells (cell IDs 0 to 559 inclusive)
```

Each **row** of the grid alternates between two sub-rows offset by
half a cell horizontally (iso projection). This means the neighbor
lookup depends on the parity of the **row index** `i`.

From **habbablekebab128**, Cadernis thread **#2381** (*Tutoriel
déplacements Dofus 1.29*) — verbatim from the code block:

```python
# Odd rows (i % 2 == 1)
odd_neighbors = [
    (0,  1),  # right
    (0, -1),  # left
    (1,  0),  # bottom-right
    (-1, 0),  # top-right
    (1,  1),  # bottom
    (1, -1),  # ???
    (0,  2),  # 2 cells right
    (0, -2),  # 2 cells left
]

# Even rows (i % 2 == 0)
pair_neighbors = [
    (0,  1),
    (0, -1),
    (1,  0),
    (-1, 0),
    (-1, 1),
    (-1,-1),
    (0,  2),
    (0, -2),
]
```

The `(0, 2)` / `(0, -2)` pairs are the **2-cell horizontal jumps**
that look weird but are legit in Dofus 1.29 because of how the cells
map back to rendered tiles.

### Cell ↔ (i, j) conversion

From the wiki + confirmed in thread **#2239** (*Dofus 1.29 taille des
cells*):

```
cell_id = i * (W * 2) + j    # where j is 0..(W*2)-1
i = cell_id // (W * 2)
j = cell_id %  (W * 2)
```

For a 14-wide map:
- `cell_id = 0..27`    → row 0, cols 0..27
- `cell_id = 28..55`   → row 1, cols 0..27
- `cell_id = 559`      → row 19, col 27 (last cell of half-height)

Wait — the math doesn't match 560 = 14 * 40 unless each row contains
**28 cells** (not 14). This is the iso projection artifact: the W=14
logical columns unfold into 2*W=28 physical cells per row. Correct
formulation:

```
cells_per_row = W * 2 = 28
num_rows      = H = 20    # physical row count
total_cells   = cells_per_row * num_rows = 560
```

The "40" from the old folklore is actually the **tile count along the
diagonal**, not a row count. Our `game/map_data.py` uses `width=14,
height=40` as the API contract, but internally computes the flat
cell index the same way `i * 28 + j`.

## 2. Line of sight + walkability

- **Line of sight (LoS)** — thread **#2519** (*gestion des combats*)
  + Arakne's Java reference. Standard Bresenham-like iteration on the
  `(i, j)` pairs, with cell blocked if the `loS_blocker` flag is set
  in the map data.
- **Walkability** — comes from the GDM (Game Data Map) payload, each
  cell has a `movement_lock` flag. In our `map_data.py` we default
  everything to walkable because we don't yet parse the full GDM
  compression (thread **#1903** + **#2225**).

We currently skip walkability extraction — the bot's Lua API exposes
`bot:block_cells({123, 456})` so the user can mark obstacles by
hand when a route hits a dead end.

## 3. Diagonal moves — combat rules

From **zahid98**, thread **#1976** (*les déplacements en combat*):

> "Attention: en combat, les déplacements diagonaux sont INTERDITS.
> Si tu envoies un path avec une diagonale, le serveur te met en
> erreur et annule ton tour. Hors combat c'est OK."

Concrete: the A* neighbor set must be **filtered** in combat mode
to exclude the diagonal offsets (the 5th and 6th entries in each
table above). Our `pathfinding.py` has a `combat_mode` flag that
does this.

## 4. Wire packets

### Out-of-combat movement — `GA0`

```
C → S: GA0;1;<charId>;<encoded_path>\x00
```

- `0` = movement action category
- `1` = "commit a movement path"
- `<charId>` = our character ID (learned from `ASK`)
- `<encoded_path>` = base64-ish compressed path (see §5)

The server replies with a `GA0;1;<charId>;<same_path>` broadcast to
everyone on the map, including us. The client uses this echo to
animate the character.

### Walk commit — `GA001`

**1.48 Electron addition** (LuthTeur, thread #3258). The old 1.29
emulators don't require this, but the official Ankama Retro backend
does.

```
C → S: GA001;<actorId>;<cellId>\x00
```

Note the **actor ID** (not character ID). LuthTeur lost 2 weeks on
this one because the two numeric IDs are different after you select
your character.

**Our TODO**: test whether Hystoria's server requires `GA001`. If so,
our `movement_handler.py` needs to learn the actor ID from the `GM`
packet and echo a `GA001` after each `GA0`. If not, we can skip it.

### Map change — `GA0;0`

```
C → S: GA0;0;<exit_cell>\x00
```

The exit cell is one of the map's edge cells (configured in the
GDM). Server replies with a map transition, then a new `GDM` for
the destination map.

### In-combat movement — `GA0;1` but within PM budget

Same wire format as out-of-combat. The server checks:
1. Path length ≤ remaining PM.
2. No diagonals.
3. Every cell is LoS-reachable from the previous.
4. The last cell is not occupied.

If any fails, the server silently ignores the packet. **This is
exactly Duke Toland's "packets ignored" bug from thread #3240**:
the bot's path was internally valid but didn't match the server's
pathfinding cost model, so the server rejected silently.

### `GKK0` — the "I'm ready" heartbeat

From **salesprendes**, thread **#2381**:

> "Ne pas oublier d'envoyer GKK0 à la fin de chaque action de
> déplacement. Sinon le serveur te marque comme AFK et peut bloquer
> le personnage."

```
C → S: GKK0\x00
```

Sent after:
- Every completed move.
- Every map change (once the new GDM is fully received).
- Every combat turn end.

This is the **anti-bot heartbeat**. Two things make it non-trivial:

1. **Timing**. salesprendes' warning: "Si tu l'envoies trop vite,
   le serveur te flag." The client sends it approximately
   `movement_duration + 50ms` after the `GA0` commit — i.e. AFTER
   the character is rendered as having arrived.
2. **Movement duration** depends on the path length and the movement
   mode (walk vs run):

| Mode | Direction   | Seconds per cell |
| ---- | ----------- | ---------------- |
| RUN  | Horizontal  | 0.3              |
| RUN  | Vertical    | 0.2              |
| RUN  | Diagonal    | 0.2              |
| WALK | Horizontal  | 0.75             |
| WALK | Vertical    | 0.5              |
| WALK | Diagonal    | 0.5              |

Source: thread **#2230** (*compréhension du temps pathfinding 1.29.1*).
Sum the per-cell duration along the path to get the total, then
delay `GKK0` by that amount + ~50ms jitter.

**Our current implementation**: `movement_handler.py` sends `GKK0`
immediately, which is wrong. TODO: add a `GkkScheduler` that times
the heartbeat correctly.

## 5. Path encoding / decoding

Each cell is encoded as **2 characters** from a 64-char alphabet:

```
HASH_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
```

A cell ID `c` in [0, 4095] is encoded as:

```
cell_encoded = HASH_CHARS[c // 64] + HASH_CHARS[c % 64]
```

A path is a sequence of `(direction, target_cell)` tuples, where
`direction` is a single char from the alphabet that encodes one of
the 8 neighbor offsets (same table as §1). The full encoding is:

```
encoded_path = <dir_char><cell_2chars><dir_char><cell_2chars>...
```

So 3 waypoints = 9 characters. A typical 5-cell move is 15 chars.

Reference code: `dofus_bot/protocol/path.py` (already implemented +
unit-tested in `test_path_encoding.py`).

## 6. Silent-rejection pitfalls (Duke Toland's bug)

Thread **#3240** (*mitm-dofus-retro-packets-send-ignores*) is a
goldmine for what NOT to do:

1. **Wrong character ID**. The `GA0` packet needs the character's
   **in-game ID** (from `ASK`), not the account ID (from `AL`). Our
   `stats_handler.py` stores both, but the old version mixed them
   up and `move_to` silently failed.
2. **Stale cell ID**. If you computed the path before the `GDM`
   handshake completed, you're starting from a stale cell and every
   subsequent move is off by one. Always wait for `character_ready`
   + `map_change` before planning.
3. **Diagonal in combat**. See §3.
4. **Over-budget PM in combat**. Server silently drops.
5. **Obstacle mid-path**. The server recomputes the path server-side
   and rejects if any cell is blocked.
6. **GKK0 too fast**. Server flags for anti-bot review.

## 7. Multi-map pathfinding (WorldGraph)

Not yet implemented. The WorldGraph is a precomputed map-to-map
adjacency table that tells you which edge cells transition to which
target maps. Threads:

- **#2842** — worldgraph-projet-de-pathfinding
- **#2773** — world-path-finder-help
- **Arakne/ArakneUtils** — `worldgraph` package in Java

The simplest intermediate solution: hardcode the map IDs of the
route in YAML (`data/routes/bouftous.yaml`) and the exit-cell IDs
for each transition.

## 8. References

- **Thread #2381** — Tutoriel déplacements Dofus 1.29 (habbablekebab128)
- **Thread #2230** — Compréhension du temps pathfinding 1.29.1
- **Thread #1976** — Les déplacements en combat (zahid98)
- **Thread #2239** — Dofus 1.29 taille des cells
- **Thread #2197** — Taille des cellules d'une map
- **Thread #2095** — D2.0 distinguer les cellules d'un escalier
- **Thread #1903** — Compréhension cryptage map 1.29
- **Thread #2225** — Décryptage des maps 1.29
- **Thread #3051** — Cellules disponibles dans une map
- **Thread #3240** — MITM Dofus Retro packets send ignorés par serveur
- **Thread #1650** — MITM 1.29 déplacements (Caliphe wire log)
- **Thread #3258** — Dofus Retro 1.47.22 ticket AT (LuthTeur GA001)
- **Thread #3265** — Grille map bot Dofus serveur privé
- **Thread #3260** — Détection position de la map actuelle
- **Thread #2842** — Worldgraph projet de pathfinding
- **Arakne/ArakneUtils** — Java pathfinding reference
