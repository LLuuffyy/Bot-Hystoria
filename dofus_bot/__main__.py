"""Entry point for the Dofus 1.29 socket bot.

Usage:
    python -m dofus_bot [--sniff] [--login]

Modes:
    --sniff   Connect and dump every received message (protocol discovery).
              Does NOT send any credentials. Safe first test.
    --login   Run the authentication flow (HC -> credentials -> server select)
              and stop after receiving the game server ticket.

Both modes exit cleanly on Ctrl-C.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from .config import DofusConfig
from .handlers.auth_handler import AuthHandler
from .logger import setup_dofus_logging
from .network.connection import DofusConnection
from .protocol.router import MessageRouter

logger = logging.getLogger("dofus_bot.main")


async def run_sniffer(config: DofusConfig) -> None:
    """Connect to the auth server and log every incoming message.

    Sends nothing. Useful to discover the exact protocol variant used by
    the Hystoria server (prefixes, separators, delimiters).
    """
    conn = DofusConnection(config.auth_host, config.auth_port)
    await conn.connect()
    logger.info("=== SNIFF MODE === (press Ctrl-C to stop)")
    try:
        async for msg in conn.listen():
            logger.info("<< %s", msg)
    except ConnectionError as exc:
        logger.warning("Connection closed: %s", exc)
    finally:
        await conn.disconnect()


async def run_login(config: DofusConfig) -> None:
    """Run the authentication flow up to the game server handoff."""
    conn = DofusConnection(config.auth_host, config.auth_port)
    router = MessageRouter()
    auth = AuthHandler(conn, config)

    router.register("HC", auth.on_hello_connect)
    router.register("AYK", auth.on_server_ticket)
    router.register("AlEx", auth.on_account_error)

    await conn.connect()

    async def network_loop() -> None:
        try:
            async for msg in conn.listen():
                await router.dispatch(msg)
        except ConnectionError as exc:
            logger.warning("Connection closed: %s", exc)

    loop_task = asyncio.create_task(network_loop())

    try:
        await auth.wait_authenticated(timeout=30.0)
        logger.info(
            "Authenticated successfully. Game server: %s:%s (ticket=%s)",
            auth.game_host,
            auth.game_port,
            auth.game_ticket,
        )
    except asyncio.TimeoutError:
        logger.error("Timed out waiting for authentication")
    finally:
        loop_task.cancel()
        try:
            await loop_task
        except (asyncio.CancelledError, ConnectionError):
            pass
        await conn.disconnect()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m dofus_bot")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--sniff",
        action="store_true",
        help="Log all incoming messages, send nothing (protocol discovery).",
    )
    mode.add_argument(
        "--login",
        action="store_true",
        help="Run the full authentication flow and stop after ticket.",
    )
    return parser.parse_args()


async def main_async() -> None:
    config = DofusConfig.load()
    setup_dofus_logging(config.log_level)

    args = parse_args()
    if args.sniff:
        await run_sniffer(config)
    elif args.login:
        await run_login(config)


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")


if __name__ == "__main__":
    main()
