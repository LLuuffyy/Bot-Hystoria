# dofus_bot

Bot MITM pour le serveur prive Dofus 1.29 Retro Hystoria.

Le bot se place **entre ton client Dofus et le serveur Hystoria**. Tu
joues normalement (tu vois la fenetre de jeu), et le bot observe tous
les paquets reseau pour automatiser ce que tu veux via des scripts Lua.

```
  Client Dofus  <---->  dofus_bot (proxy)  <---->  serveur Hystoria
       ^                       |
       |                       v
   tu vois            scripts Lua automatisent
   ton perso          combats / farm / soins
```

**Reserve a ton propre serveur prive, pour des tests.**

## Etat actuel

- [x] Proxy MITM TCP (`network/proxy.py`)
- [x] Framing \\x00 + decodage latin-1
- [x] Routeur de messages par prefixe
- [x] Parsers de base : entree de map (`GDM`), acteurs (`GM`), combat (`GJK`/`GTS`/`GTM`/`GTE`/`GE`)
- [x] Mode `--proxy` : lance le proxy et log tout le trafic
- [x] API Lua (`bot.character.hp`, `bot:cast(...)`, `bot:on("turn_start", ...)`)
- [x] Injection de paquets (`GA300` sort, `GA900` combat, `GA903` fin de tour, raw `bot:send`)
- [x] Bus d'evenements (`fight_start`, `turn_start`, `hp_low`, `map_change`, ...)
- [x] Recharge des scripts a chaud (surveillance du mtime)
- [x] Stats handler : remplit `character.id/name/level/hp/ap/mp` via `ASK`/`As`
- [x] Pathfinding A* sur grille losange + encodage du path
- [x] Injection de deplacement (`GA0;1;charId;encodedPath`) via `bot:move_to`
- [x] Suivi des walks (GA0) : met a jour la cell des acteurs et emet `character_moved`
- [ ] Moteur de rotation de sorts declaratif (turns[1] = {...}, turns[2] = {...})
- [ ] Auto-heal hors combat (utilisation d'items)
- [ ] Pathfinding multi-maps (WorldGraph)

## Setup Windows (mode simple)

**Prerequis** : [Python 3.11+](https://www.python.org/downloads/) installe
avec l'option "Add Python to PATH".

### 1. Installation

Double-clique sur `install.bat` a la racine du projet. Il cree un
environnement virtuel et installe les dependances.

### 2. Configuration

```
copy .env.example .env
```

Puis ouvre `.env` avec le Bloc-notes. La seule section qui nous
interesse est :

```
DOFUS_PROXY_HOST=127.0.0.1
DOFUS_PROXY_PORT=5555
DOFUS_UPSTREAM_HOST=162.19.127.155
DOFUS_UPSTREAM_PORT=5555
```

Par defaut le proxy ecoute sur `127.0.0.1:5555` et forwarde vers
**`162.19.127.155:5555`** (serveur de jeu Hystoria V5, identifie via
`netstat` pendant qu'un vrai client Hystoria etait connecte).

Si l'IP change un jour (maintenance, nouveau serveur...), retrouve-la
en lancant le client Hystoria jusqu'a l'ecran de selection de perso
puis en tapant dans `cmd` :

```
netstat -n | findstr :5555
```

La ligne affichee est du style :

```
TCP    192.168.1.16:61008    162.19.127.155:5555    ESTABLISHED
```

→ la partie droite (`162.19.127.155:5555`) est le serveur reel.
Mets l'IP dans `DOFUS_UPSTREAM_HOST` et le port dans
`DOFUS_UPSTREAM_PORT`.

### 3. Redirection du client Dofus vers le proxy

Le client Dofus doit se connecter a `127.0.0.1` au lieu de
`play-hystoria.net`. La methode la plus simple : modifier le fichier
`hosts` de Windows.

1. Ouvre le Bloc-notes **en tant qu'administrateur** (clic droit ->
   Executer en tant qu'administrateur)
2. Ouvre le fichier : `C:\Windows\System32\drivers\etc\hosts`
3. Ajoute tout en bas cette ligne :

   ```
   127.0.0.1    play-hystoria.net
   ```

4. Sauvegarde et ferme

**Desactive cette ligne (en la prefixant par `#`) quand tu veux jouer
sans le proxy.**

### 4. Lancer le proxy

Double-clique sur `run_proxy.bat`. Tu devrais voir :

```
============================================================
Dofus MITM proxy
  listen   : 127.0.0.1:5555  <-- point your Dofus client here
  upstream : play-hystoria.net:5555
  script   : (none)
============================================================
Waiting for the Dofus client to connect...
```

### 5. Lancer Dofus et te connecter

Laisse `run_proxy.bat` ouvert et lance ton client Dofus normalement.
Connecte-toi avec ton compte. Tu devrais voir dans la fenetre du proxy
des lignes du type :

```
Client connected from ('127.0.0.1', 54321)
Upstream connected to play-hystoria.net:5555
Entered map 7411
Fight joined: GJK1
Turn 1 start (entity 12345, mine=True)
```

Si tu vois ca, **le bot comprend ce qui se passe dans le jeu**. C'est
la base sur laquelle les scripts de farm vont s'executer.

## Troubleshooting

### "Connection refused" quand tu lances Dofus

Le proxy n'est pas demarre. Lance `run_proxy.bat` d'abord.

### Le client Dofus se connecte mais ne fait rien

Le port d'upstream est sans doute faux. Regarde dans la fenetre du
proxy : si tu vois "Client connected" mais pas "Upstream connected",
c'est que le bot n'arrive pas a joindre le vrai serveur. Verifie
`DOFUS_UPSTREAM_PORT`.

### Le proxy reste bloque sur "Waiting for client"

Le client Dofus ne tente pas de se connecter au proxy. Verifications :
- Le fichier `hosts` a bien ete modifie (et sauvegarde)
- Tu as **ferme et relance** le client Dofus apres la modif de `hosts`
- Pas de cache DNS : ouvre `cmd` admin et tape `ipconfig /flushdns`

### Je vois les paquets mais mon perso ne bouge pas

Par defaut le bot est en mode "observation" : il log tout mais
n'injecte aucun paquet. Pour qu'il agisse, il faut charger un script :

```
python -m dofus_bot --proxy --script examples/explore.lua
```

Si le script tourne mais que le perso reste immobile, verifie dans
les logs que le `character_id` et la `cell_id` sont connus (attends
l'evenement `character_ready` avant de bouger).

## Scripts Lua

Le moteur Lua (via [`lupa`](https://pypi.org/project/lupa/)) charge un
fichier `.lua` depuis `dofus_bot/data/scripts/` et l'execute dans un
thread dedie. Les scripts utilisent l'objet global `bot` pour lire
l'etat du jeu et injecter des paquets a travers le proxy MITM.

### Lancer un script

```
python -m dofus_bot --proxy --script examples/hello.lua
```

Ou via `.env` :

```
DOFUS_SCRIPT=examples/combat_cra.lua
```

### API exposee

Lecture d'etat (tout en direct, mis a jour par les handlers) :

```lua
bot.character.hp, bot.character.max_hp
bot.character.ap, bot.character.mp
bot.character.cell, bot.character.map_id
bot.character.name, bot.character.level, bot.character.kamas

bot.fight.is_active, bot.fight.my_turn
bot.fight.enemies    -- {{id, cell, hp, max_hp, ap, mp}, ...}
bot.fight.allies

bot.map.id
bot.map.actors       -- tous les acteurs
bot.map.monsters     -- seulement les monstres
bot.map.players      -- seulement les joueurs
```

Actions (injectent directement dans la session MITM) :

```lua
bot:log("message")                       -- ecrit dans logs/dofus_bot.log
bot:wait(seconds)                        -- pause du script

bot:cast(spell_id, target_cell)          -- GA300;spellId;cell
bot:cast_on_enemy(spell_id, enemy_id)    -- resout la cell puis GA300
bot:end_turn()                           -- GA903
bot:engage(monster_group_id)             -- GA900;groupId
bot:send("GA300;161;234")                -- paquet brut (echappatoire)

bot:move_to(cell_id)                     -- A* + GA0;1;charId;encodedPath
bot:move_to_xy(x, y)                     -- idem, en coordonnees grille
bot:path_to(cell_id)                     -- calcule le chemin sans l'envoyer
bot:distance(cell_a, cell_b)             -- distance de Chebyshev
bot:block_cells({123, 456})              -- marque des cells non-walkables
bot:unblock_cells({123})                 -- annule un block precedent
bot:set_map_size(width, height)          -- override la taille 14x40 par defaut

bot:closest_enemy()                      -- helper
bot:weakest_enemy()                      -- helper
```

Notes sur le deplacement :

- `bot:move_to` envoie **un seul** paquet au serveur, contenant tout le
  chemin encode. C'est comme cliquer une fois avec la souris en jeu.
- Le perso a besoin d'un `character_id` connu (recu via `ASK`) **et**
  d'une `cell_id` connue (recue via `GDM` au moment d'entrer sur la
  map). Tant que l'un ou l'autre manque, `move_to` retourne `false`
  sans rien envoyer.
- Le pathfinder utilise une grille losange 14x40 par defaut. La plupart
  des maps Amakna fittent. Si tu tombes sur une map plus petite ou plus
  grande (Incarnam, donjons...), appelle `bot:set_map_size(w, h)` avant
  de replanifier.
- La walkability n'est pas extraite des paquets serveur pour l'instant :
  toutes les cases sont reputees walkables sauf celles marquees via
  `bot:block_cells`. C'est suffisant pour des deplacements sur des maps
  ouvertes, pas pour slalomer entre des obstacles.

Evenements (un meme script peut en enregistrer autant qu'il veut) :

```lua
bot:on("fight_start",      function(data) ... end)
bot:on("fight_end",        function(data) ... end)
bot:on("turn_start",       function(data) ... end)  -- data.turn, data.entity_id
bot:on("turn_end",         function(data) ... end)
bot:on("map_change",       function(data) ... end)  -- data.map_id
bot:on("actors_update",    function(data) ... end)  -- data.count
bot:on("hp_low",           function(data) ... end)  -- data.hp, data.max_hp
bot:on("character_ready",  function(data) ... end)  -- data.id, data.name, data.level
bot:on("character_moved",  function(data) ... end)  -- data.from, data.to, data.path
```

### Exemples fournis

- `examples/hello.lua` - sanity-check, log un message et reagit a
  quelques evenements.
- `examples/combat_cra.lua` - rotation basique de Cra : cible le plus
  faible, spam Fleche Magique tant qu'il reste du PA, passe le tour.
- `examples/auto_heal.lua` - reagit a l'evenement `hp_low` (en dessous
  de 40 pct de la vie max).
- `examples/farm_bouftous.lua` - engage automatiquement le monstre le
  plus proche a chaque arrivee sur une nouvelle map.
- `examples/explore.lua` - fait tourner le perso en rectangle sur la
  map courante pour tester le pathfinder et `character_moved`.

### Hot reload

Le moteur surveille le `mtime` du fichier source toutes les secondes.
Quand tu sauvegardes ton script, il est recharge automatiquement sans
couper la session du client. Pratique pour iterer.

### Sandbox

Les modules Lua dangereux (`os`, `io`, `package`, `debug`, `require`,
`loadfile`, ...) sont retires du runtime avant le chargement du
script. Il reste `math`, `string`, `table`, `coroutine` et `bot`.

## Architecture interne

```
dofus_bot/
  __main__.py             # Entree principale, mode --proxy
  config.py               # .env -> DofusConfig
  logger.py               # Log vers logs/dofus_bot.log

  network/
    connection.py         # TCP asyncio + framing \x00 (reutilise par le proxy)
    proxy.py              # MITM bidirectionnel, API on_client/on_server/send_to_*

  protocol/
    router.py             # Dispatch par prefixe (3 chars avant 2 chars)
    constants.py          # Prefixes connus (HC, GDM, GTS, etc.)
    crypto.py             # Hash mot de passe (garde au cas ou, pas utilise en MITM)

  handlers/
    map_handler.py        # GDM, GM -> GameState + EventBus.map_change
    combat_handler.py     # GJK/GTS/GTM/GTE/GE -> GameState + EventBus.fight_*
    stats_handler.py      # ASK, As -> character.id/name/level/hp/ap/mp + character_ready
    movement_handler.py   # GA0 (walk) -> update cell + EventBus.character_moved

  game/
    state.py              # GameState partage (Character, Actor, FightEntity)
    map_data.py           # DofusMap : grille losange 14x40, neighbors, walkability
    pathfinding.py        # A* admissible (Chebyshev) sur la grille

  protocol/
    path.py               # encode_cell/decode_cell (2 chars) + encode_path/decode_path

  scripting/
    events.py             # EventBus (fight_start, turn_start, hp_low, ...)
    api.py                # BotAPI : etat + actions exposees a Lua
    engine.py             # LuaEngine : thread worker + hot reload
    sandbox.py            # Retire os/io/require du runtime Lua

  data/
    scripts/
      examples/
        hello.lua         # Sanity check
        combat_cra.lua    # Rotation Cra basique
        auto_heal.lua     # Reaction a hp_low
        farm_bouftous.lua # Engage auto le monstre le plus proche
        explore.lua       # Demo pathfinding : walk en rectangle
      my_scripts/         # Tes propres scripts (gitignored)
```
