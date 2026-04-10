# Auth flow — Dofus Retro 1.29 (text protocol)

Single source of truth for the wire auth handshake we need to either
**observe** (MITM mode) or **drive** (pure-socket mode) against a 1.29
server. This is the classic text protocol used by every 1.29 emulator
(Shivas, Emudofus, Ankama's own Retro backend), including private
servers like **Hystoria V5**.

This doc does **not** cover the Shield wrapper (see
`shield_research.md`) nor the modern Zaap/HAAPI front-door used by
official 1.48 clients (see `signing_strategies.md` §2).

---

## 1. Canonical wire log (Dofus 1.29 raw)

Captured by **Caliphe** in Cadernis thread **#1650** (*MITM 1.29
déplacements*) against a 1.29 private server. This is the cleanest
verbatim log we have — keep this as the reference when writing parsers
or unit tests for `handlers/auth_handler.py`.

```
[Server(AUTH)] ===> HC<32-char-key>
[Client]       ===> 1.29.1
[Client]       ===> <login>\n#<hashed_password>
[Client]       ===> Af
[Server(AUTH)] ===> Af1|0|1|0|-1
[Server(AUTH)] ===> AdPseudo
[Server(AUTH)] ===> Ac0
[Server(AUTH)] ===> AH <servers list>
[Server(AUTH)] ===> AlK0
[Server(AUTH)] ===> AQ
[Client]       ===> Ax
[Server(AUTH)] ===> Ax <servers list>
[Client]       ===> AX<serverid>
[Server(AUTH)] ===> AYK<host>:<port>;<ticket>

---- TCP reconnect to game server ----

[Server(GAME)] ===> HG
[Client]       ===> AT<ticket>
[Server(GAME)] ===> ATK0
[Client]       ===> Ak0
[Client]       ===> AV
[Client]       ===> Agfr
[Client]       ===> Ai<token>
[Client]       ===> AL
[Client]       ===> Af
[Server(GAME)] ===> ALK|...|<charid>;<name>;<level>;...
[Client]       ===> AS<charid>
[Server(GAME)] ===> ASK|<charid>|<name>|...
[Client]       ===> GCK|1|
[Server(GAME)] ===> GC1 (game start)
[Server(GAME)] ===> GDM<compressed_map>
[Server(GAME)] ===> GM|...actors list...
```

## 2. Packet-by-packet semantics

| Prefix  | Direction  | Meaning                                                       |
| ------- | ---------- | ------------------------------------------------------------- |
| `HC`    | S → C      | Hello Connect. 32-char random key, seeds the password hash.   |
| version | C → S      | Plain `1.29.1` string (or whatever the emulator accepts).     |
| `#<hp>` | C → S      | Login + `\n` + `#` + hashed password (see `crypto.py`).       |
| `Af`    | C → S      | "Ask free" — queue status request.                            |
| `Af1\|…`| S → C      | Queue response (position\|server\|pref\|weight\|total).       |
| `Ad`    | S → C      | Account pseudonym display name.                               |
| `Ac`    | S → C      | Community flag.                                               |
| `AH`    | S → C      | Hosts / server list summary.                                  |
| `AlK`   | S → C      | Account level / kickout status.                               |
| `AQ`    | S → C      | Account question marker (end of account dump).                |
| `Ax`    | C → S      | Ask servers — client requests the full server list.           |
| `Ax`    | S → C      | Server list reply.                                            |
| `AX`    | C → S      | Select server (`AX<serverID>`).                               |
| `AYK`   | S → C      | Yield ticket — `AYK<host>:<port>;<ticket>`. See §3.           |
| `HG`    | S → C      | Hello Game — greets the reconnected socket.                   |
| `AT`    | C → S      | Auth Ticket — `AT<ticket>` as received from AYK.              |
| `ATK`   | S → C      | Ticket OK.                                                    |
| `Ak`    | C → S      | Account keys request.                                         |
| `AV`    | C → S      | Account version.                                              |
| `Ag`    | C → S      | Account language (`Agfr`, `Agen`…).                           |
| `Ai`    | C → S      | Account id token.                                             |
| `AL`    | C → S      | Account characters list request.                              |
| `ALK`   | S → C      | Character list reply (pipe-separated tuples).                 |
| `AS`    | C → S      | Account select character (`AS<charid>`).                      |
| `ASK`   | S → C      | Character selected OK (full stats).                           |
| `GCK`   | C → S      | Game Context "K" — entering play mode (`GCK\|1\|`).          |
| `GC1`   | S → C      | Game Context 1 — in-game acknowledged.                        |
| `GDM`   | S → C      | Game Data Map (compressed 1.29 .dlm format).                  |
| `GM`    | S → C      | Game Map actors list.                                         |

## 3. `AYK` handoff — critical detail

The `AYK` packet is the **only** link between the auth socket and the
game socket. Layout:

```
AYK<game_host>:<game_port>;<short_ticket>\x00
```

Example from Caliphe's log (private server):

```
AYK10.0.0.5:5555;abc123xyz
```

Steps the client MUST perform:

1. Parse `host`, `port`, `ticket` from the payload.
2. **Close** the auth socket.
3. **Open** a fresh TCP socket to `host:port`.
4. Wait for the server-side `HG` greeting.
5. Send `AT<ticket>\x00`.
6. Expect `ATK0` (ticket accepted). Anything else = auth failure.

If step 2 is skipped (keeping the auth socket open) some emulators
don't care, but Ankama's real 1.29 backend used to drop the game
socket with `ATF` (ticket failure). We mirror the canonical flow.

## 4. Modern Dofus Retro 1.48 differences (Hystoria V5 client)

The Hystoria V5 launcher ships the **official 1.48 Electron client**.
That client does **not** talk the raw flow above. It goes through a
Zaap/Thrift front-door before hitting the text protocol:

```
Electron launcher (main.jsc Shield)
    |
    v   Thrift RPC on localhost:26116 (Zaap bridge)
    |
    v
dofusretro-co-production.ankama-games.com:443
    | send "#Z\n<uuid>\x00"
    | recv "AYK<game_host>:<port>;<short_ticket>\x00"
    v
Game server (Boune, Eratz, Henual, …)
    | send "AT<short_ticket>\x00"
    v   (same text protocol as §1 from here on)
```

This is documented in Cadernis thread **#3258** (*Dofus Retro 1.47.22
ticket AT*) by **LuthTeur** + **Mirsa**. Key quotes:

> **Mirsa, thread #3258 msg 11**:
> "En gros il faut que tu envoies `#Z\n<uuid>` au serveur de connexion
> (port 443). Il te répond avec un `AYK<host>:<port>;<ticket>`. Après
> tu ouvres une nouvelle socket sur le game server et tu envoies
> `AT<ticket>`."

> **LuthTeur, thread #3258 msg 3** (on the 3 bugs that cost them 2
> weeks):
> 1. `WSASend()` is hooked by Shield — must use `send()` directly on
>    the raw socket FD.
> 2. The `ù` (`\xf9`) byte wraps the Shield signature. Not a framing
>    delimiter — part of the signed payload envelope.
> 3. `GA001` (walk commit) **requires the actor ID**, not just the
>    character ID. This is a 1.48-era addition.

### Two consequences for Hystoria

1. **The Hystoria server is a private server**. We do not know yet
   whether its front-door is the classic 1.29 `HC + Af + Ax + AX + AYK`
   flow (§1) or the modern `#Z` Thrift handoff (§4). **Test #1 in
   `status_plan.md` resolves this.**
2. **The Hystoria client is the official 1.48 Electron**. When we MITM
   it on `162.19.127.155:5555` (the IP extracted by `netstat` during a
   real connection), the client has already done its local Shield
   handshake and is about to send whatever the Hystoria server expects.
   So the **server side** of the test determines the protocol, not the
   client side.

## 5. Password hashing (`protocol/crypto.py`)

The Dofus 1.29 password hash is:

```
HASH_CHARS = "-_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

def hash_password(password: str, hc_key: str) -> str:
    # Returns "#1" + base64-ish encoding of password XOR hc_key
    # where hc_key is the 32-char key received in HC.
```

Reference implementations:

- **kralamoure/retroproto** (Go) — canonical `EncryptPassword`.
- **Arakne** (Java) — `fr.arakne.utils.encoding.Password`.
- **xfux/xfus** repos on GitHub — various JS ports.

Two things we've seen break this:

1. **Account name case**: some servers downcase the login before
   hashing, others don't. Hystoria status: **unknown** — to test.
2. **HC key length**: Caliphe's capture shows 32 chars. Some older
   1.29 builds used 4 chars. If the hash fails, check the length first.

## 6. References

- **Thread #1650** — Caliphe — MITM 1.29 déplacements (wire log)
- **Thread #1633** — Connexion serveur de jeu (old-school AYK flow)
- **Thread #2476** — Analyse paquets TCP Dofus Retro
- **Thread #3039** — Akihiko Hikage — Création bot MITM Dofus Retro
  (Python HAAPI bypass, Zaap keydata decryption)
- **Thread #3258** — LuthTeur + Mirsa — Dofus Retro 1.47.22 ticket AT
- **Thread #3121** — Connexion Dofus Retro via Thrift (deep dive on
  the Zaap Thrift bridge)
- **Thread #381**  — Connexion (old thread, confirms 32-char HC key)
- **kralamoure/retroproto** — `proto/auth/` package
- **Emudofus/Shivas** — `login/src/main/java/org/shivas/login/` (server side)
