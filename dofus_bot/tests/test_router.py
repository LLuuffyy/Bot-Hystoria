"""Unit tests for :mod:`dofus_bot.protocol.router`.

These exercise the edge case that prompted the 3-char-first lookup:
handlers registered for ``GT`` must not swallow ``GTS`` / ``GTM`` /
``GTE`` messages.
"""

from __future__ import annotations

import asyncio
import unittest

from dofus_bot.protocol.router import MessageRouter


class RouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.router = MessageRouter()

    def _record(self, tag: str):
        async def handler(message: str) -> None:
            self.calls.append((tag, message))

        return handler

    def test_three_char_prefix_wins_over_two_char(self) -> None:
        self.router.register("GT", self._record("GT"))
        self.router.register("GTS", self._record("GTS"))

        asyncio.run(self.router.dispatch("GTS4242|30000"))
        asyncio.run(self.router.dispatch("GT1|2|3"))

        self.assertEqual(
            self.calls,
            [("GTS", "GTS4242|30000"), ("GT", "GT1|2|3")],
        )

    def test_unknown_prefix_is_ignored(self) -> None:
        self.router.register("HC", self._record("HC"))
        asyncio.run(self.router.dispatch("ZZsomething"))
        self.assertEqual(self.calls, [])

    def test_empty_message_is_ignored(self) -> None:
        self.router.register("HC", self._record("HC"))
        asyncio.run(self.router.dispatch(""))
        self.assertEqual(self.calls, [])

    def test_handler_exception_does_not_propagate(self) -> None:
        async def boom(message: str) -> None:
            raise RuntimeError("handler crashed")

        self.router.register("HC", boom)
        # Should not raise.
        asyncio.run(self.router.dispatch("HCabcdef"))


if __name__ == "__main__":
    unittest.main()
