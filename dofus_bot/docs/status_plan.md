# Plan de statut : Bot Hystoria — où on en est, où on va, tests à faire

## Contexte

Deux demandes utilisateur cette session :

1. **"Tu as bien tout tout fouillé sur le forum ?"** → scrape exhaustif
   de Cadernis.fr pour ne rien louper. **FAIT** : 57 threads récupérés
   dans `/tmp/cadernis/threads/`, indexés dans
   `dofus_bot/docs/cadernis_index.md`, passages clés extraits dans 4
   docs de synthèse.
2. **"Refais moi un plan de où on en est et de où on va par rapport au
   projet initial, savoir si on est sur la bonne voie, savoir les
   tests à faire pour créer le bot automatisation."** → ce document.

Le projet initial visait un **bot socket Python asyncio** pour Dofus
1.29 Retro sur le serveur privé Hystoria V5, avec scripting Lua,
combats PvM et farm automatisé. Le scrape a **changé le tableau** :
on n'a plus le même degré de confiance sur l'architecture socket
pure, et on a découvert deux voies alternatives.

## Où on en est (par rapport au plan initial)

### Ce qui est FAIT

| Phase du plan initial             | Statut          | Fichiers livrés                                    |
| --------------------------------- | --------------- | -------------------------------------------------- |
| Phase 1 — Fondations réseau       | ✅ **Terminé**  | `network/connection.py`, `network/proxy.py`, `protocol/router.py`, `config.py`, `__main__.py` |
| Phase 2 — Authentification        | ⚠️ **Partiel**  | `protocol/crypto.py` (hash password), **mais** pas de handler auth complet. On a pivoté en mode MITM : on observe le vrai client qui fait l'auth à notre place. |
| Phase 3 — État du jeu & map       | ✅ **Terminé**  | `handlers/map_handler.py`, `handlers/stats_handler.py`, `game/state.py`, `game/map_data.py` |
| Phase 4 — Déplacement             | ✅ **Terminé**  | `game/pathfinding.py` (A* losange), `protocol/path.py` (encodage), `handlers/movement_handler.py`, `bot:move_to()` en Lua |
| Phase 5 — Combat                  | ✅ **Partiel**  | `handlers/combat_handler.py` (GJK/GTS/GTM/GTE/GE), `bot:cast()`, `bot:end_turn()`. Pas encore d'IA combat par défaut. |
| Phase 6 — Farming autonome        | ❌ **Pas fait** | — (dépend de l'IA combat + signatures validées)    |
| Phase 7 — Scripting Lua           | ✅ **Terminé**  | `scripting/engine.py`, `scripting/api.py`, `scripting/events.py`, `scripting/sandbox.py` + 5 scripts d'exemple, hot-reload OK |
| **Bonus** — Hook Frida            | ✅ **Terminé**  | `hook/` — redirige `ws2_32.dll!connect()` vers le proxy sans toucher au client Hystoria |
| **Bonus** — Strip signature Shield| ✅ **Terminé**  | `protocol/shield.py` + tests (côté LECTURE uniquement) |
| **Bonus** — Signer Shield         | ⚠️ **Squelette**| `protocol/shield_signer.py` + 22 tests unitaires — la chaîne AES est là **mais la longueur de ciphertext est fausse** (voir section suivante) |

### Nouveaux livrables de cette session (scrape Cadernis)

| Doc                                       | Contenu                                                     |
| ----------------------------------------- | ----------------------------------------------------------- |
| `dofus_bot/docs/auth_flow_1_29.md`        | Log wire verbatim de Caliphe (thread #1650), flow Zaap Thrift moderne (LuthTeur/Mirsa #3258), password hashing |
| `dofus_bot/docs/signing_strategies.md`    | Les 3 architectures (socket pur / MITM+oracle / clics UI), matrice de décision, recommandation |
| `dofus_bot/docs/movement_protocol.md`     | Grille losange, tables de voisinage odd/even, interdiction diagonales en combat, **timings GKK0** (anti-bot) |
| `dofus_bot/docs/cadernis_index.md`        | Index des 57 threads scrappés, catégorisés, résumés d'une ligne |
| `dofus_bot/docs/shield_research.md` (maj) | Correction 80→208 bytes, synthèse thread #2952, payload rtab, warning Brizze sur détection oracle RPC |

### Ce qu'on a APPRIS qui change le tableau

1. **La signature Shield fait 305 bytes, pas 133.** Notre
   `shield_signer.py` produit 80 bytes de ciphertext, mais la vraie
   signature fait **208 bytes** (Eleko thread #2952 + nos propres
   logs `+shield(304)` sur Hystoria). Le chain AES actuel est donc
   incomplet — soit il y a plus de rounds, soit on signe un blob
   plus long qui inclut un hash machine + des sentinelles
   (lagrangian #2952). **Sans les vraies clés ET un vecteur de test,
   on ne peut pas valider notre signer.**

2. **Le serveur privé Hystoria n'a probablement PAS d'équipe
   d'intégrité.** Les warnings "banni sur officiel" de Brizze / rtab
   viennent tous d'Ankama officiel. Sur Hystoria, **il est plausible
   que le serveur n'applique même pas la validation Shield**
   (LinningSilver #3092 + Duke Toland #3240 rapportent que les
   paquets non signés passent sur des serveurs privés).

3. **Le flow d'auth 1.29 complet est documenté.** Le log verbatim de
   Caliphe (thread #1650) donne toute la séquence
   `HC → Af → Ax → AX → AYK → HG → AT → ASK → GCK → GC1 → GDM`. On
   peut implémenter un handler d'auth sans devoir sniffer nous-mêmes.

4. **Une alternative sérieuse : le bot click (Nebular).** cremi532
   (#2990) a partagé un bot C# open source (Azzary/NebulaR-Bot) qui
   fonctionne sur Retro **sans aucun forge de paquet** : il clique
   dans la fenêtre du client via user32.dll. **Zero surface Shield.**
   C'est notre filet de sécurité si tout le reste échoue.

5. **Pathfinding piège silencieux.** Duke Toland (#3240) a perdu des
   semaines sur un bug "paquets ignorés" qui était en fait un
   mismatch entre son path client et le modèle de coût serveur. Le
   serveur ne répond rien, il faut juste matcher son calcul au byte
   près.

6. **GKK0 est un heartbeat anti-bot.** salesprendes (#2381) :
   envoyer GKK0 trop vite après un déplacement = flag anti-bot. Il
   faut respecter la durée de marche/course (tableau dans
   `movement_protocol.md`). Notre `movement_handler.py` le spamme
   pour l'instant — à corriger.

## Où on va — la décision clé

### La question qu'il faut trancher en premier

**Est-ce que le serveur Hystoria valide les signatures Shield, oui ou
non ?** Tant qu'on n'a pas la réponse, on ne peut pas choisir
l'architecture :

- **Si Hystoria S'EN FOUT de Shield** → on garde l'approche MITM
  actuelle, on branche `shield_signer.py` en mode "no-op" (retourne
  le paquet brut sans suffixe), et on finit les phases 5-6 en 2-3
  jours. C'est le scénario rose.
- **Si Hystoria VALIDE Shield** → on a deux options :
  1. Pivoter vers l'architecture B2 (client-as-oracle via le payload
     rtab de #2952) — 1 semaine de travail, risque bas sur serveur
     privé.
  2. Pivoter vers l'architecture C (Nebular-style clics UI) — on
     jette tout le code réseau et on repart sur user32/pyautogui.
     2 semaines, mais **zéro risque Shield**.

**Tout le plan de tests ci-dessous est conçu pour répondre à cette
question en premier, avant d'investir davantage.**

### Chemin recommandé

1. Commit + push tous les docs de recherche (ce qu'on fait maintenant).
2. **TEST #1** — détecter si Shield est enforced. Coût : 10 minutes
   de Lua via le proxy existant. Verdict binaire.
3. Selon le verdict :
   - **Shield off** → continuer les phases 5-6 (IA combat + farming)
   - **Shield on, léger** → extraire les clés via DevTools +
     implémenter le signer correct (208 bytes)
   - **Shield on, lourd** → pivot vers l'oracle rtab OU vers Nebular
4. Une fois la stratégie verrouillée, faire les TESTs #2 à #7 dans
   l'ordre.

## Plan de tests pour créer le bot d'automatisation

Ordonnés par **valeur informationnelle décroissante** : chaque test
débloque le suivant. Arrêter au premier test qui échoue et itérer sur
cette étape.

### TEST #1 — Hystoria enforce-t-il Shield ? (le test qui décide tout)

**Objectif** : savoir si on peut envoyer des paquets non signés au
serveur Hystoria et avoir une réponse.

**Pré-requis** : proxy MITM + hook Frida déjà lancés, client Hystoria
connecté à un perso en jeu, debout sur une map connue (pas en combat).

**Procédure** :

1. Lancer le proxy en mode injection :
   ```
   python -m dofus_bot --proxy --script examples/test_shield.lua
   ```
2. Créer le script `examples/test_shield.lua` qui fait **un seul
   truc** : envoyer un paquet brut non signé pour bouger d'une case :
   ```lua
   bot:on("character_ready", function()
     bot:wait(2)
     local target = bot.character.cell + 28  -- une case au sud
     bot:log("Test #1 : envoi GA0 brut non signé vers " .. target)
     bot:move_to(target)  -- passe par le pathfinder + GA0 brut
   end)
   ```
3. Observer dans les logs proxy :
   - **Verdict A (Shield OFF)** : le perso se déplace visuellement
     dans le client, le serveur broadcaste un `GA0` écho au client,
     et on voit `[S>>C] GA0;1;<charid>;<path>`. ✅ Hystoria ne
     valide pas Shield.
   - **Verdict B (Shield ON, silent drop)** : aucun mouvement, le
     serveur ne répond rien sur ce charid. Le client ne voit jamais
     l'écho. **Lancer aussitôt TEST #1b.**
   - **Verdict C (Shield ON, ban instant)** : le serveur envoie un
     `AD<code>` kick ou un `mI1\ue004...Triche`. ❌ Shield dur.

**TEST #1b — discrimination ambiguë** : si verdict B, remplacer
`bot:move_to(target)` par `bot:send("GA0;1;" .. bot.character.id ..
";" .. encode_cell(target))` avec `encode_cell` emprunté à
`protocol/path.py`. Même résultat = confirmation Shield ON. Si le
mouvement marche sur cet appel-là mais pas l'autre, c'est un bug côté
pathfinder (cf. Duke Toland #3240), pas Shield.

**Durée** : 10 minutes de setup + 1 minute de test.

### TEST #2 — Validation du flow d'auth 1.29 en mode sniffer

**Objectif** : confirmer qu'Hystoria parle bien le flow Caliphe
(thread #1650) et pas un protocole custom.

**Procédure** :

1. Lancer le proxy avec `--dump logs/auth_flow.log`
2. Se déconnecter du client, se reconnecter.
3. Grep dans `auth_flow.log` les préfixes `HC`, `Ax`, `AYK`, `AT`,
   `HG`, `ASK`, `GDM`. On doit voir **exactement** la séquence de
   `auth_flow_1_29.md` §1.
4. Si un préfixe manque ou est dans un autre ordre, noter la
   divergence. Si le flow matche, on sait qu'on pourrait (en théorie)
   faire un client pur-socket sans passer par le MITM.

**Durée** : 5 minutes.

### TEST #3 — Déplacement injecté hors combat (1ʳᵉ action écrite)

**Objectif** : vérifier que `bot:move_to(cell)` déclenche un vrai
mouvement visible dans le client et synchronisé sur le serveur.

**Pré-requis** : TEST #1 avec Verdict A **ou** keys Shield extraites +
signer corrigé **ou** oracle rtab branché.

**Procédure** :

1. Bot en mode proxy + script `examples/explore.lua` (déjà existant).
2. Vérifier dans le client Hystoria que le perso fait le tour de la
   map courante en rectangle.
3. Vérifier qu'après chaque mouvement le serveur renvoie bien le `GA0`
   écho avec le même path encodé.
4. Bug à surveiller : si le serveur ignore silencieusement, c'est
   probablement le pathfinder qui produit un chemin que le serveur
   juge invalide (diagonale interdite, cellule bloquée, PM
   insuffisants). Dans ce cas → TEST #3b.

**TEST #3b** : réduire le path à **une seule case adjacente**. Si ça
marche, le bug est dans la génération du chemin multi-cell, pas dans
le wire format.

**Succès** : le perso fait 5 mouvements consécutifs sur la map sans
intervention.

**Durée** : 30 minutes si succès, potentiellement 1 journée si
debugging de path.

### TEST #4 — Validation pathfinder A* contre un capture réel

**Objectif** : s'assurer que notre A* produit le même chemin que le
vrai client Dofus pour une paire (start, end) donnée.

**Procédure** :

1. Depuis le client réel, clic-droit sur une cellule distante. Dans
   les logs du proxy `--dump` on voit le `GA0` sortant du client avec
   le path encodé.
2. Décoder ce path avec `protocol.path.decode_path()`.
3. Appeler `pathfinding.astar(start_cell, end_cell)` avec les mêmes
   paramètres et comparer les cellules case par case.
4. Si différence : c'est probablement un problème d'heuristique
   (Manhattan vs Chebyshev) ou d'ordre de neighbors. Loguer la
   divergence et corriger `pathfinding.py`.

**Durée** : 1 heure.

### TEST #5 — Cast de sort en combat

**Objectif** : lancer un combat, attendre notre tour, cast un sort,
finir le tour.

**Pré-requis** : TESTS #1-4 OK.

**Procédure** :

1. Monter `examples/test_cast.lua` :
   ```lua
   bot:on("turn_start", function(data)
     if not bot.fight.my_turn then return end
     local e = bot:closest_enemy()
     if e then bot:cast(161, e.cell) end
     bot:wait(0.5)
     bot:end_turn()
   end)
   ```
2. Engager manuellement un monstre faible dans le client.
3. Vérifier : au tour du bot, on envoie `GA300;161;<cell>` suivi de
   `GA903`. Le sort anime bien dans le client. Le monstre prend des
   dégâts visibles dans les logs `GJK`.
4. Bug typique : l'ID `161` (Flèche Magique) n'est pas forcément le
   bon pour la classe jouée. Adapter selon le perso.

**Durée** : 30 minutes.

### TEST #6 — Farm autonome sur une route de 3 maps

**Objectif** : boucle de farm complète sans intervention.

**Pré-requis** : TESTS #1-5 OK + au moins une IA combat minimale
(Python par défaut OU script Lua).

**Procédure** :

1. Créer `data/routes/test_bouftous.yaml` avec 3 map IDs adjacentes
   (Astrub, bouftous faibles).
2. Lancer `python -m dofus_bot --proxy --script examples/farm_route.lua`
3. Laisser tourner 15 minutes. Vérifier :
   - Au moins 3 combats complétés.
   - XP gagnée visible dans `ASK` ou logs.
   - Pas de déconnexion.
   - Pas de warning anti-bot dans le canal "Information".
4. Logger chaque combat dans `logs/farm_test.log` avec timestamp +
   durée + résultat.

**Durée** : 30 minutes de setup + 15 minutes de run.

### TEST #7 — Hot-reload Lua pendant un combat

**Objectif** : valider le workflow de développement : itérer sur un
script Lua sans recharger le bot.

**Procédure** :

1. Bot en cours de farm (TEST #6).
2. Éditer `farm_route.lua` → changer la route.
3. Vérifier que le bot adopte la nouvelle route à la **prochaine** fin
   de combat, sans redémarrage.

**Durée** : 10 minutes.

## Critères de décision "bot prêt pour production personnelle"

On considère le bot comme **utilisable** quand :

- [ ] TESTS #1 à #6 passent au vert
- [ ] 1 heure de farm continu sans crash ni ban
- [ ] Le script utilisateur peut être modifié à chaud sans couper
      la session
- [ ] Les logs tracent clairement chaque action importante
      (connexion, combat, déplacement, erreur)
- [ ] Un README Windows clair permet à l'utilisateur de tout relancer
      après un reboot

## Fichiers critiques à toucher ensuite (selon verdict TEST #1)

**Si Shield OFF** :
- `dofus_bot/__main__.py` — brancher un mode `--shield-noop` qui
  bypasse le signer et envoie les paquets bruts
- `dofus_bot/strategy/combat_ai.py` — **à créer**, IA par défaut
  simple (closest enemy + spell rotation)
- `dofus_bot/strategy/farming.py` — **à créer**, boucle farm
- `dofus_bot/handlers/movement_handler.py` — corriger le timing GKK0
  (aujourd'hui spammé immédiatement)

**Si Shield ON (signer)** :
- `dofus_bot/protocol/shield_signer.py` — étendre la chaîne AES pour
  produire 208 bytes de ciphertext
- `tools/validate_shield_signer.py` — **à créer**, compare vecteurs
  réels capturés vs sortie du signer
- `dofus_bot/data/shield_keys.json` — **à créer**, keys extraites
  via DevTools + `--inspect-brk`

**Si Shield ON (oracle rtab)** :
- `dofus_bot/protocol/shield_oracle.py` — **à créer**, client TCP RPC
  vers `127.0.0.1:31339`
- `dofus_bot/hook/shield_oracle.js` — **à créer**, payload
  `@electron/remote` à injecter dans la DevTools console du client
- Adapter `proxy.py` pour router les injections via l'oracle

## Références — tous les docs sur lesquels ce plan s'appuie

- `dofus_bot/docs/shield_research.md`
- `dofus_bot/docs/signing_strategies.md`
- `dofus_bot/docs/auth_flow_1_29.md`
- `dofus_bot/docs/movement_protocol.md`
- `dofus_bot/docs/cadernis_index.md`

