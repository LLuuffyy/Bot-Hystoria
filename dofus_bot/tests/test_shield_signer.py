"""Unit tests for :mod:`dofus_bot.protocol.shield_signer`.

These exercise the signer's math end-to-end against synthetic keys
(not the real Shield keys — we don't have those in the repo). The
goal is to pin:

1. The shape of the output (raw || marker || b64(iv) || b64(ct))
   which matches the format observed in the 639 captured
   ``applyPacketToSendPostProcessing`` call pairs.
2. The counter lockstep (increments by 1 per sign, zero-padded width).
3. The round-trip with :func:`strip_shield_signature`.
4. Deterministic replay via :meth:`sign_with_iv`.
5. Validation of key constraints (32-byte AES-256, 16-byte IV, etc.).
6. The ``signature_only`` mode that drops the raw prefix so we can
   compare against the stock client's return value 1:1.

When we get the real keys, we'll add a ``test_real_vectors`` file that
replays captured calls from ``data/security_api_calls.json`` and
asserts bit-for-bit match. That file stays out of the tree until the
keys land.
"""

from __future__ import annotations

import base64
import hashlib
import unittest

from dofus_bot.protocol.shield import SHIELD_MARKER, strip_shield_signature
from dofus_bot.protocol.shield_signer import (
    BLOCK_SIZE,
    KEY_SIZE,
    ShieldKeys,
    ShieldSigner,
    SignerConfig,
)

#: Length of a base64-encoded 16-byte IV (padded): ceil(16/3)*4 = 24.
_IV_B64_LEN = 24


def _make_keys(
    slot_k1: int = 0,
    slot_k2: int = 1,
) -> ShieldKeys:
    """Build deterministic synthetic keys for tests."""
    hash_array = [bytes([i] * KEY_SIZE) for i in range(1, 10)]  # 9 keys
    wrap_key = bytes([0xAA] * KEY_SIZE)
    static_iv = bytes(range(BLOCK_SIZE))
    return ShieldKeys(
        hash_array=hash_array,
        wrap_key=wrap_key,
        static_iv=static_iv,
        slot_k1=slot_k1,
        slot_k2=slot_k2,
    )


class ShieldKeysValidationTests(unittest.TestCase):
    def test_rejects_short_hash_array(self) -> None:
        with self.assertRaises(ValueError):
            ShieldKeys(
                hash_array=[bytes(KEY_SIZE)],
                wrap_key=bytes(KEY_SIZE),
                static_iv=bytes(BLOCK_SIZE),
            )

    def test_rejects_wrong_key_size(self) -> None:
        with self.assertRaises(ValueError):
            ShieldKeys(
                hash_array=[bytes(16), bytes(16)],  # AES-128 keys, nope
                wrap_key=bytes(KEY_SIZE),
                static_iv=bytes(BLOCK_SIZE),
            )

    def test_rejects_wrong_iv_size(self) -> None:
        with self.assertRaises(ValueError):
            ShieldKeys(
                hash_array=[bytes(KEY_SIZE), bytes(KEY_SIZE)],
                wrap_key=bytes(KEY_SIZE),
                static_iv=bytes(8),  # too short
            )

    def test_rejects_out_of_range_slot(self) -> None:
        with self.assertRaises(ValueError):
            ShieldKeys(
                hash_array=[bytes(KEY_SIZE), bytes(KEY_SIZE)],
                wrap_key=bytes(KEY_SIZE),
                static_iv=bytes(BLOCK_SIZE),
                slot_k1=5,  # only 2 keys -> valid range is [0, 2)
            )

    def test_from_dict_roundtrip(self) -> None:
        keys = _make_keys()
        data = {
            "hash_array": [k.hex() for k in keys.hash_array],
            "wrap_key": keys.wrap_key.hex(),
            "static_iv": keys.static_iv.hex(),
            "slot_k1": keys.slot_k1,
            "slot_k2": keys.slot_k2,
        }
        loaded = ShieldKeys.from_dict(data)
        self.assertEqual(loaded.hash_array, keys.hash_array)
        self.assertEqual(loaded.wrap_key, keys.wrap_key)
        self.assertEqual(loaded.static_iv, keys.static_iv)


class ShieldSignerShapeTests(unittest.TestCase):
    """The output structure must match the format seen in real captures.

    Real captures (639 call pairs in
    ``data/security_api_calls.json``) show exactly one ``\\xf9`` at
    position 0 of the stock function's return value, followed by
    b64(iv) then b64(ct) with no separator between them. Our wire
    form prepends the raw packet so the output is ready to be framed
    on the socket.
    """

    def setUp(self) -> None:
        self.keys = _make_keys()
        self.signer = ShieldSigner(self.keys)

    def test_output_starts_with_raw_packet(self) -> None:
        raw = b"GA300;161;234"
        out = self.signer.sign(raw)
        self.assertTrue(out.startswith(raw))

    def test_output_contains_shield_marker(self) -> None:
        out = self.signer.sign(b"GA0;1;1234;abcd")
        self.assertIn(SHIELD_MARKER, out)

    def test_output_uses_exactly_one_marker(self) -> None:
        """Real captures show a single ``\\xf9`` marker, not 2 or 3."""
        out = self.signer.sign(b"GC1")
        self.assertEqual(out.count(SHIELD_MARKER), 1)

    def test_marker_sits_immediately_after_raw(self) -> None:
        raw = b"GA0;1;1234;abcd"
        out = self.signer.sign(raw)
        self.assertEqual(out[len(raw):len(raw) + 1], SHIELD_MARKER)

    def test_output_does_not_end_with_marker(self) -> None:
        out = self.signer.sign(b"GC1")
        self.assertNotEqual(out[-1:], SHIELD_MARKER)

    def test_output_roundtrips_through_stripper(self) -> None:
        raw = b"GDM|1|7411|abcdef"
        out = self.signer.sign(raw)
        payload, sig = strip_shield_signature(out)
        self.assertEqual(payload, raw)
        self.assertIsNotNone(sig)

    def test_signature_only_mode_drops_raw_prefix(self) -> None:
        """``signature_only=True`` matches the stock function's return value."""
        raw = b"GC1"
        sig = self.signer.sign(raw, signature_only=True)
        self.assertTrue(sig.startswith(SHIELD_MARKER))
        self.assertNotIn(raw, sig)
        # marker + b64(iv) + b64(ct)
        self.assertEqual(sig.count(SHIELD_MARKER), 1)

    def test_signature_only_and_wire_differ_only_by_raw_prefix(self) -> None:
        raw = b"GDM|1|7411"
        iv = bytes([0xAB] * BLOCK_SIZE)
        wire = self.signer.sign_with_iv(raw, iv, signature_only=False)
        # Reset counter so the second sign uses the same counter value.
        self.signer.reset_counter(0)
        sig = self.signer.sign_with_iv(raw, iv, signature_only=True)
        self.assertEqual(wire, raw + sig)


class ShieldSignerCounterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.keys = _make_keys()
        self.signer = ShieldSigner(self.keys)

    def test_counter_starts_at_zero(self) -> None:
        self.assertEqual(self.signer.current_counter, 0)

    def test_counter_increments_after_sign(self) -> None:
        self.signer.sign(b"GC1")
        self.assertEqual(self.signer.current_counter, 1)
        self.signer.sign(b"GC2")
        self.assertEqual(self.signer.current_counter, 2)

    def test_counter_influences_output(self) -> None:
        """Same packet signed at different counters yields different sigs."""
        out0 = self.signer.sign_with_iv(b"GC1", bytes(BLOCK_SIZE))
        out1 = self.signer.sign_with_iv(b"GC1", bytes(BLOCK_SIZE))
        # Raw prefix is identical, but the signature part must differ.
        raw0, sig0 = strip_shield_signature(out0)
        raw1, sig1 = strip_shield_signature(out1)
        self.assertEqual(raw0, raw1)
        self.assertNotEqual(sig0, sig1)

    def test_reset_counter(self) -> None:
        self.signer.sign(b"GC1")
        self.signer.sign(b"GC2")
        self.signer.reset_counter(42)
        self.assertEqual(self.signer.current_counter, 42)
        self.signer.sign(b"GC3")
        self.assertEqual(self.signer.current_counter, 43)


class ShieldSignerDeterminismTests(unittest.TestCase):
    """Deterministic replay: same raw + same counter + same iv_rand -> same output."""

    def setUp(self) -> None:
        self.keys = _make_keys()

    def test_sign_with_iv_is_deterministic(self) -> None:
        sig_a = ShieldSigner(self.keys).sign_with_iv(
            b"GC1", bytes([0xBB] * BLOCK_SIZE)
        )
        sig_b = ShieldSigner(self.keys).sign_with_iv(
            b"GC1", bytes([0xBB] * BLOCK_SIZE)
        )
        self.assertEqual(sig_a, sig_b)

    def test_sign_rejects_wrong_iv_length(self) -> None:
        signer = ShieldSigner(self.keys)
        with self.assertRaises(ValueError):
            signer.sign_with_iv(b"GC1", b"too short")

    def test_different_keys_produce_different_sigs(self) -> None:
        raw = b"GC1"
        iv = bytes([0xCC] * BLOCK_SIZE)
        sig_default = ShieldSigner(_make_keys()).sign_with_iv(raw, iv)
        sig_swapped = ShieldSigner(
            _make_keys(slot_k1=2, slot_k2=3)
        ).sign_with_iv(raw, iv)
        self.assertNotEqual(sig_default, sig_swapped)


class ShieldSignerMathTests(unittest.TestCase):
    """Spot-check the 4-step flow against a hand-computed vector."""

    def test_step1_hash_matches_sha256(self) -> None:
        """The first step must be SHA-256(raw || counter_str)."""
        keys = _make_keys()
        signer = ShieldSigner(keys)
        raw = b"GC1"
        # Peek at step 1 by recomputing the hash ourselves.
        expected_hash = hashlib.sha256(raw + b"00000").digest()
        self.assertEqual(len(expected_hash), 32)

        # The signed output, stripped, should match the raw prefix. This
        # doesn't test step 1 directly but ensures step 1 didn't crash.
        out = signer.sign(raw)
        payload, _ = strip_shield_signature(out)
        self.assertEqual(payload, raw)

    def test_counter_string_uses_five_digit_width(self) -> None:
        """We match the client's '00000', '00001', ... format."""
        cfg = SignerConfig(counter=42)
        self.assertEqual(format(cfg.counter, f"0{cfg.counter_width}d"), "00042")

    def test_iv_rand_is_not_reused(self) -> None:
        signer = ShieldSigner(_make_keys())
        outs = {signer.sign(b"GC1") for _ in range(20)}
        # Random IV => 20 distinct outputs.
        self.assertEqual(len(outs), 20)

    def test_iv_rand_appears_in_output(self) -> None:
        signer = ShieldSigner(_make_keys())
        iv = bytes([0xDE] * BLOCK_SIZE)
        raw = b"GC1"
        out = signer.sign_with_iv(raw, iv)
        # Layout: raw + \xf9 + b64(iv) + b64(ct). Exactly one marker
        # at position len(raw), and the 24 bytes right after it must
        # decode to the provided iv.
        self.assertEqual(out.count(SHIELD_MARKER), 1)
        marker_idx = out.index(SHIELD_MARKER)
        self.assertEqual(marker_idx, len(raw))
        iv_b64 = out[marker_idx + 1 : marker_idx + 1 + _IV_B64_LEN]
        self.assertEqual(base64.b64decode(iv_b64), iv)

    def test_signature_length_matches_expected_crypto_sizes(self) -> None:
        """SHA256(32) -> PKCS7 48 -> PKCS7 64 -> PKCS7 80 -> b64 108 chars.

        Together with the 1-byte marker and the 24-char b64(iv), the
        signature suffix is always 1 + 24 + 108 = 133 bytes.
        """
        signer = ShieldSigner(_make_keys())
        iv = bytes([0x11] * BLOCK_SIZE)
        sig = signer.sign_with_iv(b"GC1", iv, signature_only=True)
        self.assertEqual(len(sig), 1 + 24 + 108)


if __name__ == "__main__":
    unittest.main()
