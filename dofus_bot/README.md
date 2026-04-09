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
- [ ] API Lua (`bot.character.hp`, `bot:cast(...)`, `bot:on("turn_start", ...)`)
- [ ] Moteur de rotation de sorts declaratif (turns[1] = {...}, turns[2] = {...})
- [ ] Recherche/engagement automatique des monstres sur la map
- [ ] Auto-heal post-combat
- [ ] Recharge des scripts a chaud

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

Ce n'est pas un bug : on en est a l'etape "observation". Le bot ne
**fait rien** pour l'instant, il se contente de logger. Les scripts
qui injectent des actions arrivent dans la prochaine iteration.

## Ce que tes scripts Lua vont pouvoir faire (bientot)

```lua
-- data/scripts/examples/farm_cra.lua
return {
  turns = {
    [1] = {
      { spell = "fleche_magique", target = "closest" },
      { spell = "fleche_magique", target = "closest" },
      { action = "move_melee",    target = "closest" },
    },
    [2] = {
      { spell = "pression",       target = "weakest" },
      { spell = "fleche_magique", target = "closest" },
    },
  },

  after_fight = function(bot)
    if bot.character.hp < bot.character.max_hp * 0.7 then
      bot:use_item("pain_complet")
      bot:wait(3)
    end
  end,

  farming = {
    maps = { 7411, 7412, 7413, 7668 },
    target = "bouftou",
  },
}
```

Rotation de sorts par tour, action apres combat, route de maps : tout
sera declaratif et facile a modifier sans toucher au code Python.

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
    map_handler.py        # GDM, GM -> GameState.current_map_id, actors
    combat_handler.py     # GJK/GTS/GTM/GTE/GE -> GameState.fight_*

  game/
    state.py              # GameState partage (Character, Actor, FightEntity)

  scripting/              # (vide pour l'instant - prochaine iteration)

  data/
    scripts/
      examples/           # Scripts d'exemple (a venir)
      my_scripts/         # Tes propres scripts (gitignored)
```
