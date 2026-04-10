"""Unit tests for :mod:`dofus_bot.protocol.shield`.

These pin the contract of ``strip_shield_signature``: it must be a
safe no-op when no signature is present, and it must correctly split
on the first ``\\xf9`` marker when a shield suffix is appended.
"""

from __future__ import annotations

import unittest

from dofus_bot.protocol.shield import (
    SHIELD_MARKER,
    has_shield_signature,
    strip_shield_signature,
)


class StripShieldSignatureTests(unittest.TestCase):
    def test_empty_fragment_is_identity(self) -> None:
        payload, sig = strip_shield_signature(b"")
        self.assertEqual(payload, b"")
        self.assertIsNone(sig)

    def test_unsigned_fragment_is_identity(self) -> None:
        payload, sig = strip_shield_signature(b"GDM|1|7411")
        self.assertEqual(payload, b"GDM|1|7411")
        self.assertIsNone(sig)

    def test_signed_fragment_strips_suffix(self) -> None:
        raw = b"GDM|1|7411" + SHIELD_MARKER + b"AAECAw==" + SHIELD_MARKER
        payload, sig = strip_shield_signature(raw)
        self.assertEqual(payload, b"GDM|1|7411")
        self.assertIsNotNone(sig)
        assert sig is not None  # for mypy
        # The signature starts and ends with the marker.
        self.assertTrue(sig.startswith(SHIELD_MARKER))
        self.assertTrue(sig.endswith(SHIELD_MARKER))

    def test_signed_fragment_with_nested_base64_markers(self) -> None:
        # Real Shield signatures carry base64(iv)\xf9 base64(ct)\xf9. The
        # stripper must split on the FIRST marker so the whole suffix is
        # peeled off in one shot.
        raw = (
            b"GA0;1;1234;abcdef"
            + SHIELD_MARKER
            + b"UklGRjIBAAA="
            + SHIELD_MARKER
            + b"AAECAwQFBgcICQoL"
            + SHIELD_MARKER
        )
        payload, sig = strip_shield_signature(raw)
        self.assertEqual(payload, b"GA0;1;1234;abcdef")
        assert sig is not None
        # Everything from the first \xf9 to the end belongs to the sig.
        self.assertEqual(
            sig,
            SHIELD_MARKER
            + b"UklGRjIBAAA="
            + SHIELD_MARKER
            + b"AAECAwQFBgcICQoL"
            + SHIELD_MARKER,
        )

    def test_marker_at_start_gives_empty_payload(self) -> None:
        # Degenerate case we want to handle cleanly: the whole fragment
        # looks like a signature. We still return a tuple rather than
        # crashing.
        raw = SHIELD_MARKER + b"xyz" + SHIELD_MARKER
        payload, sig = strip_shield_signature(raw)
        self.assertEqual(payload, b"")
        self.assertIsNotNone(sig)

    def test_latin1_content_before_marker_is_preserved(self) -> None:
        # Dofus 1.29 is latin-1 on the wire and legitimately uses
        # accented chars (e.g. character names). Make sure we don't
        # accidentally chop them: we split on bytes not on decoded text.
        raw = "GM|4;Éléonore".encode("latin-1") + SHIELD_MARKER + b"sig="
        payload, sig = strip_shield_signature(raw)
        self.assertEqual(payload.decode("latin-1"), "GM|4;Éléonore")
        self.assertIsNotNone(sig)


class HasShieldSignatureTests(unittest.TestCase):
    def test_true_when_marker_present(self) -> None:
        self.assertTrue(has_shield_signature(b"GDM|1|7411" + SHIELD_MARKER + b"x"))

    def test_false_when_marker_absent(self) -> None:
        self.assertFalse(has_shield_signature(b"GDM|1|7411"))

    def test_false_on_empty(self) -> None:
        self.assertFalse(has_shield_signature(b""))


if __name__ == "__main__":
    unittest.main()
