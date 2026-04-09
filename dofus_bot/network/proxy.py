"""MITM proxy for Dofus 1.29 Retro.

Sits between the real Dofus client and the Hystoria game server. Every
packet in both directions is parsed, logged and optionally handed to the
MessageRouter so bot logic can react. The scripting layer can also
inject packets into either direction via :meth:`send_to_server` and
:meth:`send_to_client`.

Architecture::

    Dofus client  ──TCP──►  DofusProxy  ──TCP──►  Hystoria server
                    ◄───                    ◄───

How it's wired up:

    proxy = DofusProxy(listen_host="127.0.0.1", listen_port=5555,
                       upstream_host="play-hystoria.net",
                       upstream_port=5555)
    proxy.on_client_message(handler)   # called for every client-to-server
    proxy.on_server_message(handler)   # called for every server-to-client
    await proxy.serve_forever()

The proxy accepts a single client connection at a time (Dofus connects
to the auth server, then to the game server; the proxy re-uses the same
listening socket). Multi-session support can be added later if needed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from .connection import MESSAGE_TERMINATOR, WIRE_ENCODING, _split_newlines

logger = logging.getLogger(__name__)

MessageCallback = Callable[[str], Awaitable[None]]


class DofusProxy:
    """Transparent TCP MITM proxy for the Dofus 1.29 text protocol."""

    def __init__(
        self,
        listen_host: str,
        listen_port: int,
        upstream_host: str,
        upstream_port: int,
    ) -> None:
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port

        self._on_client_message: Optional[MessageCallback] = None
        self._on_server_message: Optional[MessageCallback] = None

        self._client_writer: Optional[asyncio.StreamWriter] = None
        self._server_writer: Optional[asyncio.StreamWriter] = None
        self._server: Optional[asyncio.base_events.Server] = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def on_client_message(self, callback: MessageCallback) -> None:
        """Register a coroutine called for every client->server message."""
        self._on_client_message = callback

    def on_server_message(self, callback: MessageCallback) -> None:
        """Register a coroutine called for every server->client message."""
        self._on_server_message = callback

    async def send_to_server(self, message: str) -> None:
        """Inject a packet as if it came from the client.

        Used by the scripting layer to trigger actions (move, cast, ...).
        """
        if self._server_writer is None or self._server_writer.is_closing():
            logger.warning("Cannot inject to server: not connected")
            return
        payload = message.encode(WIRE_ENCODING) + MESSAGE_TERMINATOR
        logger.info("INJECT >> server: %s", message)
        self._server_writer.write(payload)
        try:
            await self._server_writer.drain()
        except ConnectionError as exc:
            logger.warning("Server write failed: %s", exc)

    async def send_to_client(self, message: str) -> None:
        """Inject a packet as if it came from the server.

        Less commonly used but occasionally handy (e.g. displaying a
        fake chat message to the user).
        """
        if self._client_writer is None or self._client_writer.is_closing():
            logger.warning("Cannot inject to client: not connected")
            return
        payload = message.encode(WIRE_ENCODING) + MESSAGE_TERMINATOR
        logger.info("INJECT >> client: %s", message)
        self._client_writer.write(payload)
        try:
            await self._client_writer.drain()
        except ConnectionError as exc:
            logger.warning("Client write failed: %s", exc)

    async def serve_forever(self) -> None:
        """Start accepting connections. Blocks until cancelled."""
        self._server = await asyncio.start_server(
            self._handle_client, self.listen_host, self.listen_port
        )
        sockets = self._server.sockets or []
        addrs = ", ".join(str(s.getsockname()) for s in sockets)
        logger.info("Proxy listening on %s (forwarding to %s:%d)",
                    addrs, self.upstream_host, self.upstream_port)
        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    # ------------------------------------------------------------------ #
    # Internal plumbing
    # ------------------------------------------------------------------ #

    async def _handle_client(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        client_addr = client_writer.get_extra_info("peername")
        logger.info("Client connected from %s", client_addr)

        # Open an upstream connection per client session.
        try:
            server_reader, server_writer = await asyncio.open_connection(
                self.upstream_host, self.upstream_port
            )
        except OSError as exc:
            logger.error("Could not reach upstream %s:%d: %s",
                         self.upstream_host, self.upstream_port, exc)
            client_writer.close()
            return

        self._client_writer = client_writer
        self._server_writer = server_writer
        logger.info("Upstream connected to %s:%d",
                    self.upstream_host, self.upstream_port)

        # Two relay tasks, one in each direction. Whichever finishes first
        # tears the whole session down.
        c2s = asyncio.create_task(
            self._relay(
                src_reader=client_reader,
                dst_writer=server_writer,
                callback=self._on_client_message,
                label="C>>S",
            )
        )
        s2c = asyncio.create_task(
            self._relay(
                src_reader=server_reader,
                dst_writer=client_writer,
                callback=self._on_server_message,
                label="S>>C",
            )
        )

        done, pending = await asyncio.wait(
            {c2s, s2c}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

        for writer in (client_writer, server_writer):
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

        self._client_writer = None
        self._server_writer = None
        logger.info("Session closed for %s", client_addr)

    async def _relay(
        self,
        src_reader: asyncio.StreamReader,
        dst_writer: asyncio.StreamWriter,
        callback: Optional[MessageCallback],
        label: str,
    ) -> None:
        """Forward one direction of the TCP stream, framing on \\x00.

        Each framed message is:
        1. Logged at DEBUG.
        2. Passed to the callback (which may update state or ignore it).
        3. Forwarded to the destination AS-IS.

        The forwarded bytes are the original bytes, not a re-serialised
        version of the parsed message: this avoids any accidental
        corruption if our parser disagrees with the server about a
        field's encoding.
        """
        buffer = bytearray()
        try:
            while True:
                chunk = await src_reader.read(4096)
                if not chunk:
                    logger.debug("[%s] peer closed", label)
                    return

                # Forward raw bytes first so latency is minimal.
                dst_writer.write(chunk)
                try:
                    await dst_writer.drain()
                except ConnectionError as exc:
                    logger.debug("[%s] destination closed: %s", label, exc)
                    return

                # Then parse the stream for our own visibility.
                buffer.extend(chunk)
                while True:
                    idx = buffer.find(MESSAGE_TERMINATOR)
                    if idx == -1:
                        break
                    raw = bytes(buffer[:idx])
                    del buffer[: idx + 1]
                    for frag in _split_newlines(raw):
                        try:
                            decoded = frag.decode(WIRE_ENCODING, errors="replace")
                        except Exception:
                            continue
                        logger.debug("[%s] %s", label, decoded)
                        if callback is not None:
                            try:
                                await callback(decoded)
                            except Exception:
                                logger.exception(
                                    "[%s] callback failed on: %s",
                                    label, decoded[:80],
                                )
        except (asyncio.CancelledError, ConnectionResetError):
            raise
        except Exception:
            logger.exception("[%s] relay crashed", label)
