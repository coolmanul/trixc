from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from .client import MatrixClient
    from .room import Room
    from .user import User


@dataclass
class Attachment:
    """
    a file attached to a message.

    attributes
    ----------
    url : str
        ``mxc://`` uri of the file.
    filename : str
        original filename.
    content_type : str
        mime type, e.g. ``image/png``.
    size : int
        file size in bytes.
    """
    url: str
    filename: str
    content_type: str = ""
    size: int = 0

    @property
    def is_image(self) -> bool:
        return self.content_type.startswith("image/")

    @property
    def is_audio(self) -> bool:
        return self.content_type.startswith("audio/")

    @property
    def is_video(self) -> bool:
        return self.content_type.startswith("video/")

    def __repr__(self) -> str:
        return f"<Attachment filename={self.filename!r} type={self.content_type!r}>"


class Message:
    """
    represents a matrix room message.

    attributes
    ----------
    id : str
        event id, e.g. ``$abc123``.
    room : room
        the room this message was sent in.
    author : user
        the user who sent this message.
    content : str
        plain text body.
    html_content : str or none
        formatted html body, if present.
    created_at : datetime
        utc timestamp of when the message was sent.
    reference : message or none
        the message being replied to, if any.
    attachments : list[attachment]
        attached files.
    msg_type : str
        raw matrix msgtype (``m.text``, ``m.image``, etc.).
    """

    __slots__ = (
        "_client", "id", "room", "author", "content", "html_content",
        "created_at", "reference", "attachments", "msg_type", "_deleted",
    )

    def __init__(
        self,
        *,
        client: "MatrixClient",
        event_id: str,
        room: "Room",
        author: "User",
        content: str = "",
        html_content: Optional[str] = None,
        created_at: Optional[datetime] = None,
        reference: Optional["Message"] = None,
        attachments: Optional[List[Attachment]] = None,
        msg_type: str = "m.text",
    ):
        self._client = client
        self.id = event_id
        self.room = room
        self.author = author
        self.content = content
        self.html_content = html_content
        self.created_at = created_at or datetime.utcnow()
        self.reference = reference
        self.attachments: List[Attachment] = attachments or []
        self.msg_type = msg_type
        self._deleted = False


    async def reply(
        self,
        content: str = "",
        *,
        embed=None,
        notice: bool = False,
    ) -> "Message":
        """
        reply to this message.

        example::

            @bot.command()
            async def ping(ctx):
                await ctx.message.reply("pong!")
        """
        return await self.room.send(
            content,
            embed=embed,
            reply_to=self.id,
            notice=notice,
        )

    async def edit(self, new_content: str) -> None:
        """edit this message (only works if the author is the bot)."""
        if self.author.id != self._client.user.id:
            from .errors import Forbidden
            raise Forbidden("Cannot edit another user's message")
        await self._client._http.edit_message(self.room.id, self.id, new_content)
        self.content = new_content

    async def delete(self, reason: str = "") -> None:
        """redact (delete) this message."""
        await self._client._http.redact_event(self.room.id, self.id, reason)
        self._deleted = True

    async def add_reaction(self, emoji: str) -> None:
        """add a reaction to this message."""
        await self._client._http.send_reaction(self.room.id, self.id, emoji)

    async def pin(self) -> None:
        """pin this message (sets m.room.pinned_events state)."""
        try:
            state = await self._client._http.request(
                "GET", f"rooms/{self.room.id}/state/m.room.pinned_events"
            )
            pinned: list = state.get("pinned", [])
        except Exception:
            pinned = []
        if self.id not in pinned:
            pinned.append(self.id)
        await self._client._http.request(
            "PUT",
            f"rooms/{self.room.id}/state/m.room.pinned_events",
            {"pinned": pinned},
        )


    @property
    def clean_content(self) -> str:
        """content with matrix reply fallback quote stripped."""
        lines = self.content.splitlines()
        filtered = [l for l in lines if not l.startswith("> ")]
        return "\n".join(filtered).strip()

    @property
    def is_reply(self) -> bool:
        return self.reference is not None

    @property
    def is_deleted(self) -> bool:
        return self._deleted

    @property
    def jump_url(self) -> str:
        """matrix.to deep-link to this specific event."""
        return f"https://matrix.to/#/{self.room.id}/{self.id}"


    def __repr__(self) -> str:
        return (
            f"<Message id={self.id!r} author={self.author.id!r} "
            f"room={self.room.id!r}>"
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Message) and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
