# dofus_bot

Socket bot for the Dofus 1.29 Retro private server Hystoria.

Lives alongside the Playwright-based voting bot at the repo root but is
completely independent. Connects directly to the game server over TCP,
emulates the 1.29 protocol and automates combat, movement and farming.

**For personal use on the user's own private server only.**

## Status

Foundation only. Current build contains:

- [x] Async TCP connection with null-byte framing (`network/connection.py`)
- [x] Prefix-based message router (`protocol/router.py`)
- [x] Password hashing (canonical MD5+XOR and plain-XOR fallback)
- [x] Auth handler skeleton (HC -> credentials -> server select -> ticket)
- [x] `--sniff` mode for protocol discovery
- [x] `--login` mode to validate the auth flow end-to-end
- [ ] Game-server connection and character selection
- [ ] Map / actors / movement
- [ ] Combat
- [ ] Farming brain
- [ ] Lua scripting engine

## Setup

```bash
pip install -r ../requirements.txt
cp ../.env.example ../.env   # fill in DOFUS_* vars
```

Required env vars:

```
DOFUS_USERNAME=moncompte
DOFUS_PASSWORD=monmdp
DOFUS_CHARACTER=MonPerso
DOFUS_AUTH_HOST=play-hystoria.net
DOFUS_AUTH_PORT=443
DOFUS_SERVER_ID=0
```

## Usage

**Protocol discovery (safe first run, sends nothing):**

```bash
python -m dofus_bot --sniff
```

Connect to the auth server and log every message received. Use the
output to verify the port is correct and to observe the exact
`HC<key>` greeting before attempting a login.

**Authentication flow:**

```bash
python -m dofus_bot --login
```

Runs the full login sequence up to the game-server ticket and then
stops. Success looks like:

```
Authenticated successfully. Game server: 1.2.3.4:5555 (ticket=...)
```

If the auth step fails, re-run `--sniff`, observe what the server sends
back, and adjust `AuthHandler._send_credentials` or
`hash_password(..., mode=...)` accordingly.

## Next steps

1. Validate `--sniff` on the real Hystoria auth server (confirm port,
   capture the exact HC message, check encoding).
2. Validate `--login` and tune the credential format / crypto mode if
   the server rejects the default.
3. Implement the game-server connection (character select, enter world).
4. Map + movement (Phases 3-4 of the plan).
5. Combat (Phase 5).
6. Lua scripting engine (Phase 7).
