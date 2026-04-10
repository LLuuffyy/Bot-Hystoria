"""Shield signature handling for Dofus Retro 1.48 / Hystoria V5.

The Dofus Retro 1.48 Electron client (which Hystoria V5 embeds to host
its Flash 1.29 game logic) ships an in-process anti-cheat module called
**Shield**. Shield is initialised in ``main.jsc`` and is responsible for
signing every outgoing game packet via a 4-step AES-256-CBC chain. The
key insight, documented in reverse-engineering notes, is that **Shield
does not encrypt the packet body** — it only *appends* a signature:

.. code-block:: text

    raw_packet + b"\\xf9" + base64(iv_rand) + base64(ct3) + b"\\xf9"

So on the wire, every signed game message that reaches the server (and
often the reverse) looks like::

    GDM|1|7411|AbCdEf...ù<base64_iv>ù

where ``ù`` is ``\\xf9`` rendered in latin-1. The raw Dofus 1.29 text
prefix (``GDM``, ``GA``, ``GTS``...) sits *before* the first ``\\xf9``
marker and is perfectly readable — we just need to crop the suffix
before handing the message to the protocol router.

For us, this means two very different problems:

1. **Reading**: strip the suffix, no cryptography required. This module.
2. **Injecting**: produce a valid signature. Hard — requires the AES
   keys extracted from ``main.jsc`` and a synchronised counter. Not
   handled here.

Notes / caveats:

- On some Hystoria V5 builds the server ACK / chat / small notification
  packets do **not** carry a signature at all. ``strip_shield_signature``
  must be a safe no-op when no ``\\xf9`` marker is found.
- If multiple ``\\xf9`` markers are present we split on the first one,
  returning everything before it as the payload. The tail (including the
  two markers and the base64 chunk) is returned as the raw signature
  bytes so diagnostic code can log or verify it.
- Packets encrypted via ``cryptBasicPacket`` / ``parseBasicCryptedPacket``
  (the login handshake, at least on stock 1.48) are NOT handled by this
  stripper — their body is not plaintext-prefixed. We can't read those
  without the AES keys. If we see such a packet, the returned payload
  will look like random bytes and the router will drop it.
"""

from __future__ import annotations

from typing import Optional, Tuple

#: Byte marker that delimits a Shield signature block. It is ``0xF9`` which
#: happens to render as ``ù`` in latin-1 (the wire encoding). Convenient
#: because it is outside the base64 alphabet used for the signature payload,
#: outside the Dofus 1.29 text protocol character set, and cannot collide
#: with the ``\\x00`` frame terminator or the ``|`` / ``;`` separators.
SHIELD_MARKER = b"\xf9"


def strip_shield_signature(fragment: bytes) -> Tuple[bytes, Optional[bytes]]:
    """Split a framed packet fragment into ``(payload, signature)``.

    ``fragment`` is a single message as produced by the ``\\x00`` framer
    (i.e. what sits between two null bytes on the wire). It may or may
    not carry a Shield signature at the end.

    Returns a ``(payload, signature)`` tuple:

    * ``payload`` is the shield-stripped bytes ready to be decoded as the
      usual Dofus 1.29 text protocol. When no signature is present it is
      simply the input fragment.
    * ``signature`` is the full trailing block (including both ``\\xf9``
      markers) or ``None`` if no signature was found.

    Examples
    --------
    >>> strip_shield_signature(b"GDM|1|7411")
    (b'GDM|1|7411', None)

    >>> payload, sig = strip_shield_signature(
    ...     b"GDM|1|7411\\xf9AAECAw==\\xf9BBB==\\xf9"
    ... )
    >>> payload
    b'GDM|1|7411'
    >>> sig.startswith(b"\\xf9") and sig.endswith(b"\\xf9")
    True
    """
    if not fragment:
        return fragment, None

    idx = fragment.find(SHIELD_MARKER)
    if idx == -1:
        return fragment, None

    payload = fragment[:idx]
    signature = fragment[idx:]
    return payload, signature


def has_shield_signature(fragment: bytes) -> bool:
    """Quick predicate: does this fragment look shield-signed?

    Used only for logging/metrics. The authoritative stripping is done
    by :func:`strip_shield_signature`.
    """
    return SHIELD_MARKER in fragment
