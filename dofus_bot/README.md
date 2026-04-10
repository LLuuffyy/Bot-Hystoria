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
- [x] Strip de la signature Shield `\xf9...\xf9` avant dispatch (`protocol/shield.py`)
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
- [ ] **Signature Shield des paquets injectes** (bloquant pour que `bot:cast`/`bot:move_to`
      soient acceptes par le serveur Hystoria — voir section "Shield" plus bas)
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

### 3. Redirection du client Dofus vers le proxy (hook Frida)

Le client Hystoria V5 (Electron + Flash) utilise une IP codee en
dur dans son bytecode, inaccessible via le fichier `hosts`. On
utilise [Frida](https://frida.re/) pour intercepter l'appel
`ws2_32.dll!connect()` et rediriger la connexion vers le proxy.

**Aucune modification du client Dofus n'est necessaire.**

### 4. Lancer le proxy

Double-clique sur `run_proxy.bat`. Tu devrais voir :

```
============================================================
Dofus MITM proxy
  listen   : 127.0.0.1:5555  <-- point your Dofus client here
  upstream : 162.19.127.155:5555
  script   : (none)
============================================================
Waiting for the Dofus client to connect...
```

### 5. Lancer Dofus (sans se connecter)

Lance `Dofus Retro.exe` normalement. L'ecran de login s'affiche.
**Ne te connecte pas encore.**

### 6. Lancer le hook Frida

Double-clique sur `run_hook.bat` (ou en PowerShell admin) :

```
python -m dofus_bot.hook
```

Tu devrais voir :

```
Attaching Frida to 'Dofus Retro.exe' ...
Hook installed.  connect() calls to 162.19.127.155:5555 will be
redirected to 127.0.0.1:5555.
```

### 7. Se connecter dans Dofus

**Maintenant** connecte-toi avec ton compte. Tu devrais voir dans la
fenetre du proxy des lignes du type :

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

## Shield (anti-cheat Ankama)

Le client Hystoria V5 est base sur l'Electron de Dofus Retro 1.48 qui
embarque un module d'anti-cheat appele **Shield** (dans `main.jsc`).
Shield **signe** chaque paquet sortant avec une chaine AES-256-CBC en
4 etapes. Point crucial : Shield ne **chiffre pas** le corps du
paquet, il ajoute juste une signature en suffixe :

```
<raw_packet>\xf9<base64_iv><base64_ct>
```

Un **seul** marqueur `\xf9` separe le paquet lisible de la signature
binaire. Format confirme contre les 639 paires de captures
`applyPacketToSendPostProcessing` dans
`data/security_api_calls.json` (xkenzzo31/dofus-retro-deobfuscator) :
le marqueur se trouve a la position 0 de la valeur de retour, suivi
immediatement de 24 caracteres de `b64(iv)` (IV 16 octets) puis de
108 caracteres de `b64(ct)` (ciphertext 80 octets apres les 4 etapes
AES + PKCS7). Pas de separateur interne entre `iv` et `ct`, pas de
marqueur en fin.

Le prefixe Dofus 1.29 habituel (`GDM`, `GA`, `GTS`, ...) reste lisible
directement avant le marqueur.

### Cote lecture (fait)

Le proxy appelle `protocol.shield.strip_shield_signature()` sur chaque
fragment avant de le passer au routeur. Si le paquet n'a pas de
signature (ex. ACK, chat, pre-login), le stripper est un no-op. La
premiere fois qu'une signature est detectee, tu verras dans la console :

```
[C>>S] Shield signature detected (stripped 304 bytes, payload=16 bytes).
       Readable mode engaged.
```

En mode `--dump`, chaque ligne est taguee avec la taille de la
signature strippee, ex. `[C>>S] +shield(304) GA0;1;1234;abcd...`.

### Cote injection (en cours)

Le module `protocol/shield_signer.py` implemente la chaine
AES-256-CBC complete decrite dans
[xkenzzo31/dofus-retro-deobfuscator](https://github.com/xkenzzo31/dofus-retro-deobfuscator) :

```
counter_str = format(counter, "05d")
hash        = SHA256(raw_packet + counter_str)
ct1         = AES-256-CBC(hash, key=hash_array[k1], iv=static_iv)
ct2         = AES-256-CBC(ct1,  key=hash_array[k2], iv=static_iv)
iv_rand     = os.urandom(16)
ct3         = AES-256-CBC(ct2,  key=wrap_key,      iv=iv_rand)
output      = raw_packet + \xf9 + b64(iv_rand) + b64(ct3)
```

Le code est deja la, teste (22 unit tests sur la forme et la
determinisme), **mais il a besoin des vraies cles**. Les cles
(9 cles AES-256 dans `hash_array`, 1-2 wrap keys, IV statique) ne sont
stockees nulle part dans le repo public : il faut les extraire **une
fois** d'un client Dofus Retro 1.48 en cours d'execution, puis les
ecrire dans `dofus_bot/data/shield_keys.json` (fichier gitignored).

#### Recette d'extraction (Chrome DevTools sur Electron)

1. **Fermer** Dofus Retro.exe s'il est lance.

2. Lancer Dofus en mode debug Node.js :
   ```
   "C:\Users\touki\Desktop\Client Hystoria V5\Dofus Retro.exe" --inspect-brk=0.0.0.0:9229
   ```
   L'executable va s'arreter avant de charger `main.jsc` et ecouter
   sur le port 9229.

3. Ouvrir Chrome/Edge, aller sur `chrome://inspect`. Cliquer
   "Configure..." et ajouter `localhost:9229` si ce n'est pas deja
   la. Attendre que le target "node" apparaisse sous "Remote Target"
   puis cliquer "inspect". DevTools s'ouvre, arrete sur le premier
   statement.

4. Dans l'onglet "Sources", chercher (Ctrl+P) le fichier qui contient
   `applyPacketToSendPostProcessing`. Meme si le nom de fonction est
   obfuscated, la chaine est presente dans les litteraux — Ctrl+Shift+F
   dans tous les fichiers marche bien. Poser un breakpoint sur la
   premiere ligne de la fonction.

5. Reprendre l'execution (F8). Le client continue de demarrer. Des que
   le premier paquet partant tombe dans le breakpoint, inspecter le
   panel "Scope" a droite :
   - "Local" : le `packet` recu
   - "Closure" : c'est la que vivent `hash_array`, `wrap_key`, et le
     `static_iv`. Survoler chaque entree pour voir son type. Les cles
     apparaissent comme `Uint8Array(32)` ou `CryptoJS.lib.WordArray`
     selon le build.

6. Exporter chaque cle en hex via la console DevTools :
   ```js
   // Si c'est un Uint8Array :
   Array.from(hash_array[0]).map(b => b.toString(16).padStart(2, '0')).join('')

   // Si c'est une CryptoJS WordArray :
   hash_array[0].toString(CryptoJS.enc.Hex)
   ```
   Collecter les 9 valeurs de `hash_array`, le `wrap_key`, et le
   `static_iv` (16 bytes = 32 hex chars).

7. Copier `dofus_bot/data/shield_keys.example.json` vers
   `dofus_bot/data/shield_keys.json` et remplacer les valeurs
   d'exemple par les vraies cles.

8. Valider le chargement :
   ```
   python -c "from dofus_bot.protocol.shield_signer import ShieldKeys; from pathlib import Path; ShieldKeys.from_json(Path('dofus_bot/data/shield_keys.json')); print('OK')"
   ```

Une fois les cles en place, la variable d'environnement
`DOFUS_SHIELD_KEYS=dofus_bot/data/shield_keys.json` dans `.env` suffit
pour activer le signer. Tant que cette variable n'est pas definie, la
proxy tourne en mode lecture seule et les injections du script Lua
sont logguees mais non envoyees.

#### Validation contre des vecteurs reels

Une fois les cles en main, on peut les valider contre les 639 paires
input/output capturees dans
[`data/security_api_calls.json`](https://github.com/xkenzzo31/dofus-retro-deobfuscator/blob/main/data/security_api_calls.json)
du repo xkenzzo31. Un script `tools/validate_shield_signer.py` sera
ajoute pour faire ce round-trip automatiquement.

### Hex dump de diagnostic

Si le mode `--dump` affiche des messages illisibles (ni texte clair, ni
shield clair), lance le proxy avec `--hex-dump` pour ecrire un dump
hexa des bytes bruts :

```
python -m dofus_bot --proxy --hex-dump logs/proxy_hex.log
```

Ca te donne la verite terrain : chaque chunk lu sur la socket est
ecrit tel quel, avant framing et stripping, pour pouvoir comparer avec
ce qu'attend le format documente.

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

  hook/
    __main__.py           # python -m dofus_bot.hook
    injector.py           # Frida attach + script loader
    redirect.js           # Frida JS : hook ws2_32!connect + rewrite sockaddr

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
