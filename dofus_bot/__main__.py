"""Entry point for the Dofus 1.29 MITM bot.

Usage:
    python -m dofus_bot --proxy
        Start the MITM proxy and log every packet passing through.
        Safe first run: no injection, no script loaded.

    python -m dofus_bot --proxy --script examples/farm_cra.lua
        (Not implemented yet) start the proxy AND load a Lua script
        that drives combat / farming via injected packets.

Stop cleanly with Ctrl-C.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from .config import DofusConfig
from .game.state import GameState
from .handlers.combat_handler import CombatHandler
from .handlers.map_handler import MapHandler
from .logger import setup_dofus_logging
from .network.proxy import DofusProxy
from .protocol.router import MessageRouter

logger = logging.getLogger("dofus_bot.main")


def build_routers(state: GameState) -> tuple[MessageRouter, MessageRouter, CombatHandler]:
    """Wire up packet handlers to two routers (client->server, server->client)."""
    map_handler = MapHandler(state)
    combat_handler = CombatHandler(state)

    # Server -> client router: everything the server tells us about the world
    server_router = MessageRouter()
    server_router.register("GDM", map_handler.on_map_data)
    server_router.register("GM", map_handler.on_map_actors)
    server_router.register("GJK", combat_handler.on_fight_join)
    server_router.register("GTS", combat_handler.on_turn_start)
    server_router.register("GTM", combat_handler.on_turn_mid)
    server_router.register("GTE", combat_handler.on_turn_end)
    server_router.register("GE", combat_handler.on_fight_end)

    # Client -> server router: for now we only log, but the scripting
    # layer will hook here too (e.g. to observe what the real client
    # sends when the user clicks a monster).
    client_router = MessageRouter()

    return client_router, server_router, combat_handler


async def run_proxy(config: DofusConfig) -> None:
    state = GameState()
    client_router, server_router, combat_handler = build_routers(state)

    proxy = DofusProxy(
        listen_host=config.proxy_host,
        listen_port=config.proxy_port,
        upstream_host=config.upstream_host,
        upstream_port=config.upstream_port,
    )
    proxy.on_client_message(client_router.dispatch)
    proxy.on_server_message(server_router.dispatch)

    logger.info("=" * 60)
    logger.info("Dofus MITM proxy")
    logger.info("  listen   : %s:%d  <-- point your Dofus client here",
                config.proxy_host, config.proxy_port)
    logger.info("  upstream : %s:%d",
                config.upstream_host, config.upstream_port)
    logger.info("  script   : %s", config.script or "(none)")
    logger.info("=" * 60)
    logger.info("Waiting for the Dofus client to connect...")

    try:
        await proxy.serve_forever()
    except asyncio.CancelledError:
        pass
    finally:
        await proxy.stop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m dofus_bot")
    parser.add_argument(
        "--proxy",
        action="store_true",
        help="Start the MITM proxy (the only mode for now).",
    )
    parser.add_argument(
        "--script",
        type=str,
        default=None,
        help="Lua script to load (relative to dofus_bot/data/scripts/).",
    )
    return parser.parse_args()


async def main_async() -> None:
    config = DofusConfig.load()
    setup_dofus_logging(config.log_level)

    args = parse_args()
    if args.script is not None:
        config.script = args.script

    if not args.proxy:
        logger.error("No mode selected. Use --proxy.")
        return

    await run_proxy(config)


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")


if __name__ == "__main__":
    main()
