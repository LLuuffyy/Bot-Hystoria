# Cadernis.fr — Indexed thread catalog

Every Cadernis thread we've scraped, one-line summary, and which doc
it feeds. Use this as the **entry point** when you need to look up a
specific topic — grep for a keyword, find the thread ID, open
`/tmp/cadernis/threads/<slug>.<id>.html` (or re-fetch from
`https://cadernis.fr/index.php?threads/<slug>.<id>/` with the
session cookies in `/tmp/cadernis/jar.txt`).

Scraped with authenticated session, 2026-04-10, account
`toukiki83@gmail.com`. Total threads in the scrape: 57 (from the
list of 176 candidate threads in
`/tmp/cadernis/all_thread_urls.txt`).

Legend:

- 🟢 Directly actionable — we implemented something from it
- 🟡 Reference — good context, not directly used yet
- 🔵 Dead-end / outdated — scraped for completeness

---

## Shield / anti-cheat / packet signing

| # | ID    | Thread title                                                        | Contribution                                                                  |
| - | ----- | ------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| 🟢 | 2952 | Nouvelle signature `ù` dans les packets envoyes                    | **Eleko**: sig = 16 + 208 bytes. **rtab**: `@electron/remote` RPC payload. **Brizze**: flagged 2-3 months. **Killersarea**: "ne tente pas de reverse le jsc". **lagrangian**: "plusieurs clés, flags, ivs..." |
| 🟢 | 3262 | Déobfuscation client Dofus Retro 1.48 — Reverse engineering Shield V8 | xkenzzo31's decompiler repo (84% of 8611 functions). 4-step AES chain. `applyPacketToSendPostProcessing`. |
| 🟢 | 3092 | Détection hook packets non chiffrés                                | **LinningSilver**: server accepts unsigned packets instantly but flags for human review. |
| 🟢 | 3240 | MITM Dofus Retro packets send ignorés par le serveur               | **Duke Toland**: unsigned packets accepted on private server, but hit pathfinding/char ID mismatch. |
| 🟡 | 2891 | Cloudflare error code 1020                                         | HAAPI / Cloudflare bot detection on the launcher side.                       |
| 🟡 | 2942 | Reverse engineering et législations                                | Legal discussion — confirms private-server bot dev is a gray zone only.     |
| 🟡 | 1871 | Authentification et chiffrement                                    | Historical RSA handshake on 1.48 beta (not used in production).              |
| 🟡 | 2449 | AuthentificationFrame — calcul credentials                         | 1.48 Flash credentials calculation.                                          |

## Auth flow / handshake

| # | ID    | Thread title                                                     | Contribution                                                           |
| - | ----- | ---------------------------------------------------------------- | ---------------------------------------------------------------------- |
| 🟢 | 1650 | MITM 1.29 déplacements                                           | **Caliphe**: complete verbatim wire auth log HC→AYK→AT→ASK→GDM. This is the Rosetta stone for `auth_flow_1_29.md`. |
| 🟢 | 3258 | Dofus Retro 1.47.22 ticket AT                                    | **LuthTeur + Mirsa**: modern Zaap Thrift `#Z\n<uuid>` handoff. LuthTeur's 3 bugs (WSASend, `ù` wrap, GA001 actor ID). |
| 🟢 | 3039 | Création de mon bot MITM Dofus Retro                             | **Akihiko Hikage**: Python HAAPI bypass journey. **Killersarea**: Zaap bridge port 26117, `keydata` file at `%APPDATA%\zaap\keydata`. **Suftouil**: decryption code AES-128-CBC + MD5. |
| 🟢 | 1633 | Connexion serveur de jeu                                         | Old-school AYK handoff + packet 42 trigger on legacy 1.29 emulators.  |
| 🟢 | 381  | Connexion                                                        | Confirms the 32-char HC key length on classic 1.29.                  |
| 🟡 | 3121 | Connexion à Dofus Retro en utilisant Thrift                      | Deep dive on Zaap Thrift bridge.                                      |
| 🟡 | 2869 | IdentificationFailed — wrong credential                          | Credentials debugging, confirms login downcasing on some servers.    |
| 🟡 | 2841 | Problème avec le HelloConnectMessage                             | 1.48 HelloConnectMessage (not relevant to 1.29).                     |
| 🟡 | 402  | Problème IdentificationMessage                                   | Historical 2.x auth issue.                                           |
| 🟡 | 1196 | Quelques problèmes avec IdentificationMessage id 4               | Historical 2.x auth issue.                                           |
| 🟡 | 1199 | Public key et message d'authentification                        | 2.x RSA.                                                              |
| 🟡 | 1347 | Encore et toujours ce RSA                                        | 2.x RSA.                                                              |
| 🟡 | 298  | Tutoriel mise à jour du cryptage du mot de passe en RSA          | Pre-1.29 password encryption tutorial (mostly obsolete).             |
| 🟡 | 524  | 2-5-5 password encryption                                        | Pre-1.29 password encryption historical.                             |

## Movement / pathfinding / map data

| # | ID    | Thread title                                               | Contribution                                                           |
| - | ----- | ---------------------------------------------------------- | ---------------------------------------------------------------------- |
| 🟢 | 2381 | Tutoriel déplacements Dofus 1.29                          | **habbablekebab128**: odd/even neighbor tables. **salesprendes**: `GKK0` timing warning. |
| 🟢 | 2230 | Compréhension du temps pathfinding 1.29.1                 | Per-cell walk/run durations table (0.3 / 0.2 / 0.75 / 0.5 sec).      |
| 🟢 | 1976 | Les déplacements en combat                                 | **zahid98**: diagonals forbidden in combat.                           |
| 🟢 | 2239 | Dofus 1.29 taille des cells                                | Cell ↔ (i,j) conversion math.                                         |
| 🟢 | 2197 | Taille des cellules d'une map                              | Confirms 560 cell count on Amakna maps.                               |
| 🟡 | 3265 | Grille map bot Dofus serveur privé                         | Private-server variant of the grid layout.                            |
| 🟡 | 3260 | Détection position de la map actuelle                      | Reading current map ID from the GDM packet.                           |
| 🟡 | 3051 | Cellules disponibles dans une map                          | Walkability extraction from GDM.                                      |
| 🟡 | 3066 | Changer de map Dofus MITM                                  | Map transition packet sequence.                                       |
| 🟡 | 2931 | Analyse de map avec l'image                                | Visual extraction from rendered tiles.                                |
| 🟡 | 1903 | Compréhension cryptage map 1.29                            | DLM compressed map format.                                            |
| 🟡 | 2225 | Décryptage des maps 1.29                                   | DLM decompressor reference.                                           |
| 🟡 | 2095 | D2.0 distinguer les cellues d'un escalier et autopather    | Stairs detection for 2.x (not 1.29).                                  |
| 🟡 | 2842 | Worldgraph projet de pathfinding                           | Multi-map WorldGraph reference.                                       |

## Combat / spells

| # | ID    | Thread title                                               | Contribution                                                    |
| - | ----- | ---------------------------------------------------------- | --------------------------------------------------------------- |
| 🟢 | 1774 | Dofus bot 1.29 2 sorts                                     | **BlueDream**: `GA300<spell>;<cell>` + `GKK0` spell cast loop. |
| 🟢 | 2519 | Gestion des combats                                        | GJK/GTS/GTR/GTM/GTE/GE combat cycle breakdown.                 |
| 🟡 | 3259 | Bot combat farm XP — détecter un monstre sur Dofus         | Monster detection via GM packet entity flags.                  |
| 🟡 | 2608 | Demande d'aide pour interprétation élémentaire de paquet   | GA action subfield semantics.                                  |
| 🟡 | 2392 | Problème paquet GA envoie de sort                          | Spell cast edge cases.                                         |
| 🟡 | 2826 | Détection archi monstre                                    | Monster group detection.                                       |
| 🟡 | 2617 | Pixelbot combat displacement spells attack summon          | Pixelbot combat implementation reference.                      |

## Bot implementations (ready to steal from)

| # | ID    | Thread title                                               | Contribution                                                   |
| - | ----- | ---------------------------------------------------------- | -------------------------------------------------------------- |
| 🟢 | 2990 | NebulaR Bot Dofus Retro                                    | **cremi532**: full C# bot source with Lua scripting, user32.dll clicks. https://github.com/Azzary/NebulaR-Bot |
| 🟢 | 3223 | Bon voici le code source entier de Snowbot                 | Full snowbot source share (Dofus Retro UI-automation bot).    |
| 🟡 | 3175 | Release Dofus 3 bot MVP — connexion socket + OAuth         | Modern Dofus 3 bot MVP source (different game).               |
| 🟡 | 2174 | CookieTouch — bot Dofus Touch                              | Dofus Touch reference (different protocol).                   |
| 🟡 | 2308 | Difys Headless — Dofus Touch botting client                | Dofus Touch reference.                                         |
| 🟡 | 2668 | Mirage — un nouveau client pour Dofus Touch                | Dofus Touch reference.                                         |
| 🟡 | 2565 | Mirage — le nouveau client Dofus Touch                     | Dofus Touch reference.                                         |
| 🟡 | 2103 | Alpha Bot — bot Dofus 2.00                                 | Historical 2.x bot.                                            |
| 🟡 | 2642 | Dofus Retro Supertools — outil multicompte                 | Multiclient coordination reference.                            |

## MITM / proxy / hooking

| # | ID    | Thread title                                                | Contribution                                                  |
| - | ----- | ----------------------------------------------------------- | ------------------------------------------------------------- |
| 🟢 | 3124 | Création MITM — rediriger la connexion (hook)              | **NoKi-senpai**: failed hooks at `connect`/`WSAConnect`/`ConnectEx`. **lagrangian**: Chromium CEF child process spawn, Frida, CREATE_SUSPENDED, app proxy > WinDivert, Zaap env vars. |
| 🟢 | 2988 | Comment créer un bot MITM pour de bon                       | MITM architecture discussion.                                 |
| 🟡 | 2480 | MITM sur Dofus Retro                                        | Early MITM attempts.                                          |
| 🟡 | 2958 | MITM bot Dofus Retro                                        | MITM proxy discussions.                                       |
| 🟡 | 3060 | MITM Dofus Retro — besoin d'un dernier coup de pouce        | MITM debug.                                                   |
| 🟡 | 2722 | MITM d-fus                                                  | MITM on classic server.                                       |
| 🟡 | 2587 | macOS Python MITM Dofus Retro                               | macOS-specific proxy setup.                                   |
| 🟡 | 2513 | Connection MITM                                             | MITM setup questions.                                         |
| 🟡 | 3105 | Bot MITM automatisation lancement Retro                     | Bot launcher automation.                                       |
| 🟡 | 2589 | Rediriger la connexion sur Dofus Touch                      | Dofus Touch reference.                                         |

## Frida / DLL injection / process manipulation

| # | ID    | Thread title                                                        | Contribution                                    |
| - | ----- | ------------------------------------------------------------------- | ----------------------------------------------- |
| 🟢 | 3122 | Détection des clics synthétiques et discussions générales bots 3.0 | **anon + kerop**: SendInput not flagged on Retro. |
| 🟢 | 3136 | Simulation de clics via injection DLL détectable sur Dofus Retro   | DLL injection click discussion.                  |
| 🟡 | 3133 | Problème injection Dofus Retro DLL                                 | DLL injection troubleshooting.                   |
| 🟡 | 3143 | Blocage des clics sur Dofus Retro                                  | Click blocking discussion.                       |
| 🟡 | 3132 | Décompilation client Dofus Retro — problème déobfuscation          | Client decompilation discussion.                 |
| 🟡 | 3029 | Lire SWF Dofus Retro (résolu)                                      | SWF extraction from the 1.48 client.             |
| 🟡 | 929  | Tuto pimpmyfux                                                      | Historical Flash client patcher tutorial.        |
| 🟡 | 3017 | Ban des machines virtuelles                                         | VM detection by Shield.                          |
| 🟡 | 2626 | Ban using device ID                                                 | Device fingerprinting.                           |

## Data sniffing / protocol analysis

| # | ID    | Thread title                                                  | Contribution                                             |
| - | ----- | ------------------------------------------------------------- | -------------------------------------------------------- |
| 🟢 | 491  | Tuto bot socket — les fondamentaux                            | Foundation tutorial, 1.29 packet basics.                 |
| 🟡 | 2866 | Retro — analyser paquets facilement                           | Packet analysis workflow.                                |
| 🟡 | 3130 | Débutant cherche aide pas à pas pour projet Dofus Retro data sniffer | Data sniffing walkthrough.                      |
| 🟡 | 3071 | Python sniffer help — impossible de décoder certains packets  | Python sniffer debugging.                                |
| 🟡 | 2861 | Retro — demande information MITM                              | MITM info request.                                       |
| 🟡 | 2424 | Journal de bord — analyser ses premiers paquets               | Protocol analysis journal.                                |
| 🟡 | 3084 | Extraction adresse IP bot Dofus Retro                         | How to find the real game server IP (netstat workflow). |
| 🟡 | 3067 | ID serveur privé Retro                                        | Server ID in the AYK packet.                             |
| 🟡 | 3016 | Bot Dofus Retro serveur privé                                 | Private server bot discussion.                           |
| 🟡 | 2730 | Wireshark dissector                                           | Wireshark dissector plugin.                              |

## Non-applicable (wrong game / wrong era)

- **#2937** — Dofus Retro héros (feature discussion, no protocol info)
- **#3061** — DofusInvoker.swf Node.js (Flash client extraction)
- **#3087** — DivaSniffer outil de sniff Dofus Unity
- **#3074** — Dofus Unity — petite histoire d'un robot
- **#3081** — Création de bot réseau Dofus 2 Unity ou Touch
- **#3082** — Dofus Unity — comment récupérer les protos
- **#2991** — Dofux Unitx — Dofus open source
- **#1943** — Émulateur Dofus 2.4x C++
- **#1881** — Noxus Node.js émulateur 2.39
- **#2361** — Elk émulateur Dofus Touch
- All other 2.x/Unity/Touch threads

## Session cookies

Valid session at `/tmp/cadernis/jar.txt` (xf_user token, expires
2027-04-07). Account `toukiki83@gmail.com`. Re-fetching a thread:

```bash
curl -sL 'https://cadernis.fr/index.php?threads/<slug>.<id>/' \
  -b /tmp/cadernis/jar.txt \
  -c /tmp/cadernis/jar.txt \
  -H 'User-Agent: Mozilla/5.0 ...' \
  > /tmp/cadernis/threads/<slug>.<id>.html
```

Multi-page threads: add `page-N` (e.g.
`threads/retro-nouvelle-signature-xc3-xb9-dans-les-packets-envoyes.2952/page-2`).
