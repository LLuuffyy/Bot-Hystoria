"""Configuration loader for dofus_bot.

Loads credentials, server endpoint and runtime options from environment
variables (via ``python-dotenv``, already used by the voting bot).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


@dataclass
class DofusConfig:
    username: str
    password: str
    character: str
    auth_host: str
    auth_port: int
    server_id: int
    script: Optional[str]
    log_level: str

    @classmethod
    def load(cls) -> "DofusConfig":
        load_dotenv()

        username = os.environ.get("DOFUS_USERNAME", "").strip()
        password = os.environ.get("DOFUS_PASSWORD", "")
        character = os.environ.get("DOFUS_CHARACTER", "").strip()
        auth_host = os.environ.get("DOFUS_AUTH_HOST", "play-hystoria.net").strip()
        auth_port = int(os.environ.get("DOFUS_AUTH_PORT", "443"))
        server_id = int(os.environ.get("DOFUS_SERVER_ID", "0"))
        script = os.environ.get("DOFUS_SCRIPT", "").strip() or None
        log_level = os.environ.get("DOFUS_LOG_LEVEL", "INFO").strip()

        if not username or not password:
            raise RuntimeError(
                "DOFUS_USERNAME and DOFUS_PASSWORD must be set in .env"
            )

        return cls(
            username=username,
            password=password,
            character=character,
            auth_host=auth_host,
            auth_port=auth_port,
            server_id=server_id,
            script=script,
            log_level=log_level,
        )
