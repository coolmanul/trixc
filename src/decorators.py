from __future__ import annotations
import functools
import time
from typing import Callable, Optional


def listen(event: str):
    def decorator(func: Callable) -> Callable:
        func.__trixc_listener__ = event
        return func
    return decorator


def check(predicate: Callable):
    def decorator(func: Callable) -> Callable:
        if not hasattr(func, "__checks__"):
            func.__checks__ = []
        func.__checks__.append(predicate)
        return func
    return decorator


def cooldown(rate: int, per: float):
    def decorator(func: Callable) -> Callable:
        buckets: dict[str, list[float]] = {}

        @functools.wraps(func)
        async def wrapper(ctx, *args, **kwargs):
            from .errors import CommandOnCooldown
            user_id = ctx.author.id
            now = time.monotonic()
            history = [t for t in buckets.get(user_id, []) if now - t < per]
            if len(history) >= rate:
                retry_after = per - (now - history[0])
                raise CommandOnCooldown(per, retry_after)
            history.append(now)
            buckets[user_id] = history
            return await func(ctx, *args, **kwargs)

        wrapper.__checks__ = getattr(func, "__checks__", [])
        wrapper.__cooldown__ = (rate, per)
        return wrapper
    return decorator


def command(name: Optional[str] = None, **attrs):
    def decorator(func: Callable) -> Callable:
        func.__is_command__ = True
        func.__command_name__ = name or func.__name__
        func.__command_attrs__ = attrs
        return func
    return decorator