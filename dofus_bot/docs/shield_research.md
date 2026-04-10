# Shield research notes — Dofus Retro 1.48 / Hystoria V5

Consolidated findings from:

- `xkenzzo31/dofus-retro-deobfuscator` repo (README + `DOCS.md` + the 639
  captured Shield API call pairs in `data/security_api_calls.json`).
- Cadernis.fr thread **#3262** *"Deobfuscation du client Dofus Retro 1.48 —
  Reverse engineering du Shield V8"* (xkenzzo31, 37 replies, April 2026).
  Quoted verbatim below where it adds information beyond the repo.
- **Cadernis.fr thread #2952** *"Retro — Nouvelle signature `ù` dans les
  packets envoyes"* (2 pages, 20+ replies). Contains:
  - **Eleko, msg 2**: measured signature length = **16 bytes IV + 208
    bytes ciphertext** on 1.39.9 build. This **contradicts** our
    earlier 80-byte ciphertext guess and means the chain is more
    complex than we thought.
  - **lagrangian, msg 9**: "plusieurs clés, flags, ivs aléatoires,
    ivs statiques, sentinelles, token d'intégrité, hash d'infos sur
    la machine". Shield is a multi-key, multi-IV state machine with
    sentinels and a machine-info hash — not a simple AES chain.
  - **rtab, msg 16**: full `@electron/remote` + TCP RPC payload that
    turns the running Electron client into a signing oracle (see
    `signing_strategies.md` §1 architecture B2). **Flagged** on
    official servers since 2-3 months per Brizze (p2).
  - **Killersarea, msg 12**: "Ne tente pas de reverse le jsc, perte
    de temps. Utilise les fonctions du jsc via le client même mais
    **sans le client entier** — il y a d'autres packets antibot que
    la signature, pas que ça."
- Cadernis thread **#3092** *"Détection hook packets non chiffrés"*
  (LinningSilver) — server does not reject unsigned packets instantly
  but flags for human moderation review on **official** servers. On
  private servers like Hystoria there is no moderation team.
- Cadernis thread **#3240** *"MITM Dofus Retro packets send ignorés"*
  (Duke Toland) — confirms unsigned packets work on a private server
  but silently fail when the path doesn't match server-side pathfinding
  cost model.
- Adjacent Cadernis threads on 1.29 MITM (#1633, #1650, #2476, #3039)
  used for the auth flow reference — see `auth_flow_1_29.md`.

This file is meant to be the single source of truth when we touch
`shield.py`, `shield_signer.py`, or the proxy write path. Update it
when we get new vectors.

---

## 1. Architecture confirmed

```
Flash SWF (Dofus 1.29 game logic)
   │ packet to send (plaintext 1.29 text protocol)
   ▼
D1ElectronLauncher (renderer, PepperFlash plugin)
   │ IPC: "shield-hash"
   ▼
main.jsc Shield module  (V8 8.7 bytecode, bytenode-compiled)
   ├── applyPacketToSendPostProcessing(packet)   ← signs outgoing
   ├── getRandomNetworkKey()                      ← connection key + fingerprint
   ├── getTelemetry(challenge, ctx)               ← server anti-cheat response
   ├── getSystemInformation()                     ← hardware fingerprint
   ├── parseBasicCryptedPacket()                  ← decrypts incoming login handshake
   └── cryptBasicPacket()                         ← encrypts outgoing login handshake
```

Source: `xkenzzo31/dofus-retro-deobfuscator` `DOCS.md` lines 320-360. The
IPC bridge between the Flash client and the Electron Shield module is
the single point where an observer could hook cleanly (no need to read
V8 bytecode). It is also where `onPacketSent` sees the *plaintext*
packet — confirmed by the captures where `onPacketSent` args are always
readable strings (`"1.48.2e|fr"`, `"Af"`, `"GC1"`, etc.).

> **xkenzzo31, thread #3262 msg 16**:
> "le jeux et lancer dans un electron qui utilise un vieux plugin
> papperflash pour executer le client Flash de dofus rétro. le client
> flash construit des requête que le electron signe. côter electron ta
> tout un tas de méthode de vérifications il utilise une biblihothèque
> qui renvois les info de ta machine et il ce serve de ça comme anti
> bot."

## 2. Signing flow (4-step AES-256-CBC chain)

```
counter_str = format(counter, "05d")            # "00000", "00001", ...
hash        = SHA256(raw_packet + counter_str)  # 32 bytes
ct1         = AES_CBC(hash, key=hash_array[k1], iv=static_iv, pad=PKCS7)   # 48 bytes
ct2         = AES_CBC(ct1,  key=hash_array[k2], iv=static_iv, pad=PKCS7)   # 64 bytes
iv_rand     = crypto.randomBytes(16)
ct3         = AES_CBC(ct2,  key=wrap_key,       iv=iv_rand,   pad=PKCS7)   # 80 bytes
counter    += 1
```

- **Algorithm**: AES-256-CBC via **CryptoJS** (not Node.js native `crypto`).
- **Padding**: PKCS7.
- **Keys**: 9 AES-256 keys in a `hash_array` closure, plus 2 wrap keys
  (some builds only use one). `k1` and `k2` are two slots into
  `hash_array` — assumed constant per connection.
- **`static_iv`**: 16 bytes, derived at `init()` from the hash chain,
  stays fixed for the session.
- **Counter**: 5-digit zero-padded decimal. Must stay in lockstep with
  the server — MITM mode must bump it for every legitimate client
  packet we see on the wire, not just ours.

## 3. Output format (verified against captures)

**Update 2026-04-10** — the ciphertext is **longer** than we initially
inferred. Both the live Hystoria traffic (`+shield(304)` lines in the
proxy) and Eleko's direct measurement on a 1.39.9 build agree:

```
\xf9 + b64(iv, 16 bytes) + b64(ct, 208 bytes)
   1 +    24 chars       +    280 chars       = 305 bytes of suffix
```

Exactly **one** `\xf9` marker at position 0. No separator between
`b64(iv)` and `b64(ct)`. No trailing marker. The 304 byte count we
observe in the `(stripped 304 bytes, payload=16 bytes)` proxy log is
(305 - 1) because the marker is accounted for separately in the
stripper.

**The ciphertext is NOT 80 bytes**, contrary to our first hypothesis
based on the 200-char truncation of `security_api_calls.json`. See §3b
below.

The wire layout is:

```
<raw_packet> \xf9 <b64(iv_rand)[24]> <b64(ct)[280]>
```

Confirmed by inspecting all 81 `applyPacketToSendPostProcessing` captures
in `security_api_calls.json`: every result starts with one `\xf9` at
position 0 (the captured return value is the suffix only — the raw
packet is prepended by the caller before the socket write).

| Section     | Size         | Notes                                             |
| ----------- | ------------ | ------------------------------------------------- |
| `\xf9`      | 1 byte       | Delimiter, outside the Dofus 1.29 charset.        |
| `b64(iv)`   | 24 bytes     | 16-byte random IV, base64 with `==` padding.      |
| `b64(ct)`   | 280 bytes    | 208-byte AES output (ct_final), base64-encoded.   |
| **total suffix** | **305 bytes** | Same length regardless of the raw packet.    |

### 3b. Why we were wrong about 80 bytes

Our first reading came from `security_api_calls.json`, where the
capture tool caps every string result at 200 chars + `"..."`. Within
that 200-char window we saw 1 marker + 24 chars of `b64(iv)` + 175
chars of `b64(ct_prefix)`, and extrapolated a **"133 byte total"**
assumption that matches an 80-byte ct3.

This was wrong because the capture was truncated. On live Hystoria
traffic we consistently see `+shield(304)` — i.e. 304 bytes of
stripped suffix (after the marker). That's `24 + 280 = 304`, which
means `b64(ct)` is 280 chars, which means `ct` is **208 bytes**.

Eleko's independent measurement on a 1.39.9 build in thread #2952
also reports 16 + 208. This is **three independent confirmations**
(our Hystoria proxy, Eleko's 1.39.9 capture, and the capture tool's
exact 203-char uniform cutoff) that the real ciphertext is 208 bytes.

### 3c. What this means for the signer chain

Our current `shield_signer.py` applies 3 AES-256-CBC rounds and
produces an 80-byte ciphertext:

- Input to round 1: 32 bytes (SHA-256 output) → ct1 = 48 bytes (32 +
  PKCS7 pad to next 16-byte boundary)
- ct2 = AES(ct1, k2) → 64 bytes
- ct3 = AES(ct2, wrap_key) → 80 bytes

For the output to be 208 bytes we need the **plaintext to the last
AES round** to be 192-208 bytes (200-ish after PKCS7 padding to the
next 16-byte boundary). Possible sources of those extra bytes:

1. **Nested chain** — the simple 3-round chain is applied to a
   **longer input**, e.g. `SHA256(...) || machine_hash || counter_str ||
   sentinel`. A machine fingerprint blob of ~160 bytes would land us
   at 32 + 160 = 192, pad to 208 after PKCS7. Matches lagrangian's
   "hash d'infos sur la machine" + "token d'intégrité" quote.
2. **More rounds** — if every round adds 16 bytes (input of N gets
   padded to N+16), getting from 32 to 208 needs 11 rounds. Plausible
   but ugly.
3. **Output concatenation** — chain produces ~80 bytes and is
   concatenated with a 128-byte telemetry blob (which is itself
   AES-encrypted with a different key, matching lagrangian's
   "plusieurs clés"). The whole 208-byte thing is then the final
   `b64(ct)` payload.

Hypothesis 1 (long plaintext to a short chain) is the cleanest fit
and matches the "sentinelles" language. Hypothesis 3 is the best fit
if the signer is actually two parallel primitives mashed together.
**We can disambiguate these empirically once we have real keys** by:

- Decrypting a live captured ciphertext with the extracted wrap key
  and the IV from the suffix.
- Inspecting the decrypted plaintext to see if it's a chain output
  (opaque 32-byte-aligned binary) or a structured blob (identifiable
  fields like version strings, MAC addresses, etc.).

The DOCS.md draft which mentioned "`raw + \xf9 + b64(iv) + b64(ct) + \xf9`"
(2 markers) and the earlier "3 marker" hypothesis are **wrong** — they
predate the capture collection. `shield_signer.py` was patched in commit
`8b7391a` to emit the correct 1-marker form.

**Reality check against truncated captures — resolved.** Hypothesis 1
(ct is longer than 80 bytes) is confirmed. See §3b above. The
uniform 203-char cutoff across all 81 captures is the capture tool's
`result.slice(0, 200) + "..."` stringification, **not** the real
output length. The real output is 305 bytes (1 marker + 24 b64(iv) +
280 b64(ct)), matching live Hystoria traffic.

## 4. Related primitives — not the same format

Two other Shield functions leak AES ciphertext but use a *different*
framing — **no `\xf9` marker at all**:

- **`getRandomNetworkKey()`** — returns a 560-char base64 key sent as
  `Ai2<key>` at connection setup. Contains (encrypted) username, system
  info, and system hash. Format: `b64(iv) + b64(ct)` directly
  concatenated, no markers. Confirmed on 3 captured calls, e.g.
  `"/qwYPJVf6T1u2Duj19zZcQ==TR/Tl/55WouiE3zPZohPmxR..."`.
- **`getTelemetry(challenge, ctx)`** — called every ~30s in response to a
  server challenge. Same `b64(iv) + b64(ct)` layout as
  `getRandomNetworkKey`. Captured 4 times.

The `\xf9` marker is therefore specific to the *wire framing* of outgoing
game packets, not to the underlying AES primitive. Our signer handles
this by exposing `signature_only=True` which drops the raw prefix and
returns `\xf9 + b64(iv) + b64(ct)`; for `getRandomNetworkKey` /
`getTelemetry` we will need a separate helper that returns
`b64(iv) + b64(ct)` without the marker.

## 5. Anti-cheat scanning — AVOID THESE TOOLS

Per `DOCS.md` §"Anti-Cheat Scanning" and confirmed by LuthTeur#7938 in
thread #3262, the Shield module scans the host process list **every ~30
seconds** and bans accounts that have any of the following running:

| Category             | Tools flagged                                          |
| -------------------- | ------------------------------------------------------ |
| Debuggers            | x64dbg, OllyDbg, WinDbg, gdb, lldb                     |
| Reverse engineering  | IDA Pro, Ghidra, Radare2, Binary Ninja                 |
| **Network sniffers** | **Wireshark, Fiddler, Charles Proxy, mitmproxy**       |
| Memory editors       | Cheat Engine, ArtMoney, GameGuardian                   |
| **Instrumentation**  | **Frida, Xposed, Substrate**                           |
| Process monitors     | Process Explorer, Process Hacker, API Monitor          |

> **LuthTeur#7938, thread #3262 msg 15**:
> "leur shield ping toutes les 30secondes et analyse, et de ce que j'ai
> vu frida est dans les triggers"
>
> **LuthTeur#7938, thread #3262 msg 12**:
> "Je l'ai utilisé au debut et je suis passer a un tool plus perso
> pour eviter les triggers justement"

Concrete implications for us:

1. **Do not run Frida on a machine that is also logged in to an
   Hystoria account.** Our key-extraction must happen on a throwaway
   client that never authenticates (use `--inspect-brk`, grab keys
   before login, kill the client).
2. **Our asyncio TCP proxy is not on the list by default** — the
   process is a plain `python3`, not named `mitmproxy`. We should keep
   it that way: never rename the entrypoint to anything that matches
   the substring, and don't run `mitmproxy` / `mitmdump` alongside the
   client even as a parallel tool.
3. **Wireshark captures should be done from a different machine** (a
   span port, another box on the LAN, a VM network tap). Do not install
   `wireshark.exe` on the same Windows host as the Dofus client.
4. The xkenzzo31 account used to collect `security_api_calls.json`
   got banned mid-session — evidence: the `mI1\ue004...Triche` packet
   in the captures, which is the stock "cheat detected" server message.
   The ban happened during *their* Frida hooking session. Don't repeat
   the same mistake.

## 6. Current deobfuscation status (xkenzzo31's repo)

- **84%** of the 8611 functions in `main.jsc` are fully decompiled and
  valid per Babel validation.
- The V8 8.7 Ignition bytecode pipeline (Docker + patched V8 + Python
  decompiler + webcrack string resolution) is functional.
- The string array / control-flow obfuscation (obfuscator.io layer) is
  **not fully broken**. This is the layer that hides the literal hex
  key bytes inside the decompiled JS.
- Llith#4960 asked in thread #3262 msg 19 whether the tool produces a
  clean version of `applyPacketToSendPostProcessing` on Boune
  (`kdofusretro-ga-boune.ankama-games.com`) — no one has posted such a
  clean decompile as of msg 20. **We don't have a human-readable
  reference implementation of the function yet.**

> **xkenzzo31, thread #3262 msg 13**:
> "J'arrive à dépiler le V8 avec Claude mais je reste bloqué sur
> obfuscator.io on a quand même pas mal d'infos coter client mais je
> suis preneur si des personnes techniquement savent reverse la couche
> obfuscator.io"

## 6b. Cadernis #2952 synthesis — what the regulars actually know

Thread #2952 is the single most important thread on the forum for our
purposes. Four takeaways beyond what's in §1-§6 above:

1. **Eleko** — 16 bytes IV + 208 bytes ct. See §3b.
2. **rtab** — full working RPC oracle payload (architecture B2 in
   `signing_strategies.md`). Paste at
   `/tmp/cadernis/threads/retro-nouvelle-signature-xc3-xb9-dans-les-packets-envoyes.2952.html`
   (extracted verbatim from the `<pre>` tag in the `bbWrapper`):

   ```js
   require('@electron/remote').BrowserWindow.fromId(1).webContents
     .executeJavaScript(`(()=>{
       const net = require('net');
       function getFn() {
         const f = window.applyPacketToSendPostProcessing;
         if (typeof f !== 'function') throw new Error('prob applyPacketToSendPostProcessing');
         return f.bind(window);
       }
       const OPC_APPLY = 1;
       const u32 = (b, o) => b.readUInt32LE(o);
       const w32 = n => { const b = Buffer.allocUnsafe(4); b.writeUInt32LE(n, 0); return b; };
       const server = net.createServer(sock => {
         /* length-prefixed framing: [4-byte len][1-byte opcode][payload] */
         /* on OPC_APPLY: read payload as UTF-8, call getFn()(payload),
            reply with [4-byte len][result-bytes] */
       });
       const PORT = 31339;
       server.listen(PORT, '0.0.0.0', () => { console.log('signer ready on ' + PORT); });
       return 'OK';
     })()`, true)
   ```

   Our use: after the Electron client has loaded its Shield module
   but BEFORE we log in, we inject this payload via Chrome DevTools
   (since `@electron/remote` requires a renderer context and the
   DevTools console runs there). Then our Python proxy connects to
   `127.0.0.1:31339` as a local RPC client. Every time the Lua API
   wants to inject a packet, the proxy sends the plaintext over the
   RPC and the client returns the signed form.

3. **Brizze, page 2**: the RPC-oracle trick is **flagged** on
   official Ankama servers — their integrity monitoring catches the
   `@electron/remote` + `executeJavaScript(...)` IPC signature. Quote:
   > "Ouais ça fait 2-3 mois que cette méthode est détectée, perso
   > j'ai tous mes comptes bannis sur celle-là. Si tu veux jouer
   > avec ça sur officiel oublie."

   **Hystoria V5 is not official** — no integrity monitoring team,
   most likely no detection for this. Still: we should not
   advertise this usage publicly and we should keep the RPC oracle
   as an opt-in fallback, not the default.

4. **Killersarea + lagrangian** both agree: trying to reverse-engineer
   the obfuscated `main.jsc` is a multi-year rabbit hole. The
   pragmatic path is to either (a) use the client as an oracle, or
   (b) build a pure-socket bot and hope the private server doesn't
   enforce signatures.

## 7. Key extraction strategies, ranked by safety

| # | Strategy                                   | Risk  | Effort | Status |
| - | ------------------------------------------ | ----- | ------ | ------ |
| 1 | `--inspect-brk` + Chrome DevTools scope walk on `Shield.init` (client never logs in) | Low   | Low    | **Recommended — recipe in `README.md`**  |
| 2 | Static analysis of decompiled `main.jsc` once xkenzzo31 breaks the obfuscator.io layer | Low   | High   | Waiting on upstream.                     |
| 3 | Custom V8 hook via D1ElectronLauncher debugger API (same idea as #1, no devtools UI) | Low   | Med    | Fallback if DevTools is blocked.         |
| 4 | Frida `Interceptor.attach` on `applyPacketToSendPostProcessing` from a throwaway VM | **High** | Low   | **Avoid** — Frida is on the detection list. |
| 5 | CPU-side side-channel / cold-boot attack   | ?     | Absurd | Don't.                                   |

Strategy 1 is what our current `README.md` §"Shield" documents, and it
remains the right path.

## 8. Immediate verification plan once keys land

1. Drop the extracted keys into `dofus_bot/data/shield_keys.json`.
2. Run `tools/validate_shield_signer.py` (to be written, next task)
   which does:
   - Load `security_api_calls.json`.
   - For each `applyPacketToSendPostProcessing` call, extract the
     b64(iv) from the captured result's bytes 1-25, decode it.
   - Call `signer.sign_with_iv(raw, iv_bytes, signature_only=True)`
     with `counter` = the inferred global packet counter at that
     timestamp.
   - Compare `our_result[:200]` to `captured_result[:200]` byte-for-byte.
   - Green: chain is correct. Red: iterate on slot_k1 / slot_k2 /
     ct length hypothesis.
3. Wire `signer.sign()` into `proxy.send_to_server()` and shadow-run
   for a few hours before the MITM bot actually injects anything.
4. If the shadow comparison is stable, enable injection and test with a
   throwaway character.

## 9. Reference — reply from Llith about the function name

> **Llith#4960, thread #3262 msg 19**:
> "Ca a l'air interessant ton projet, je serais curieux pour voir, sur
> boune, ils utilisent une fonction nomée `applyPacketToSendPostProcessing`
> pour signer les paquets, est-ce que ton tool arrive a reconstituer une
> version lisible de cette fonction ?"

The function name `applyPacketToSendPostProcessing` is thus confirmed as
the canonical Shield entry point on the Boune test server. Our signer
module uses the same name in its docstrings, which matches the ecosystem
vocabulary.
