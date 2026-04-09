"""Authentication flow for Dofus 1.29 Retro.

Handles the connection lifecycle from the first server greeting up to
the bot entering the game world:

    1. Connect to the auth server (host/port from config)
    2. Receive HC<key>, store the hash key
    3. Send account version + login
    4. Send hashed password
    5. Receive account info / server list
    6. Select the configured server -> receive ticket + game server endpoint
    7. Disconnect from auth, reconnect to game server
    8. Send ticket, receive character list
    9. Select character, enter game

This module focuses on the AUTH SERVER portion. The game-server portion
lives in ``game_handler.py`` (not yet implemented). The skeleton below
intentionally leaves several steps as TODOs that depend on observing a
real Hystoria login with the sniffer first.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from ..config import DofusConfig
from ..network.connection import DofusConnection
from ..protocol.crypto import hash_password

logger = logging.getLogger(__name__)


class AuthHandler:
    """Drives the Dofus 1.29 login / server-select flow."""

    # Client version string. Hystoria may pin a specific value; override
    # from config when the actual accepted version is known.
    CLIENT_VERSION = "1.29.1"

    def __init__(self, connection: DofusConnection, config: DofusConfig) -> None:
        self.connection = connection
        self.config = config

        self._hash_key: Optional[str] = None
        self.authenticated = asyncio.Event()
        self.game_ticket: Optional[str] = None
        self.game_host: Optional[str] = None
        self.game_port: Optional[int] = None

    # ------------------------------------------------------------------ #
    # Message handlers (to be registered on the MessageRouter)
    # ------------------------------------------------------------------ #

    async def on_hello_connect(self, message: str) -> None:
        """HC<hash_key> - server greeting."""
        self._hash_key = message[2:]
        logger.info("Received HC, key length=%d", len(self._hash_key))
        await self._send_credentials()

    async def on_account_error(self, message: str) -> None:
        """Login was rejected by the server."""
        logger.error("Login rejected: %s", message)

    async def on_server_ticket(self, message: str) -> None:
        """AYK<ticket>|<host>|<port> - handoff to the game server.

        The exact field order varies by server implementation; on most
        1.29 servers the payload is ``ticket;host;port`` with either
        pipe or semicolon separators.
        """
        payload = message[3:]
        # Try common separators in priority order.
        parts: list[str]
        for sep in ("|", ";"):
            if sep in payload:
                parts = payload.split(sep)
                break
        else:
            parts = [payload]

        if len(parts) >= 3:
            self.game_ticket = parts[0]
            self.game_host = parts[1]
            try:
                self.game_port = int(parts[2])
            except ValueError:
                logger.warning("Could not parse game port from %r", parts[2])
        logger.info(
            "Received server ticket, game server at %s:%s",
            self.game_host,
            self.game_port,
        )
        self.authenticated.set()

    # ------------------------------------------------------------------ #
    # Active messages sent by the client
    # ------------------------------------------------------------------ #

    async def _send_credentials(self) -> None:
        """Send the account credentials after receiving HC.

        Dofus 1.29 expects the login line to contain the version, account
        name and hashed password, usually separated by ``\\n``. The exact
        format depends on the emulator; sniffing a real client login is
        the easiest way to confirm it for Hystoria.
        """
        if self._hash_key is None:
            raise RuntimeError("Cannot send credentials before HC")

        hashed = hash_password(self.config.password, self._hash_key)
        login_line = f"{self.config.username}\n{hashed}\n{self.CLIENT_VERSION}"
        logger.info("Sending credentials for account %r", self.config.username)
        await self.connection.send(login_line)

    async def select_server(self) -> None:
        """Ask the auth server to hand us off to the configured world."""
        logger.info("Selecting server id=%d", self.config.server_id)
        await self.connection.send(f"AX{self.config.server_id}")

    async def wait_authenticated(self, timeout: float = 30.0) -> None:
        """Block until the server ticket has been received."""
        await asyncio.wait_for(self.authenticated.wait(), timeout=timeout)
