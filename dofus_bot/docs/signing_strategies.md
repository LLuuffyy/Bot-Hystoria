# Packet signing — architectural options

This doc exists because the Cadernis scrape (thread #2952 "Nouvelle
signature `ù` dans les packets envoyés" and a dozen adjacent threads)
turned up **evidence that our current Shield signer assumptions are
partially wrong** and that there are multiple viable architectures for
running a bot against a 1.29 Retro server. We need to pick one with
eyes open.

---

## 1. The three architectures

### A. Full socket — emulate the client from scratch

```
Python asyncio bot  <---- TCP ---->  Hystoria game server
       (no client running)
```

- We build the packets ourselves from the 1.29 text protocol.
- We must reproduce the `\xf9` Shield signature for every outgoing
  packet, **or** confirm the Hystoria server accepts unsigned packets.
- Reference: kralamoure/retroproto, Emudofus/Shivas.

**Pros**
- Zero dependency on a running Dofus client.
- Headless, scriptable, parallelisable.
- No UI clicks → no click-detection anti-cheat surface.
- Single artifact to ship to the user.

**Cons**
- Requires either (a) the full Shield signing chain keys + algorithm
  or (b) a server that accepts unsigned packets.
- 208-byte ciphertext per packet (see §3 below) — the chain is more
  involved than the 80-byte one we initially coded.
- lagrangian (thread #2952): "plusieurs clés, flags, ivs aléatoires,
  ivs statiques, sentinelles, token d'intégrité, hash d'infos sur la
  machine". Beyond the signature, Shield sends **other** anti-bot
  packets. Missing any of those = soft-ban signal.

**Feasibility on Hystoria**: **unknown, but plausibly high** — it's a
private 1.29 server, so the classic emulator stack (Shivas-like) most
likely doesn't validate Shield signatures at all. Testing this is
`status_plan.md` TEST #1, and is the cheapest experiment to run.

### B. MITM + client as signing oracle (our current approach)

```
Dofus client  <---- TCP ---->  dofus_bot proxy  <---- TCP ---->  server
                    ^
                    |
            bot: sees every packet,
            injects its own (signed by... ?)
```

- We run the real Dofus client alongside the bot.
- Incoming packets are stripped of their Shield suffix and parsed.
- Outgoing packets from the client pass through untouched.
- **Injected** packets (from Lua scripts) need a valid signature.

Two sub-options for getting the signature:

- **B1. Local signer with extracted keys.** Pull `hash_array`,
  `wrap_key`, `static_iv` from the running Electron via
  `--inspect-brk` + DevTools scope walk, drop them into
  `shield_keys.json`, and sign locally using the code in
  `shield_signer.py`. Requires getting the algorithm right.
- **B2. Client-as-oracle via RPC (rtab's payload).** Use
  `@electron/remote` to inject a TCP server inside the renderer
  process that calls `window.applyPacketToSendPostProcessing(raw)`
  on every RPC. Our proxy sends the plaintext, gets back the signed
  form, writes it to the server.

**B1 pros**
- Deterministic, offline, no side-channel surface.
- Once the keys are in, we never need to touch the client again.

**B1 cons**
- Algorithm is **not fully understood**. Our current `shield_signer.py`
  assumes a 3-step AES chain producing an 80-byte ciphertext.
  **Eleko in thread #2952 explicitly says the signature is 16 bytes
  (iv) + 208 bytes (ct) on 1.39.9 builds**, which means either:
  1. The chain has more rounds than we think.
  2. There's an extra telemetry/token blob appended.
  3. Version 1.48 differs from 1.39.9 and we got lucky.
  Until we match a captured vector byte-for-byte we can't ship this.
- Key slot selection (k1, k2) may depend on packet prefix or counter.

**B2 pros**
- Correct by construction. Uses the real function from the real
  client. Zero reverse engineering.
- Already has a working payload (thread #2952 msg 16, rtab).

**B2 cons** — these are the killer ones:
- **Brizze (thread #2952 page 2)**: "Je confirme que cette méthode
  est flaggée, ça fait 2-3 mois qu'ils détectent les sessions qui
  utilisent `@electron/remote` pour appeler `executeJavaScript`
  depuis l'extérieur." The RPC pattern itself is detected on
  **official** servers.
- Adds a TCP dependency on the client (if the client crashes, no
  more signatures, bot dies).
- Increases bot latency per packet (sync RPC call across process
  boundary).
- Unknown if Hystoria detects this — but it's a Dofus private server,
  so most likely **no**.

### C. UI automation — drive the real client via mouse/keyboard

```
Dofus client (full graphical window)
       ^
       | mouse/keyboard events via user32.dll / xdotool
       |
  dofus_bot (Python) + OCR / pixel detection
```

- Example in the wild: **Azzary/NebulaR-Bot** (cremi532's share in
  thread #2990). C# bot, user32.dll clicks, Lua scripting on top of
  `WindowManager:Click(...)`, `botInstance:LauchSpell(...)`,
  `botInstance:GetTurn()`, etc.
- No packet forging. No Shield concerns. The packets going out are
  the ones the real client sends in response to our synthetic clicks.

**Pros**
- **Completely bypasses Shield.** Shield sees legit clicks → legit
  packets with valid signatures. We never touch the wire.
- Existing reference implementation (Nebular) that works on Retro
  servers.
- anon + kerop in thread #3122: "Tu te feras pas ban avec un bot
  click... je fais tourner un bot click sur Retro depuis des mois."
- Works on ANY server (official or private) because it's transport
  agnostic.

**Cons**
- Requires a visible client window (no headless, no cloud).
- OCR / pixel detection is fragile (resolution changes, theme
  changes, chat overlay, effects during combat).
- Combat detection via frames is slower than combat detection via
  packets (~100ms lag for screen capture + detection loop).
- Cannot run multiple instances easily on one machine.
- Clicks are detectable IF the anti-cheat checks click provenance
  (SendInput vs hardware) — thread #3136 discusses this: anon
  reports SendInput is **not** flagged on Retro, but that's the
  official client, not private servers.

**Feasibility on Hystoria**: very high, but UX-degraded (must keep the
client window open, visible, with no other app covering it).

## 2. Decision matrix

| Criterion                          | A. Full socket | B1. Local signer | B2. Client oracle | C. UI clicks |
| ---------------------------------- | -------------- | ---------------- | ----------------- | ------------ |
| Works on Hystoria if no Shield     | ✅              | ✅                | ✅                 | ✅            |
| Works on Hystoria if Shield on     | ❌              | ⚠️ (need keys)   | ⚠️ (detectable)   | ✅            |
| Works on official Ankama 1.48      | ❌              | ⚠️ (detectable)  | ❌ (flagged)       | ⚠️ (SendInput debate) |
| Headless                           | ✅              | ❌                | ❌                 | ❌            |
| Latency (ms / action)              | ~5             | ~5               | ~50                | ~150          |
| Implementation effort              | Low (IF §3 OK) | **Very high**    | Medium            | Medium        |
| Risk of false-positive on detect   | Low            | Medium           | **High**          | Low           |

## 3. Signature length — we were wrong

Our current `shield_research.md` and `shield_signer.py` assume the
ciphertext is 80 bytes (= 108 chars base64). This came from inferring
the length from the truncated 200-char captures in
`security_api_calls.json`.

**Eleko, Cadernis thread #2952 post 2**, captured on a real 1.39.9
build:

> "J'ai check, la signature fait 16 bytes d'IV + 208 bytes de
> ciphertext. C'est du AES-CBC classique mais il y a clairement un
> padding + un blob additionnel à la fin."

16 + 208 = **224 bytes of raw crypto output**, which encodes to:

```
b64(16 bytes) + b64(208 bytes) = 24 + 280 = 304 chars
```

Plus the 1-byte `\xf9` marker = **305 bytes of suffix**.

That matches the `(stripped 304 bytes, payload=16 bytes)` line we
already log in the proxy on real Hystoria traffic (see
`README.md` §"Cote lecture"). **This is our confirmation that Hystoria
uses the same Shield format as Ankama's 1.48 build.**

Note: 304 bytes of stripped signature on Hystoria `\xf9` proves the
suffix length. It does **not** prove the server validates it. The
server still might accept anything after the `\xf9` on the wire — or
nothing at all. TEST #3 in `status_plan.md` is the one that answers
this.

### What changes in our signer

- `hash_array` keys, `static_iv`, `wrap_key` — probably still correct
  in count and placement, per xkenzzo31's DOCS.md.
- The number of **rounds** is wrong. Either:
  1. More than 3 AES-CBC rounds (4, 5, or a loop over all 9 slots).
  2. The output is `AES_chain(hash)` **concatenated** with a machine
     telemetry blob (MAC address hash, CPU info, etc.).
  3. Both.
- `counter` string formatting is probably still correct (5-digit
  zero-padded decimal).

### What we can do NOW

- Keep `shield_signer.py` as the **skeleton**. Its step 1 (SHA256 of
  `raw + counter_str`) and the AES-CBC primitive are both reusable.
- Add a `target_ct_len` parameter to the signer and make it
  configurable. Default remains 80 bytes (matches what we see in the
  200-char capture prefix), and a new `208` mode matches Eleko's
  observation.
- Add a `telemetry_blob` appender slot that returns a configurable
  pad when we find out what's in there.
- Write a `tools/validate_shield_signer.py` that reads a captured
  suffix from a live Hystoria session (via our existing proxy
  `--dump` mode) and tells us:
  1. What the real suffix length is on Hystoria specifically.
  2. Which byte positions are random (entropy > 6 bits per byte) vs
     deterministic (low entropy, maybe counter / MAC / version).

## 4. Recommendation

**Pursue architecture A (full socket) with the hypothesis that
Hystoria does not validate Shield signatures.** Fall back to B2 if
that fails. Do not invest in B1 until we have real captured vectors
to validate against.

Concretely:

1. **TEST #1 — Raw socket handshake** (see `status_plan.md`). This
   tells us whether we can even do the auth handshake without a real
   client.
2. **TEST #3 — Unsigned GA0 move.** If that works, we're done with
   Shield for the Hystoria scope.
3. If TEST #3 fails, fall back to architecture B2: use the existing
   MITM proxy + rtab's RPC payload to get the client to sign for us.
   The "detectability" concern from thread #2952 only applies to
   official Ankama servers. On a private server with no integrity
   monitoring team, we have zero evidence this is flagged.
4. Keep architecture C as a **strategic fallback** — document the
   Nebular codebase structure in `dofus_bot/docs/nebular_reference.md`
   so we can pivot fast if both A and B fail.

## 5. References

- **Thread #2952** — retro-nouvelle-signature-`ù`-dans-les-packets-envoyes
  - Eleko (msg 2) — signature is 16 + 208 bytes
  - rtab (msg 16) — `@electron/remote` + TCP RPC oracle payload
  - lagrangian (msg 9) — "plusieurs clés, flags, ivs..."
  - Brizze (p2) — RPC oracle detected since 2-3 months
  - Killersarea (msg 12) — "Ne tente pas de reverse le jsc, perte
    de temps"
- **Thread #2990** — nebular-bot-dofus-retro
  - cremi532 (msg 1) — shares Azzary/NebulaR-Bot repo
- **Thread #3124** — creation-mitm-rediriger-la-connection-hook
  - lagrangian — pro tips on Electron/CEF hooking, Frida, Thrift
- **Thread #3092** — detection-hook-packets-non-chiffres
  - LinningSilver — server does not reject unsigned packets
    instantly (flags you for review)
- **Thread #3240** — mitm-dofus-retro-packets-send-ignores-par-le-serveur
  - Duke Toland — unsigned packets accepted on private server but
    hit pathfinding mismatch
- **Thread #3122** — detection-des-clics-synthetiques
  - anon + kerop — SendInput not flagged on Retro
- **Thread #3136** — simulation-de-clics-via-injection-dll-detectable
  - companion to #3122
- **xkenzzo31/dofus-retro-deobfuscator** — chain skeleton +
  captured vectors (639 pairs)
- **Azzary/NebulaR-Bot** — reference UI-automation bot
