# Shield research notes — Dofus Retro 1.48 / Hystoria V5

Consolidated findings from:

- `xkenzzo31/dofus-retro-deobfuscator` repo (README + `DOCS.md` + the 639
  captured Shield API call pairs in `data/security_api_calls.json`).
- Cadernis.fr thread **#3262** *"Deobfuscation du client Dofus Retro 1.48 —
  Reverse engineering du Shield V8"* (xkenzzo31, 37 replies, April 2026).
  Quoted verbatim below where it adds information beyond the repo.
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

The wire layout is:

```
<raw_packet> \xf9 <b64(iv_rand)[24]> <b64(ct3)[108]>
```

Exactly **one** `\xf9` marker, sitting right after the plaintext packet.
No separator between `b64(iv)` and `b64(ct)`. No trailing marker.
Confirmed by inspecting all 81 `applyPacketToSendPostProcessing` captures
in `security_api_calls.json`: every result starts with one `\xf9` at
position 0 (the captured return value is the suffix only — the raw
packet is prepended by the caller before the socket write).

| Section     | Size         | Notes                                             |
| ----------- | ------------ | ------------------------------------------------- |
| `\xf9`      | 1 byte       | Delimiter, outside the Dofus 1.29 charset.        |
| `b64(iv)`   | 24 bytes     | 16-byte random IV, base64 with `==` padding.      |
| `b64(ct)`   | 108 bytes    | 80-byte AES output (ct3) base64-encoded.          |
| **total suffix** | **133 bytes** | Same length regardless of the raw packet.    |

The DOCS.md draft which mentioned "`raw + \xf9 + b64(iv) + b64(ct) + \xf9`"
(2 markers) and the earlier "3 marker" hypothesis are **wrong** — they
predate the capture collection. `shield_signer.py` was patched in commit
`8b7391a` to emit the correct 1-marker form.

**Reality-check against truncated captures**: the capture tool caps the
result string at 200 chars + `"..."` (all 81 results land at exactly 203
chars with `"..."` at the end), so we can only verify the first 200
bytes. Within those 200 bytes there is exactly 1 marker at position 0.
If a second marker existed it would sit at position 25 — it doesn't.
The expected full length is 133 bytes, well below the 200-byte cap, so
the observed truncation at exactly 200 means the real output is longer
than what we inferred. Two possibilities worth verifying once we have
the real keys:

1. ct3 is actually longer than 80 bytes (e.g. the chain is applied
   twice or a telemetry payload is appended). This would push the
   total past 200 and explain the uniform 203-char cap.
2. The capture tool stringifies a Buffer/Uint8Array via `toString()`
   which stops at the first non-latin-1 byte — but that would not
   produce a uniform 200-char cutoff, so it's unlikely.

Hypothesis 1 is the one to test: run `signer.sign_with_iv(raw, iv,
signature_only=True)` against the real keys, compare to the captured
200-char prefix, and if we match byte-for-byte up to the cut we know
our chain is right and we just need to find what gets appended (if
anything).

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
