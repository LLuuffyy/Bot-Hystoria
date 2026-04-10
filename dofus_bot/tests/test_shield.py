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

    def test_signed_fragment_with_multiple_markers_splits_on_first(self) -> None:
        # Real captures show a single \xf9 marker separating the raw
        # packet from b64(iv)+b64(ct). But early notes mentioned
        # variants with internal markers, so we keep the stripper
        # tolerant: regardless of how many markers show up in a
        # fragment, splitting on the FIRST one yields the right
        # payload.
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

    def test_signed_fragment_real_format(self) -> None:
        # The exact format we see in captures: one marker, then
        # base64(iv) (24 chars for a 16-byte IV) then base64(ct) (108
        # chars for the 80-byte AES output), no trailing marker.
        iv_b64 = b"oxiyNNxGkr2/JWH16aEI2A=="  # 24 chars, real sample
        ct_b64 = b"A" * 108                    # 108 chars, placeholder
        raw = b"GC1" + SHIELD_MARKER + iv_b64 + ct_b64
        payload, sig = strip_shield_signature(raw)
        self.assertEqual(payload, b"GC1")
        assert sig is not None
        # The suffix is exactly 1 + 24 + 108 = 133 bytes, single marker.
        self.assertEqual(len(sig), 1 + 24 + 108)
        self.assertEqual(sig.count(SHIELD_MARKER), 1)
        self.assertTrue(sig.startswith(SHIELD_MARKER))

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
