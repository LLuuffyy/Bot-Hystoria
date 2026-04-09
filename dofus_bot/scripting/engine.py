"""Lua script runtime for the Dofus MITM bot.

The engine owns a single :class:`lupa.LuaRuntime`, loads a ``.lua``
file once, exposes the :class:`BotAPI` as the global ``bot`` and then
lets the script drive the bot in one of two (composable) styles:

1. **Event-driven** - the script calls ``bot:on("turn_start", cb)``,
   ``bot:on("fight_start", cb)``, ... and returns. The engine keeps
   the runtime alive and invokes the registered callbacks whenever
   the corresponding events fire on the :class:`EventBus`.

2. **Sequential main loop** - the script runs a top-level
   ``while true do ... bot:wait(1) end`` loop. The loop is executed
   by a dedicated worker thread, and event callbacks are serialised
   into the same thread via an in-process queue so the Lua runtime
   is never touched from two threads at once.

Hot reload: the engine polls the script file's mtime every second
from a background asyncio task. When it changes the runtime is torn
down and the script is re-loaded in-place, without restarting the
proxy session.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from .api import BotAPI
from .events import EventBus
from .sandbox import apply_sandbox

if TYPE_CHECKING:  # only for type hints, avoid importing at runtime
    from ..game.state import GameState
    from ..network.proxy import DofusProxy

logger = logging.getLogger(__name__)


class LuaUnavailableError(RuntimeError):
    """Raised when lupa is not installed but a script was requested."""


# Sentinel pushed onto the work queue by :meth:`LuaEngine.stop`.
_STOP_SENTINEL = object()


class LuaEngine:
    """Owns a Lua runtime running on a dedicated worker thread."""

    def __init__(
        self,
        script_path: Path,
        state: "GameState",
        proxy: "DofusProxy",
        event_bus: EventBus,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self.script_path = Path(script_path)
        self._state = state
        self._proxy = proxy
        self._event_bus = event_bus
        self._loop = loop

        self._lua: Any = None  # lupa.LuaRuntime (typed loose to keep lupa optional)
        self._bot_api: Optional[BotAPI] = None

        # event name -> list of lua functions registered via bot:on()
        self._event_handlers: Dict[str, List[Any]] = {}

        # Work queue consumed by the worker thread. Items are either
        # callables (no-arg) or the _STOP_SENTINEL.
        self._work: "queue.Queue[Any]" = queue.Queue()

        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._hot_reload_task: Optional[asyncio.Task] = None
        self._last_mtime: Optional[float] = None

    # ------------------------------------------------------------------ #
    # Public API (called from the asyncio side)
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        """Load the script and spin up the worker thread.

        Raises :class:`LuaUnavailableError` if lupa is not installed
        and :class:`FileNotFoundError` if the script does not exist.
        """
        if not self.script_path.exists():
            raise FileNotFoundError(self.script_path)

        try:
            import lupa  # noqa: F401  (imported for side effect / availability check)
        except ImportError as exc:
            raise LuaUnavailableError(
                "lupa is not installed. Run 'pip install lupa' or reinstall "
                "the dofus_bot requirements."
            ) from exc

        self._load_runtime()

        # Subscribe ourselves to every known event on the bus. Individual
        # event -> lua handlers are still looked up in _event_handlers.
        for event in (
            "fight_start",
            "fight_end",
            "turn_start",
            "turn_end",
            "map_change",
            "actors_update",
            "hp_low",
        ):
            self._event_bus.on(event, self._make_forwarder(event))

        self._thread = threading.Thread(
            target=self._worker_loop,
            name="dofus_bot-lua",
            daemon=True,
        )
        self._thread.start()

        # Hand the top-level script body to the worker thread as its
        # first task. Any ``bot:on(...)`` calls done at top level are
        # recorded synchronously; any ``while true do`` loop runs there
        # and blocks the worker, at which point events queue up behind
        # it (which is the documented behaviour).
        self._work.put(self._run_main_body)

        self._hot_reload_task = asyncio.create_task(self._hot_reload_poller())

        logger.info("Lua engine started on %s", self.script_path)

    async def stop(self) -> None:
        """Signal the worker to exit and wait for it."""
        self._stop_flag.set()
        self._work.put(_STOP_SENTINEL)
        if self._hot_reload_task is not None:
            self._hot_reload_task.cancel()
            try:
                await self._hot_reload_task
            except asyncio.CancelledError:
                pass
            self._hot_reload_task = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("Lua engine stopped")

    def should_stop(self) -> bool:
        """Thin accessor used by :meth:`BotAPI.wait` so sleeps abort fast."""
        return self._stop_flag.is_set()

    def register_event(self, event: str, callback: Any) -> None:
        """Called from Lua via ``bot:on(event, fn)``.

        Must be callable from the worker thread (it is: the worker
        runs Lua which calls into this method synchronously).
        """
        self._event_handlers.setdefault(event, []).append(callback)
        logger.debug("Lua registered handler for event %r", event)

    # ------------------------------------------------------------------ #
    # Runtime management
    # ------------------------------------------------------------------ #

    def _load_runtime(self) -> None:
        """Create a fresh :class:`lupa.LuaRuntime` and install the bot."""
        import lupa

        self._lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        self._bot_api = BotAPI(
            state=self._state,
            proxy=self._proxy,
            loop=self._loop,
            engine=self,
        )
        self._lua.globals().bot = self._bot_api
        apply_sandbox(self._lua)
        self._event_handlers.clear()

        try:
            self._last_mtime = self.script_path.stat().st_mtime
        except FileNotFoundError:
            self._last_mtime = None

    def _run_main_body(self) -> None:
        """Execute the top level of the script in the worker thread."""
        try:
            source = self.script_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.error("Lua script disappeared: %s", self.script_path)
            return
        logger.info("Running Lua script: %s", self.script_path.name)
        try:
            self._lua.execute(source)
        except Exception as exc:
            # RuntimeError("bot stopped") is how bot:wait signals shutdown.
            if str(exc) == "bot stopped":
                logger.debug("Lua main body exited via stop signal")
            else:
                logger.exception("Lua script raised an error")

    async def _hot_reload_poller(self) -> None:
        """Re-read the script file when its mtime changes on disk."""
        while True:
            try:
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                return
            try:
                mtime = self.script_path.stat().st_mtime
            except FileNotFoundError:
                continue
            if self._last_mtime is None:
                self._last_mtime = mtime
                continue
            if mtime != self._last_mtime:
                logger.info(
                    "Lua script modified on disk, reloading: %s",
                    self.script_path.name,
                )
                self._last_mtime = mtime
                # Queue a reload work item. The currently running main
                # body (if any) will finish its current bot:wait chunk
                # before the worker picks the next item.
                self._work.put(self._reload_in_worker)

    def _reload_in_worker(self) -> None:
        """Worker-thread reload: rebuild runtime + re-run the script."""
        try:
            self._load_runtime()
        except Exception:
            logger.exception("Lua runtime recreation failed during reload")
            return
        self._run_main_body()

    # ------------------------------------------------------------------ #
    # Worker thread loop + event forwarding
    # ------------------------------------------------------------------ #

    def _worker_loop(self) -> None:
        """Single-consumer loop draining the work queue until stopped."""
        while True:
            item = self._work.get()
            if item is _STOP_SENTINEL:
                return
            if self._stop_flag.is_set():
                return
            try:
                item()
            except Exception:
                logger.exception("Lua work item crashed")

    def _make_forwarder(self, event: str):
        """Return an async callback that queues a Lua dispatch for *event*."""

        async def forwarder(payload: dict) -> None:
            handlers = list(self._event_handlers.get(event, ()))
            if not handlers:
                return

            def run_handlers() -> None:
                for cb in handlers:
                    try:
                        cb(payload)
                    except Exception as exc:
                        if str(exc) == "bot stopped":
                            return
                        logger.exception(
                            "Lua callback for %s failed", event
                        )

            self._work.put(run_handlers)

        return forwarder
