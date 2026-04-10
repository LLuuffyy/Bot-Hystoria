"""Shield packet signer for Dofus Retro 1.48 / Hystoria V5.

This is the write-side counterpart to :mod:`dofus_bot.protocol.shield`.
Reading is trivial — the Shield module only appends a signature to
outgoing packets, so stripping the ``\\xf9`` suffix is enough to get
the raw text back. Writing is the hard part: if we want the server to
accept an injected packet (``bot:cast``, ``bot:move_to``, etc.), that
packet needs a cryptographically valid Shield signature.

Flow (reverse-engineered from the stock 1.48 Electron client, see
``https://github.com/xkenzzo31/dofus-retro-deobfuscator`` README and
the companion notes in ``/tmp/dofus-deob/DOCS.md``):

.. code-block:: text

    counter_str = format(counter, "05d")            # "00000", "00001", ...
    hash        = SHA256(raw_packet + counter_str)  # 32 bytes
    ct1         = AES-256-CBC(hash, key=hash_array[k1], iv=static_iv, PKCS7)
    ct2         = AES-256-CBC(ct1,  key=hash_array[k2], iv=static_iv, PKCS7)
    iv_rand     = os.urandom(16)
    ct3         = AES-256-CBC(ct2,  key=wrap_key,      iv=iv_rand,   PKCS7)
    output      = raw_packet + "\\xf9" + b64(iv_rand) + b64(ct3)
    counter    += 1

The 9 ``hash_array`` keys and the 2 wrap keys are extracted **once**
from a live client (via Chrome DevTools scope walk on ``Shield.init``
— see ``dofus_bot/README.md`` section "Shield") and dropped into a
``shield_keys.json`` file. The signer loads them at startup.

This module deliberately does NOT read the key file on import: that's
the caller's responsibility so we can swap keys at runtime (for tests
or multi-account setups) and so importing ``dofus_bot.protocol`` never
blows up just because keys aren't configured yet.

Output format — confirmed against captures
-------------------------------------------

We ship with the format that matches the 639 captured Shield API call
pairs in ``data/security_api_calls.json`` (see
``https://github.com/xkenzzo31/dofus-retro-deobfuscator``). In those
captures, ``applyPacketToSendPostProcessing(raw)`` returns a string
that:

* starts with **exactly one** ``\\xf9`` marker at position 0,
* is followed by ``base64(iv_rand)`` (24 chars for a 16-byte IV),
* then ``base64(ct3)`` concatenated directly (no additional marker),
* has **no trailing marker**, and
* **does not** re-include the raw input.

The game code then prepends ``raw`` before writing to the socket, so
the wire layout is:

.. code-block:: text

    raw + b"\\xf9" + b64(iv_rand) + b64(ct3) + b"\\x00"   # \\x00 is the frame terminator

This is what :meth:`ShieldSigner.sign` returns by default. If you need
the raw signature suffix only (e.g. to reproduce the stock
``applyPacketToSendPostProcessing`` return value), pass
``signature_only=True`` — useful when replaying captured vectors.

The previous 2-marker and 3-marker legacy modes from early DOCS.md
drafts were never observed in real captures and have been removed.

Open questions (still unresolved):

* Which ``k1`` and ``k2`` slots are used (constant? derived from the
  packet prefix? from the counter? from the length?). Default here is
  "constant per connection, set in the keys file", which matches the
  common reverse-engineering pattern — revisit once we can validate
  against real keys + vectors.
* Counter initialisation — probably 0 after ``Shield.init()`` but the
  server might expect a non-zero starting value on resume. For now we
  start at 0 and let the caller override via ``SignerConfig.counter``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import List, Optional

try:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    _HAS_CRYPTOGRAPHY = True
except ImportError:  # pragma: no cover - optional runtime dep
    _HAS_CRYPTOGRAPHY = False

from .shield import SHIELD_MARKER

logger = logging.getLogger(__name__)

#: AES-256 expects a 32-byte key.
KEY_SIZE = 32
#: AES block size, also the IV length for CBC mode.
BLOCK_SIZE = 16
#: Counter is formatted as a zero-padded decimal string of this width.
COUNTER_WIDTH = 5


class ShieldSignerError(Exception):
    """Raised when the signer cannot produce a valid signature."""


class MissingCryptographyError(ShieldSignerError):
    """Raised when the ``cryptography`` library is not installed."""

    def __init__(self) -> None:
        super().__init__(
            "The 'cryptography' package is required for Shield signing. "
            "Install it with: pip install cryptography"
        )


@dataclass
class ShieldKeys:
    """Keys extracted from a live Dofus Retro 1.48 client.

    All byte fields are stored as raw bytes (not hex strings). The
    :meth:`from_json` / :meth:`from_dict` loaders accept hex input.

    Attributes
    ----------
    hash_array:
        The 9 AES-256 keys captured from the closure around
        ``Shield.applyPacketToSendPostProcessing``. Order MUST match
        the order observed in the client — slots are referenced by
        index in the signing flow.
    wrap_key:
        The outer AES-256 key used in step 4 (``ct3``). Some builds
        ship two wrap keys; store the primary one here, and put the
        alternate in :attr:`wrap_key_alt` if needed.
    wrap_key_alt:
        Optional secondary wrap key. Unused in the default flow; kept
        as a slot so we can try it when a capture refuses to validate.
    static_iv:
        The constant 16-byte IV used for steps 2 and 3 (inner AES
        rounds). In the 1.48 client this is derived at init time from
        the hash chain and stays fixed for the session.
    slot_k1:
        Index into ``hash_array`` for the first inner AES round.
    slot_k2:
        Index into ``hash_array`` for the second inner AES round.
    """

    hash_array: List[bytes]
    wrap_key: bytes
    static_iv: bytes
    slot_k1: int = 0
    slot_k2: int = 1
    wrap_key_alt: Optional[bytes] = None

    def __post_init__(self) -> None:
        if len(self.hash_array) < 2:
            raise ValueError(
                f"hash_array must contain at least 2 keys "
                f"(got {len(self.hash_array)})"
            )
        for i, key in enumerate(self.hash_array):
            if len(key) != KEY_SIZE:
                raise ValueError(
                    f"hash_array[{i}] is {len(key)} bytes, "
                    f"expected {KEY_SIZE} (AES-256)"
                )
        if len(self.wrap_key) != KEY_SIZE:
            raise ValueError(
                f"wrap_key is {len(self.wrap_key)} bytes, "
                f"expected {KEY_SIZE}"
            )
        if self.wrap_key_alt is not None and len(self.wrap_key_alt) != KEY_SIZE:
            raise ValueError(
                f"wrap_key_alt is {len(self.wrap_key_alt)} bytes, "
                f"expected {KEY_SIZE}"
            )
        if len(self.static_iv) != BLOCK_SIZE:
            raise ValueError(
                f"static_iv is {len(self.static_iv)} bytes, "
                f"expected {BLOCK_SIZE}"
            )
        if not 0 <= self.slot_k1 < len(self.hash_array):
            raise ValueError(
                f"slot_k1={self.slot_k1} out of range "
                f"[0, {len(self.hash_array)})"
            )
        if not 0 <= self.slot_k2 < len(self.hash_array):
            raise ValueError(
                f"slot_k2={self.slot_k2} out of range "
                f"[0, {len(self.hash_array)})"
            )

    @classmethod
    def from_dict(cls, data: dict) -> "ShieldKeys":
        """Build a :class:`ShieldKeys` from a dict with hex string fields.

        Expected schema (see ``dofus_bot/data/shield_keys.example.json``):

        .. code-block:: json

            {
              "hash_array": ["<64 hex chars>", ... 9 entries ...],
              "wrap_key":   "<64 hex chars>",
              "wrap_key_alt": "<64 hex chars or null>",
              "static_iv":  "<32 hex chars>",
              "slot_k1": 0,
              "slot_k2": 1
            }
        """
        try:
            hash_array = [bytes.fromhex(h) for h in data["hash_array"]]
            wrap_key = bytes.fromhex(data["wrap_key"])
            static_iv = bytes.fromhex(data["static_iv"])
            slot_k1 = int(data.get("slot_k1", 0))
            slot_k2 = int(data.get("slot_k2", 1))
            wrap_key_alt_hex = data.get("wrap_key_alt")
            wrap_key_alt = (
                bytes.fromhex(wrap_key_alt_hex) if wrap_key_alt_hex else None
            )
        except (KeyError, ValueError) as exc:
            raise ShieldSignerError(f"Invalid shield_keys data: {exc}") from exc
        return cls(
            hash_array=hash_array,
            wrap_key=wrap_key,
            static_iv=static_iv,
            slot_k1=slot_k1,
            slot_k2=slot_k2,
            wrap_key_alt=wrap_key_alt,
        )

    @classmethod
    def from_json(cls, path: Path) -> "ShieldKeys":
        """Load keys from a JSON file on disk."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


@dataclass
class SignerConfig:
    """Runtime knobs for the signer.

    Attributes
    ----------
    counter:
        Current packet counter. Incremented after every sign() call.
        The server is strict about ordering so this must stay in
        lockstep with the real client's internal counter — in MITM
        mode, the passthrough packets bump their own counter on the
        client side, so we must track those too.
    counter_width:
        Width of the zero-padded counter string. Default 5.
    """

    counter: int = 0
    counter_width: int = COUNTER_WIDTH


class ShieldSigner:
    """Sign outgoing Dofus Retro 1.48 packets the way the stock client does.

    Usage::

        keys = ShieldKeys.from_json(Path("shield_keys.json"))
        signer = ShieldSigner(keys)
        signed = signer.sign(b"GA300;161;234")
        proxy.send_to_server_raw(signed)

    Thread-safety
    -------------
    The counter mutation is protected by a lock so the signer can be
    called from both the Lua script thread and the asyncio relay task
    without races.
    """

    def __init__(
        self,
        keys: ShieldKeys,
        config: Optional[SignerConfig] = None,
    ) -> None:
        if not _HAS_CRYPTOGRAPHY:
            raise MissingCryptographyError()
        self.keys = keys
        self.config = config or SignerConfig()
        self._lock = Lock()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def sign(self, raw_packet: bytes, signature_only: bool = False) -> bytes:
        """Return the Shield-signed form of ``raw_packet``.

        By default returns the wire form ``raw + \\xf9 + b64(iv) +
        b64(ct)`` ready to be written to the socket (after the
        ``\\x00`` frame terminator is added by the connection layer).

        Set ``signature_only=True`` to return just the suffix
        ``\\xf9 + b64(iv) + b64(ct)``, which matches the return value
        of the stock client's ``applyPacketToSendPostProcessing`` and
        is what you want when replaying captured vectors from
        ``data/security_api_calls.json``.

        Increments the internal counter on success. On failure (e.g.
        upstream cryptography error) the counter is NOT incremented
        and the exception propagates.
        """
        iv_rand = os.urandom(BLOCK_SIZE)
        return self._sign_with_iv(raw_packet, iv_rand, signature_only)

    def sign_with_iv(
        self,
        raw_packet: bytes,
        iv_rand: bytes,
        signature_only: bool = False,
    ) -> bytes:
        """Deterministic variant of :meth:`sign` for tests/validation.

        Useful when replaying a captured signing vector: pass the same
        ``iv_rand`` as the original client and the output should match
        byte-for-byte (provided the keys are correct).
        """
        if len(iv_rand) != BLOCK_SIZE:
            raise ValueError(f"iv_rand must be {BLOCK_SIZE} bytes")
        return self._sign_with_iv(raw_packet, iv_rand, signature_only)

    def reset_counter(self, value: int = 0) -> None:
        """Reset the counter. Call on every new game-server connection."""
        with self._lock:
            self.config.counter = value

    @property
    def current_counter(self) -> int:
        return self.config.counter

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _sign_with_iv(
        self,
        raw_packet: bytes,
        iv_rand: bytes,
        signature_only: bool,
    ) -> bytes:
        with self._lock:
            counter = self.config.counter
            counter_str = format(counter, f"0{self.config.counter_width}d")

            # Step 1: SHA-256(raw_packet || counter_str)
            h = hashlib.sha256()
            h.update(raw_packet)
            h.update(counter_str.encode("ascii"))
            sha = h.digest()  # 32 bytes

            # Step 2: AES-256-CBC(hash, k1, static_iv)
            ct1 = self._aes_cbc_encrypt(
                sha,
                self.keys.hash_array[self.keys.slot_k1],
                self.keys.static_iv,
            )

            # Step 3: AES-256-CBC(ct1, k2, static_iv)
            ct2 = self._aes_cbc_encrypt(
                ct1,
                self.keys.hash_array[self.keys.slot_k2],
                self.keys.static_iv,
            )

            # Step 4: AES-256-CBC(ct2, wrap_key, iv_rand)
            ct3 = self._aes_cbc_encrypt(
                ct2,
                self.keys.wrap_key,
                iv_rand,
            )

            # Output assembly matches the format observed in real
            # captures (see module docstring): one marker, then b64(iv)
            # directly concatenated with b64(ct), no separator in
            # between and no trailing marker. The raw packet is
            # prepended by default so the output is ready to frame;
            # callers replaying the stock client's
            # applyPacketToSendPostProcessing return value can ask for
            # the suffix only via signature_only=True.
            iv_b64 = base64.b64encode(iv_rand)
            ct_b64 = base64.b64encode(ct3)
            suffix = SHIELD_MARKER + iv_b64 + ct_b64
            output = suffix if signature_only else raw_packet + suffix

            # Bump counter only after a successful assembly.
            self.config.counter = counter + 1
            return output

    @staticmethod
    def _aes_cbc_encrypt(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
        """AES-256-CBC encrypt with PKCS7 padding.

        Isolated in a static method so tests can monkeypatch it if a
        future build switches to a different cipher.
        """
        if len(key) != KEY_SIZE:
            raise ValueError(f"key must be {KEY_SIZE} bytes")
        if len(iv) != BLOCK_SIZE:
            raise ValueError(f"iv must be {BLOCK_SIZE} bytes")
        padder = padding.PKCS7(BLOCK_SIZE * 8).padder()
        padded = padder.update(plaintext) + padder.finalize()
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        return encryptor.update(padded) + encryptor.finalize()


def load_signer_from_env(
    env_var: str = "DOFUS_SHIELD_KEYS",
) -> Optional[ShieldSigner]:
    """Convenience: build a signer from a path in an env var.

    Returns ``None`` if the env var is unset or the file is missing —
    the caller decides whether that's fatal or "inject path disabled".
    """
    path = os.environ.get(env_var)
    if not path:
        return None
    p = Path(path).expanduser()
    if not p.exists():
        logger.warning("Shield keys file %s (from %s) does not exist", p, env_var)
        return None
    try:
        keys = ShieldKeys.from_json(p)
    except ShieldSignerError as exc:
        logger.error("Failed to load Shield keys from %s: %s", p, exc)
        return None
    return ShieldSigner(keys)
