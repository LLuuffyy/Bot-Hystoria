"""Attach Frida to a running Dofus process and install the connect()
redirect hook so that game-server traffic lands on the local MITM
proxy.

Can be used standalone::

    python -m dofus_bot.hook --target "Dofus Retro.exe"
    python -m dofus_bot.hook --target 12345      # attach by PID

Or imported and called from the main proxy launcher.

Electron apps like the Hystoria V5 client spawn *several* processes
with the same executable name (main, GPU, renderer, Flash plugin, ...).
The TCP connection to the game server is made from whichever process
hosts the pepperflash plugin, so this module attaches the hook to
**every** matching process.  Only the one that actually calls
``connect(162.19.127.155:5555)`` will trigger the rewrite; the others
remain silent.
"""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import List

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


def _resolve_targets(frida_mod, target: str) -> List[int]:
    """Turn *target* into a list of PIDs to attach to.

    - If *target* is purely numeric, it is treated as a PID.
    - Otherwise, all running processes whose name matches *target*
      (case-insensitive) are returned.
    """
    target_stripped = target.strip()
    if target_stripped.isdigit():
        return [int(target_stripped)]

    # In Frida 14+, process enumeration lives on the Device object.
    # Fall back to the module-level helper for older releases.
    try:
        device = frida_mod.get_local_device()
        procs = device.enumerate_processes()
    except AttributeError:
        procs = frida_mod.enumerate_processes()  # type: ignore[attr-defined]

    matches: List[int] = []
    wanted = target_stripped.lower()
    for proc in procs:
        if proc.name.lower() == wanted:
            matches.append(proc.pid)
    return matches


def attach(
    target: str = "Dofus Retro.exe",
    real_ip: str = "162.19.127.155",
    real_port: int = 5555,
    proxy_ip: str = "127.0.0.1",
    proxy_port: int = 5555,
) -> None:
    """Attach to *target* and install the redirect hook.

    Blocks the calling thread until the Frida session ends (process
    exits or user presses Ctrl-C).  When *target* is a process name,
    the hook is installed in every matching process (Electron apps
    typically spawn 4+ of them).
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

    pids = _resolve_targets(frida, target)
    if not pids:
        logger.error(
            "No process matching '%s' found.  Launch Dofus first, then run the hook.",
            target,
        )
        raise SystemExit(1)

    logger.info(
        "Found %d process(es) matching '%s': %s",
        len(pids),
        target,
        ", ".join(str(p) for p in pids),
    )

    sessions = []
    scripts = []
    for pid in pids:
        try:
            session = frida.attach(pid)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not attach to PID %d: %s", pid, exc)
            continue
        try:
            script = session.create_script(js_code)
            script.on("message", on_message)
            script.load()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load script in PID %d: %s", pid, exc)
            try:
                session.detach()
            except Exception:
                pass
            continue
        sessions.append(session)
        scripts.append(script)
        logger.info("Hook installed in PID %d", pid)

    if not sessions:
        logger.error("Failed to install the hook in any process.  Aborting.")
        raise SystemExit(1)

    logger.info(
        "Hook installed in %d process(es).  connect() calls to %s:%d will be "
        "redirected to %s:%d.",
        len(sessions),
        real_ip,
        real_port,
        proxy_ip,
        proxy_port,
    )
    logger.info("Press Ctrl+C to detach.")

    try:
        # Block forever until Ctrl-C or the Dofus process exits.
        # We read from stdin so the user can just close the window.
        sys.stdin.read()
    except KeyboardInterrupt:
        pass
    finally:
        for script in scripts:
            try:
                script.unload()
            except Exception:
                pass
        for session in sessions:
            try:
                session.detach()
            except Exception:
                pass
        logger.info("Frida detached from %d process(es).", len(sessions))


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
