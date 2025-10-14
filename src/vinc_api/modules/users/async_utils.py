from __future__ import annotations

import asyncio


def await_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():  # pragma: no cover - unlikely in sync contexts
        return asyncio.run_coroutine_threadsafe(coro, loop).result()
    return asyncio.run(coro)
