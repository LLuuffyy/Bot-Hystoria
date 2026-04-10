"""Integration tests for :mod:`dofus_bot.network.proxy`.

We exercise ``DofusProxy._relay`` directly with an in-memory
``StreamReader``/``StreamWriter`` pair so we can feed it a shield-signed
byte stream and assert that the callback sees the shield-stripped
text. This is the regression pin for the bug where the router was
receiving unreadable messages because the shield signature was never
cropped before parsing.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock

from dofus_bot.network.proxy import DofusProxy
from dofus_bot.protocol.shield import SHIELD_MARKER


class _NullWriter:
    """A minimal StreamWriter stand-in for _relay's forwarding side."""

    def __init__(self) -> None:
        self.written: list[bytes] = []
        self._closed = False

    def write(self, data: bytes) -> None:
        self.written.append(data)

    async def drain(self) -> None:
        return None

    def is_closing(self) -> bool:
        return self._closed


class ProxyShieldRelayTests(unittest.TestCase):
    def _run_relay(self, data: bytes) -> tuple[list[str], _NullWriter]:
        proxy = DofusProxy(
            listen_host="127.0.0.1",
            listen_port=0,
            upstream_host="127.0.0.1",
            upstream_port=0,
        )
        writer = _NullWriter()
        callback = AsyncMock()

        async def run() -> None:
            # StreamReader needs an event loop to exist, so build it
            # inside the coroutine.
            reader = asyncio.StreamReader()
            reader.feed_data(data)
            reader.feed_eof()
            await proxy._relay(
                src_reader=reader,
                dst_writer=writer,  # type: ignore[arg-type]
                callback=callback,
                label="C>>S",
            )

        asyncio.run(run())
        messages = [call.args[0] for call in callback.await_args_list]
        return messages, writer

    def test_unsigned_stream_is_passed_through(self) -> None:
        # Classic Dofus 1.29 framing: null-terminated plain text.
        stream = b"GDM|1|7411|abcd\x00GM|+42;0;0;5001;Bob\x00"
        messages, writer = self._run_relay(stream)

        self.assertEqual(
            messages,
            ["GDM|1|7411|abcd", "GM|+42;0;0;5001;Bob"],
        )
        # Forwarding must be byte-for-byte identical.
        self.assertEqual(b"".join(writer.written), stream)

    def test_shield_signed_stream_is_stripped_for_callback(self) -> None:
        # Build two shield-signed messages. The byte stream we forward
        # must keep the signature (so the other side still verifies it)
        # but the callback must only see the plaintext prefix.
        msg1 = (
            b"GDM|1|7411|abcd"
            + SHIELD_MARKER
            + b"UklGRjIBAAA="
            + SHIELD_MARKER
            + b"AAECAwQFBgcICQoL"
            + SHIELD_MARKER
        )
        msg2 = (
            b"GA0;1;1234;efgh"
            + SHIELD_MARKER
            + b"sigbody=="
            + SHIELD_MARKER
        )
        stream = msg1 + b"\x00" + msg2 + b"\x00"
        messages, writer = self._run_relay(stream)

        self.assertEqual(messages, ["GDM|1|7411|abcd", "GA0;1;1234;efgh"])
        # Forwarding keeps the signatures intact.
        self.assertEqual(b"".join(writer.written), stream)

    def test_chunked_shield_stream_reassembles(self) -> None:
        # Split a single signed message across the arbitrary TCP read
        # boundary to verify the framing buffer survives chunked reads.
        msg = (
            b"GDM|1|7411|abcd"
            + SHIELD_MARKER
            + b"sig=="
            + SHIELD_MARKER
            + b"\x00"
        )

        async def run() -> list[str]:
            proxy = DofusProxy(
                listen_host="127.0.0.1", listen_port=0,
                upstream_host="127.0.0.1", upstream_port=0,
            )
            reader = asyncio.StreamReader()
            writer = _NullWriter()
            callback = AsyncMock()

            # Feed the data in three chunks with small pauses to
            # exercise the streaming path.
            async def feeder() -> None:
                reader.feed_data(msg[:5])
                await asyncio.sleep(0)
                reader.feed_data(msg[5:15])
                await asyncio.sleep(0)
                reader.feed_data(msg[15:])
                reader.feed_eof()

            feed_task = asyncio.create_task(feeder())
            await proxy._relay(
                src_reader=reader,
                dst_writer=writer,  # type: ignore[arg-type]
                callback=callback,
                label="S>>C",
            )
            await feed_task
            return [call.args[0] for call in callback.await_args_list]

        messages = asyncio.run(run())
        self.assertEqual(messages, ["GDM|1|7411|abcd"])


if __name__ == "__main__":
    unittest.main()
