"""command context - passed to every command callback."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .embed import Embed
from .message import Message

if TYPE_CHECKING:
    from .bot import Bot
    from .room import Room
    from .user import User, Member


class Context:
    """
    represents the invocation context of a command.

    attributes
    ----------
    bot : Bot
    message : Message
        the message that triggered the command.
    room : Room
    author : User
    prefix : str
    command_name : str
    args : list[str]
        positional arguments after the command name.
    kwargs : dict
        keyword arguments (not used by default parser, available for custom parsers).
    """

    def __init__(
        self,
        bot: "Bot",
        message: Message,
        *,
        command_name: str,
        prefix: str,
        args: Optional[list] = None,
        kwargs: Optional[dict] = None,
    ):
        self.bot = bot
        self.message = message
        self.room: "Room" = message.room
        self.author: "User" = message.author
        self.prefix = prefix
        self.command_name = command_name
        self.args: list[str] = args or []
        self.kwargs: dict = kwargs or {}

    async def send(self, content: str = "", *, embed: Optional[Embed] = None, **kwargs) -> Message:
        """send a message to the room where the command was invoked."""
        return await self.room.send(content, embed=embed, **kwargs)

    async def reply(self, content: str = "", *, embed: Optional[Embed] = None, **kwargs) -> Message:
        """reply to the command message."""
        return await self.room.send(content, embed=embed, reply_to=self.message.id, **kwargs)

    async def typing(self, *, duration: int = 4000) -> None:
        """send a typing indicator in the command's room."""
        await self.room.typing(duration=duration)

    @property
    def member(self) -> Optional["Member"]:
        """the author as a member of the command's room (if cached)."""
        return self.room.members.get(self.author.id)

    def __repr__(self) -> str:
        return f"<Context command={self.command_name!r} author={self.author.id!r}>"