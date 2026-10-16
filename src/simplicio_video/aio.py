"""asyncio helpers shared by `swap` and `voice`: concurrency only where the time is spent waiting (network, polling).

Asyncio does not speed up CPU work (render, ffmpeg encodes stay serial). The HTTP clients stay on the standard library
(urllib, blocking), so each blocking call runs in a short-lived DAEMON thread (`athread`) and the event loop only
coordinates. A daemon thread, not `asyncio.to_thread`, on purpose: after Ctrl+C the interpreter must not wait for a
request that is still open (up to the HTTP timeout) before it exits.
"""
from __future__ import annotations

import argparse
import asyncio
import threading
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")


async def athread(fn: Callable[..., T], *args: Any) -> T:
    """Run the blocking `fn(*args)` in a daemon thread and await its result (exceptions, SystemExit included, propagate)."""
    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()

    def _deliver(setter, value) -> None:
        if not fut.done():  # a cancelled await leaves a done future behind: drop the late result
            setter(value)

    def work() -> None:
        try:
            res = fn(*args)
        except BaseException as e:  # noqa: BLE001 (forwarded to the awaiting task, SystemExit from VoiceError too)
            try:
                loop.call_soon_threadsafe(_deliver, fut.set_exception, e)
            except RuntimeError:  # loop already closed (Ctrl+C): nobody is waiting
                pass
        else:
            try:
                loop.call_soon_threadsafe(_deliver, fut.set_result, res)
            except RuntimeError:
                pass

    threading.Thread(target=work, daemon=True, name="simplicio-io").start()
    return await fut


def run_sync(coro: Awaitable[T]) -> T:
    """Run a coroutine to completion from sync code, also when this thread already runs an event loop (the MCP SDK calls
    sync tool functions from inside its loop): then the coroutine gets its own loop in a helper thread."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)  # type: ignore[arg-type]
    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["value"] = asyncio.run(coro)  # type: ignore[arg-type]
        except BaseException as e:  # noqa: BLE001
            box["error"] = e

    th = threading.Thread(target=target, name="simplicio-loop")
    th.start()
    th.join()
    if "error" in box:
        raise box["error"]
    return box["value"]


def clamp(requested: int | None, default: int, cap: int | None = None) -> int:
    """Effective concurrency: the request (or the default), at least 1, at most the cap."""
    n = default if requested is None else int(requested)
    n = max(1, n)
    return min(n, cap) if cap else n


def positive_int(text: str) -> int:
    """argparse `type` for --concurrency: an integer of 1 or more."""
    try:
        n = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"esperava um inteiro, recebi {text!r}") from None
    if n < 1:
        raise argparse.ArgumentTypeError("precisa ser 1 ou mais")
    return n
