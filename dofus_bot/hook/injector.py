"""Attach Frida to a running Dofus process and install the connect()
redirect hook so that game-server traffic lands on the local MITM
proxy.

Can be used standalone::

    python -m dofus_bot.hook --target "Dofus Retro.exe"

Or imported and called from the main proxy launcher.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Path to the Frida JS payload sitting next to this file.
_SCRIPT_PATH = Path(__file__).with_name("redirect.js")


def _prepare_script(
    real_ip: str,
    real_port: int,
    proxy_ip: str,
    proxy_port: int,
) -> str:
    """Read ``redirect.js`` and substitute the placeholder values."""
    raw = _SCRIPT_PATH.read_text(encoding="utf-8")
    return (
        raw.replace("%%REAL_IP%%", real_ip)
        .replace("%%PROXY_IP%%", proxy_ip)
        .replace("%%REAL_PORT%%", str(real_port))
        .replace("%%PROXY_PORT%%", str(proxy_port))
    )


def attach(
    target: str = "Dofus Retro.exe",
    real_ip: str = "162.19.127.155",
    real_port: int = 5555,
    proxy_ip: str = "127.0.0.1",
    proxy_port: int = 5555,
) -> None:
    """Attach to *target* and install the redirect hook.

    Blocks the calling thread until the Frida session ends (process
    exits or user presses Ctrl-C).
    """
    try:
        import frida  # type: ignore[import-untyped]
    except ImportError:
        logger.error(
            "frida is not installed.  Run:  pip install frida frida-tools"
        )
        raise SystemExit(1)

    js_code = _prepare_script(real_ip, real_port, proxy_ip, proxy_port)

    def on_message(message, _data):
        if message["type"] == "send":
            logger.info("%s", message["payload"])
        elif message["type"] == "error":
            logger.error("Frida error: %s", message.get("stack", message))

    logger.info("Attaching Frida to '%s' ...", target)
    try:
        session = frida.attach(target)
    except frida.ProcessNotFoundError:
        logger.error(
            "Process '%s' not found.  Launch Dofus first, then run the hook.",
            target,
        )
        raise SystemExit(1)

    script = session.create_script(js_code)
    script.on("message", on_message)
    script.load()
    logger.info(
        "Hook installed.  connect() calls to %s:%d will be "
        "redirected to %s:%d.",
        real_ip,
        real_port,
        proxy_ip,
        proxy_port,
    )
    logger.info("Press Ctrl+C to detach.")

    try:
        sys.stdin.read()
    except KeyboardInterrupt:
        pass
    finally:
        script.unload()
        session.detach()
        logger.info("Frida detached.")


def attach_background(
    target: str = "Dofus Retro.exe",
    real_ip: str = "162.19.127.155",
    real_port: int = 5555,
    proxy_ip: str = "127.0.0.1",
    proxy_port: int = 5555,
) -> threading.Thread:
    """Non-blocking variant: run :func:`attach` in a daemon thread.

    Returns the thread so the caller can join it if needed.
    """
    t = threading.Thread(
        target=attach,
        kwargs=dict(
            target=target,
            real_ip=real_ip,
            real_port=real_port,
            proxy_ip=proxy_ip,
            proxy_port=proxy_port,
        ),
        daemon=True,
        name="frida-hook",
    )
    t.start()
    return t


# Allow:  python -m dofus_bot.hook
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    attach()
