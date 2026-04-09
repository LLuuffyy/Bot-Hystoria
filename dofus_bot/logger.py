"""Dedicated logging setup for dofus_bot.

Kept separate from the voting bot's ``logger_setup.py`` so the two bots
can coexist with their own log files and levels.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_dofus_logging(level: str | int | None = None) -> None:
    """Configure logging for the Dofus socket bot.

    - Console: level from ``DOFUS_LOG_LEVEL`` env var (default INFO)
    - File: ``logs/dofus_bot.log``, DEBUG, rotating 5MB x 3
    """
    Path("logs").mkdir(exist_ok=True)

    if level is None:
        level = os.environ.get("DOFUS_LOG_LEVEL", "INFO")
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    bot_logger = logging.getLogger("dofus_bot")
    bot_logger.setLevel(logging.DEBUG)
    # Avoid duplicate handlers if called twice.
    for h in list(bot_logger.handlers):
        bot_logger.removeHandler(h)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(fmt)
    bot_logger.addHandler(console)

    file_handler = RotatingFileHandler(
        "logs/dofus_bot.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    bot_logger.addHandler(file_handler)

    # Do not propagate to root to keep the voting bot's log file clean.
    bot_logger.propagate = False
