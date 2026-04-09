"""Password hashing for Dofus 1.29 Retro authentication.

The server sends a random key in the ``HC`` (Hello Connect) message. The
client must encrypt its password against this key and send it back.

The canonical Dofus 1.29 algorithm, as implemented in:

    https://github.com/kralamoure/retroproto

works as follows:

1. MD5 the password and uppercase the hex digest (32 chars).
2. For each pair of characters ``(p, k)`` -- where ``p`` is a character of
   the MD5 hash and ``k`` is the matching character of the server key
   (also taken pairwise) -- compute two ASCII indices ``a`` and ``b``,
   XOR them, and encode the two nibbles using the ``HASH_CHARS`` alphabet.
3. Prefix the result with ``#1`` to signal the hash version.

Some private servers use simpler variants (plain XOR, double-MD5, etc.).
This module exposes the canonical implementation and a ``mode`` parameter
so alternatives can be added if Hystoria rejects the default login.
"""

from __future__ import annotations

import hashlib

from .constants import HASH_CHARS


def hash_password(password: str, key: str, mode: str = "md5_xor") -> str:
    """Encrypt ``password`` for the Dofus 1.29 auth flow.

    Args:
        password: plaintext account password
        key: the hash key received in the HC message (without the "HC" prefix)
        mode: encryption algorithm; "md5_xor" is the canonical Dofus 1.29

    Returns:
        The hashed password prefixed with the algorithm marker (``#1``),
        ready to be sent inside the login message.
    """
    if mode == "md5_xor":
        return _hash_md5_xor(password, key)
    if mode == "plain_xor":
        return _hash_plain_xor(password, key)
    raise ValueError(f"Unknown password hash mode: {mode}")


def _hash_md5_xor(password: str, key: str) -> str:
    """Canonical Dofus 1.29 password hash (MD5 + XOR against server key)."""
    pwd_hash = hashlib.md5(password.encode("utf-8")).hexdigest().upper()
    out: list[str] = []
    for i in range(0, min(len(pwd_hash), len(key) * 2, 32), 2):
        # Two MD5 chars per loop, one key char.
        hi = ord(pwd_hash[i])
        lo = ord(pwd_hash[i + 1])
        k = ord(key[i // 2])
        a = (hi - 32) ^ k
        b = (lo - 32) ^ k
        out.append(HASH_CHARS[a % len(HASH_CHARS)])
        out.append(HASH_CHARS[b % len(HASH_CHARS)])
    return "#1" + "".join(out)


def _hash_plain_xor(password: str, key: str) -> str:
    """Simple XOR fallback. Useful if the server doesn't use MD5."""
    out: list[str] = []
    for i, c in enumerate(password):
        xor = ord(c) ^ ord(key[i % len(key)])
        out.append(HASH_CHARS[(xor >> 4) % len(HASH_CHARS)])
        out.append(HASH_CHARS[xor % len(HASH_CHARS)])
    return "#1" + "".join(out)
