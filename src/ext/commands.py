from __future__ import annotations
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..bot import Bot


def command(name: Optional[str] = None, **attrs):
    """mark a cog method as a command."""
    def decorator(func):
        func.__is_command__ = True
        func.__command_name__ = name or func.__name__
        func.__command_attrs__ = attrs
        return func
    return decorator


def listen(event: str):
    """mark a cog method as an event listener."""
    def decorator(func):
        func.__trixc_listener__ = event
        return func
    return decorator


class Cog:
    """
    base class for command extensions.

    group related commands and event listeners into a single class.
    register with :meth:`bot.add_cog`.

    example::

        class moderation(trixc.cog):

            @trixc.cog_command()
            async def kick(self, ctx, user_id: str):
                member = await ctx.room.get_member(user_id)
                if member:
                    await member.kick()
                    await ctx.reply(f"kicked {member.name}.")

            @trixc.listen("member_join")
            async def on_join(self, member):
                await member.room.send(f"welcome, {member.name}!")
    """

    _bot: Optional["Bot"] = None

    async def cog_load(self) -> None:
        """called when the cog is loaded. override for async setup."""

    async def cog_unload(self) -> None:
        """called when the cog is unloaded. override for async cleanup."""

    async def cog_command_error(self, ctx, error: Exception) -> None:
        """called on command error within this cog. re-raises by default."""
        raise error