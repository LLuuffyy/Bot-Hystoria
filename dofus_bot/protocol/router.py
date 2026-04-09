"""Prefix-based message router.

Each incoming protocol message starts with a 2- or 3-character prefix
identifying the message type. Handlers register themselves against a
prefix and are invoked for every matching message.

Routing order:
1. Try the 3-character prefix first (e.g. "GTS", "GDM", "GTE").
2. Fall back to the 2-character prefix (e.g. "HC", "GA", "GM").
3. If nothing matches, log at DEBUG and drop the message.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable, Dict

logger = logging.getLogger(__name__)

Handler = Callable[[str], Awaitable[None]]


class MessageRouter:
    def __init__(self) -> None:
        self._handlers: Dict[str, Handler] = {}

    def register(self, prefix: str, handler: Handler) -> None:
        if prefix in self._handlers:
            logger.warning("Overwriting handler for prefix %r", prefix)
        self._handlers[prefix] = handler

    def on(self, prefix: str) -> Callable[[Handler], Handler]:
        """Decorator form: ``@router.on("HC")``."""

        def decorator(fn: Handler) -> Handler:
            self.register(prefix, fn)
            return fn

        return decorator

    async def dispatch(self, message: str) -> None:
        if not message:
            return

        handler = self._find_handler(message)
        if handler is None:
            logger.debug("No handler for message: %s", message[:80])
            return

        try:
            await handler(message)
        except Exception:
            logger.exception("Handler failed for message: %s", message[:80])

    def _find_handler(self, message: str) -> Handler | None:
        # Try 3-char prefix first, then 2-char. This matters because "GT"
        # would otherwise swallow "GTS", "GTM", "GTE".
        for length in (3, 2):
            if len(message) >= length:
                prefix = message[:length]
                if prefix in self._handlers:
                    return self._handlers[prefix]
        return None
