from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import Context

class PermissionLevel:
    """named power level thresholds."""
    DEFAULT    = 0    # regular member - can send messages
    VOICE      = 10   # can trigger media/voice (convention)
    MODERATOR  = 50   # can kick, redact, change room state
    ADMIN      = 100  # full room control

class Permissions:
    """
    wraps a matrix power level with discord-style boolean permission flags.

    parameters
    ----------
    power_level : int
        the member's current power level in the room.

    example::

        perms = permissions(member.power_level)
        if perms.kick_members:
            await member.kick()
    """

    def __init__(self, power_level: int = 0):
        self.value = power_level

    @property
    def send_messages(self) -> bool:
        """can send messages (default threshold: 0)."""
        return self.value >= PermissionLevel.DEFAULT

    @property
    def manage_messages(self) -> bool:
        """can redact other users' messages (threshold: 50)."""
        return self.value >= PermissionLevel.MODERATOR

    @property
    def kick_members(self) -> bool:
        """can kick members (threshold: 50)."""
        return self.value >= PermissionLevel.MODERATOR

    @property
    def ban_members(self) -> bool:
        """can ban members (threshold: 50)."""
        return self.value >= PermissionLevel.MODERATOR

    @property
    def manage_channels(self) -> bool:
        """can change room name/topic (threshold: 50)."""
        return self.value >= PermissionLevel.MODERATOR

    @property
    def administrator(self) -> bool:
        """full control - power level 100."""
        return self.value >= PermissionLevel.ADMIN

    @property
    def manage_roles(self) -> bool:
        """can set power levels (threshold: 100)."""
        return self.value >= PermissionLevel.ADMIN

    @property
    def mention_everyone(self) -> bool:
        """alias for moderator+ (no native matrix concept)."""
        return self.value >= PermissionLevel.MODERATOR

    def is_superset(self, other: "Permissions") -> bool:
        """true if this power level >= other's power level."""
        return self.value >= other.value

    def __ge__(self, other: "Permissions") -> bool:
        return self.value >= other.value

    def __le__(self, other: "Permissions") -> bool:
        return self.value <= other.value

    def __repr__(self) -> str:
        return f"<Permissions level={self.value}>"

def has_permissions(**flags: bool):
    """
    command check: verify the invoking member has the required permissions.

    accepts keyword arguments matching :class:`permissions` boolean properties.

    example::

        @bot.command()
        @has_permissions(kick_members=true)
        async def kick(ctx, user_id: str):
            member = await ctx.get_member(user_id)
            await member.kick()
    """
    def predicate(ctx: "Context") -> bool:
        from .errors import BotMissingPermissions, CheckFailure
        member = ctx.room.members.get(ctx.author.id)
        level = member.power_level if member else 0
        perms = Permissions(level)
        for flag, required in flags.items():
            if required and not getattr(perms, flag, False):
                raise CheckFailure(
                    f"Missing permission: {flag} "
                    f"(power level {level} insufficient)"
                )
        return True
    return predicate


def bot_has_permissions(**flags: bool):
    """
    command check: verify the bot itself has the required permissions.

    example::

        @bot.command()
        @bot_has_permissions(ban_members=true)
        async def ban(ctx, user_id: str):
            ...
    """
    def predicate(ctx: "Context") -> bool:
        from .errors import BotMissingPermissions, CheckFailure
        bot_id = ctx.bot.user.id
        member = ctx.room.members.get(bot_id)
        level = member.power_level if member else 0
        perms = Permissions(level)
        for flag, required in flags.items():
            if required and not getattr(perms, flag, False):
                raise BotMissingPermissions(
                    PermissionLevel.MODERATOR, level
                )
        return True
    return predicate


def is_owner():
    """
    command check: only the bot owner (set via ``bot.owner_id``) can run this.

    example::

        @bot.command()
        @is_owner()
        async def shutdown(ctx):
            await ctx.send("shutting down...")
            await ctx.bot.close()
    """
    def predicate(ctx: "Context") -> bool:
        from .errors import NotOwner
        owner_id = getattr(ctx.bot, "owner_id", None)
        if owner_id and ctx.author.id != owner_id:
            raise NotOwner(f"{ctx.author.id} is not the bot owner")
        return True
    return predicate