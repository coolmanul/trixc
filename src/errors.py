from __future__ import annotations
from typing import Optional


class TrixcException(Exception):
    """base class for all trixc exceptions."""


class HTTPException(TrixcException):
    """raised when an http request fails."""

    def __init__(self, status: int, message: str = ""):
        self.status = status
        self.message = message
        super().__init__(f"HTTP {status}: {message}")


class Forbidden(HTTPException):
    """http 403 - bot lacks permission."""

    def __init__(self, message: str = ""):
        super().__init__(403, message or "Missing permissions")


class NotFound(HTTPException):
    """http 404 - resource does not exist."""

    def __init__(self, message: str = ""):
        super().__init__(404, message or "Resource not found")


class RateLimited(HTTPException):
    """http 429 - rate limited by homeserver."""

    def __init__(self, retry_after: float = 0.0):
        self.retry_after = retry_after
        super().__init__(429, f"Rate limited. Retry after {retry_after:.1f}s")


class LoginFailure(TrixcException):
    """raised when login fails (bad credentials, homeserver error, etc.)."""


class ConnectionClosed(TrixcException):
    """raised when the sync connection is closed unexpectedly."""



class CommandError(TrixcException):
    """base class for all command-related errors.
    caught by the on_command_error listener."""


class CommandNotFound(CommandError):
    """raised when a prefix command is not registered."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Command '{name}' not found")


class CheckFailure(CommandError):
    """raised when a @check() predicate returns false."""


class MissingRequiredArgument(CommandError):
    """raised when a required command argument is not provided."""

    def __init__(self, param: str):
        self.param = param
        super().__init__(f"Missing required argument: '{param}'")


class BadArgument(CommandError):
    """raised when an argument cannot be converted to the expected type."""

    def __init__(self, message: str = ""):
        super().__init__(message or "Bad argument")


class CommandOnCooldown(CommandError):
    """raised when a command is invoked while on cooldown."""

    def __init__(self, cooldown: float, retry_after: float):
        self.cooldown = cooldown
        self.retry_after = retry_after
        super().__init__(
            f"Command on cooldown. Try again in {retry_after:.1f}s"
        )


class CommandInvokeError(CommandError):
    """wraps an unexpected exception raised inside a command callback."""

    def __init__(self, original: Exception):
        self.original = original
        super().__init__(f"Command raised an exception: {original!r}")


class DisabledCommand(CommandError):
    """raised when a disabled command is invoked."""


class NoPrivateMessage(CommandError):
    """raised when a command is used outside a guild/room context."""


class NotOwner(CheckFailure):
    """raised when bot.is_owner() check fails."""


class RoomNotFound(TrixcException):
    """the requested room was not found in cache or on the homeserver."""

    def __init__(self, room_id: str):
        self.room_id = room_id
        super().__init__(f"Room not found: {room_id}")


class UserNotFound(TrixcException):
    """the requested user was not found."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        super().__init__(f"User not found: {user_id}")


class MemberNotFound(TrixcException):
    """the requested member is not in the room."""

    def __init__(self, user_id: str, room_id: str):
        self.user_id = user_id
        self.room_id = room_id
        super().__init__(f"Member {user_id} not in room {room_id}")


class BotMissingPermissions(TrixcException):
    """bot lacks the required power level for this action."""

    def __init__(self, required: int, current: int):
        self.required = required
        self.current = current
        super().__init__(
            f"Bot power level {current} < required {required}"
        )


class InvalidArgument(TrixcException):
    """a function was called with an invalid argument value."""