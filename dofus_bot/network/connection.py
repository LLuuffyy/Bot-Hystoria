"""Async TCP connection for the Dofus 1.29 protocol.

Messages on the wire are text-based, encoded in latin-1 (ISO-8859-1), and
delimited by a null byte (``\\x00``). Some servers additionally use ``\\n``
as an internal separator within a single TCP segment.

This module handles:
- opening / closing the TCP connection (asyncio),
- framing (split incoming bytes on ``\\x00``),
- sending messages with the expected trailing terminator,
- yielding decoded messages via an async iterator.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Optional

logger = logging.getLogger(__name__)

# Dofus 1.29 uses latin-1 on the wire (French accents in character names, etc.)
WIRE_ENCODING = "latin-1"
MESSAGE_TERMINATOR = b"\x00"


class DofusConnection:
    """A single async TCP connection speaking the Dofus 1.29 text protocol."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._buffer = bytearray()

    @property
    def is_connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        """Open the TCP connection."""
        logger.info("Connecting to %s:%d", self.host, self.port)
        self._reader, self._writer = await asyncio.open_connection(
            self.host, self.port
        )
        logger.info("Connected to %s:%d", self.host, self.port)

    async def disconnect(self) -> None:
        """Close the connection cleanly."""
        if self._writer is None:
            return
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except Exception as exc:  # pragma: no cover - best-effort close
            logger.debug("Error while closing writer: %s", exc)
        finally:
            self._reader = None
            self._writer = None
            self._buffer.clear()
            logger.info("Disconnected from %s:%d", self.host, self.port)

    async def reconnect(self, host: Optional[str] = None, port: Optional[int] = None) -> None:
        """Close and re-open the connection, optionally to a new endpoint.

        Used after the auth server hands off to the game server.
        """
        await self.disconnect()
        if host is not None:
            self.host = host
        if port is not None:
            self.port = port
        await self.connect()

    async def send(self, message: str) -> None:
        """Send a single protocol message.

        The message is encoded in latin-1 and terminated with ``\\x00``.
        ``message`` should NOT contain the trailing null byte.
        """
        if self._writer is None:
            raise ConnectionError("Not connected")
        payload = message.encode(WIRE_ENCODING) + MESSAGE_TERMINATOR
        logger.debug("SEND: %s", message)
        self._writer.write(payload)
        await self._writer.drain()

    async def listen(self) -> AsyncIterator[str]:
        """Yield messages as they arrive from the server.

        The socket is read in chunks; whenever ``\\x00`` is found the framed
        bytes are decoded and yielded. Partial messages are kept in a
        buffer until the terminator arrives.

        Raises:
            ConnectionError: when the peer closes the connection.
        """
        if self._reader is None:
            raise ConnectionError("Not connected")

        while True:
            try:
                chunk = await self._reader.read(4096)
            except (asyncio.IncompleteReadError, ConnectionResetError) as exc:
                logger.warning("Read error: %s", exc)
                raise ConnectionError(str(exc)) from exc

            if not chunk:
                logger.warning("Connection closed by peer")
                raise ConnectionError("Connection closed by peer")

            self._buffer.extend(chunk)

            # Frame on null byte. A single TCP read may contain multiple
            # messages, or a fragment of one, so we loop until no complete
            # message remains.
            while True:
                idx = self._buffer.find(MESSAGE_TERMINATOR)
                if idx == -1:
                    break
                raw = bytes(self._buffer[:idx])
                del self._buffer[: idx + 1]
                for msg in _split_newlines(raw):
                    decoded = msg.decode(WIRE_ENCODING, errors="replace")
                    logger.debug("RECV: %s", decoded)
                    yield decoded


def _split_newlines(raw: bytes) -> list[bytes]:
    """Some Dofus Retro servers stack multiple messages between null bytes
    separated by \\n. Split on \\n and drop empty fragments.
    """
    if b"\n" not in raw:
        return [raw] if raw else []
    return [part for part in raw.split(b"\n") if part]
