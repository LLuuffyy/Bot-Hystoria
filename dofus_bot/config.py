"""Configuration loader for dofus_bot (MITM mode).

Loaded from environment variables via ``python-dotenv``. Credentials
are NOT needed here: in MITM mode the real Dofus client handles the
login, the bot just watches the resulting traffic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


@dataclass
class DofusConfig:
    # Local proxy the Dofus client connects to.
    proxy_host: str
    proxy_port: int

    # Real Hystoria server we forward traffic to.
    upstream_host: str
    upstream_port: int

    # Optional Lua script path (relative to dofus_bot/data/scripts/).
    script: Optional[str]

    log_level: str

    @classmethod
    def load(cls) -> "DofusConfig":
        load_dotenv()

        proxy_host = os.environ.get("DOFUS_PROXY_HOST", "127.0.0.1").strip()
        proxy_port = int(os.environ.get("DOFUS_PROXY_PORT", "5555"))
        upstream_host = os.environ.get(
            "DOFUS_UPSTREAM_HOST", "162.19.127.155"
        ).strip()
        upstream_port = int(os.environ.get("DOFUS_UPSTREAM_PORT", "5555"))
        script = os.environ.get("DOFUS_SCRIPT", "").strip() or None
        log_level = os.environ.get("DOFUS_LOG_LEVEL", "INFO").strip()

        return cls(
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            upstream_host=upstream_host,
            upstream_port=upstream_port,
            script=script,
            log_level=log_level,
        )
