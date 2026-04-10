"""Allow ``python -m dofus_bot.hook`` to launch the Frida redirect hook
as a standalone tool.

Usage::

    python -m dofus_bot.hook
    python -m dofus_bot.hook --target "Dofus Retro.exe"
    python -m dofus_bot.hook --real-ip 162.19.127.155 --proxy-ip 127.0.0.1
"""

from __future__ import annotations

import argparse
import logging

from .injector import attach


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        prog="python -m dofus_bot.hook",
        description="Frida hook: redirect Dofus game-server connections to the MITM proxy.",
    )
    parser.add_argument(
        "--target",
        default="Dofus Retro.exe",
        help="Process name or PID to attach to (default: 'Dofus Retro.exe').",
    )
    parser.add_argument("--real-ip", default="162.19.127.155")
    parser.add_argument("--real-port", type=int, default=5555)
    parser.add_argument("--proxy-ip", default="127.0.0.1")
    parser.add_argument("--proxy-port", type=int, default=5555)
    args = parser.parse_args()

    attach(
        target=args.target,
        real_ip=args.real_ip,
        real_port=args.real_port,
        proxy_ip=args.proxy_ip,
        proxy_port=args.proxy_port,
    )


if __name__ == "__main__":
    main()
