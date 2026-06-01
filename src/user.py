from __future__ import annotations
from typing import TYPE_CHECKING, Optional, List

if TYPE_CHECKING:
    from .client import MatrixClient
    from .room import Room
    from .message import Message


class User:
    """
    represents a matrix user.

    attributes
    ----------
    id : str
        full matrix user id, e.g. ``@alice:matrix.org``
    display_name : str or none
        human-readable display name.
    avatar_url : str or none
        ``mxc://`` uri of the user's avatar.
    """

    __slots__ = ("_client", "id", "display_name", "avatar_url", "_raw")

    def __init__(
        self,
        client: "MatrixClient",
        user_id: str,
        *,
        display_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ):
        self._client = client
        self.id = user_id
        self.display_name = display_name
        self.avatar_url = avatar_url
        self._raw: dict = {}

    @property
    def name(self) -> str:
        """display name if set, otherwise the localpart of the user id."""
        if self.display_name:
            return self.display_name
        return self.id.split(":")[0].lstrip("@")

    @property
    def mention(self) -> str:
        """returns a matrix-style html mention pill."""
        return f'<a href="https://matrix.to/#/{self.id}">{self.name}</a>'

    @property
    def mention_text(self) -> str:
        """plain-text mention fallback."""
        return f"@{self.name}"

    @property
    def is_bot(self) -> bool:
        """heuristic: true if 'bot' appears in the localpart."""
        return "bot" in self.id.split(":")[0].lower()

    async def fetch(self) -> "User":
        """fetch and update profile data from the homeserver."""
        data = await self._client._http.get_profile(self.id)
        self.display_name = data.get("displayname") or self.display_name
        self.avatar_url   = data.get("avatar_url")  or self.avatar_url
        self._raw = data
        return self

    async def send(self, content: str, **kwargs) -> "Message":
        """
        open a dm with this user and send a message.

        parameters
        ----------
        content : str
            the message text to send.
        **kwargs
            extra keyword arguments forwarded to :meth:`room.send`.

        returns
        -------
        message
            the sent message object.

        example
        -------
        ::

            await user.send("hey! check this out.")
        """
        dm = await self._client.create_dm(self.id)
        return await dm.send(content, **kwargs)

    async def create_dm(self) -> "Room":
        """
        create or fetch an existing dm room with this user.

        returns
        -------
        room
            the dm room.

        example
        -------
        ::

            dm = await user.create_dm()
            await dm.send("hello!")
        """
        return await self._client.create_dm(self.id)

    def __repr__(self) -> str:
        return f"<User id={self.id!r} name={self.name!r}>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, User) and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)


class Member(User):
    """
    a :class:`user` within the context of a specific room.

    extends :class:`user` with room-scoped state: power level,
    membership status, and room-specific display name override.

    attributes
    ----------
    room : room
        the room this member belongs to.
    power_level : int
        current power level (0 = user, 50 = moderator, 100 = admin).
    membership : str
        one of ``"join"``, ``"invite"``, ``"leave"``, ``"ban"``.
    """

    __slots__ = ("room", "power_level", "membership")

    def __init__(
        self,
        client: "MatrixClient",
        user_id: str,
        room: "Room",
        *,
        display_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        power_level: int = 0,
        membership: str = "join",
    ):
        super().__init__(client, user_id,
                         display_name=display_name, avatar_url=avatar_url)
        self.room = room
        self.power_level = power_level
        self.membership  = membership

    @property
    def is_admin(self) -> bool:
        """true if power level >= 100."""
        return self.power_level >= 100

    @property
    def is_moderator(self) -> bool:
        """true if power level >= 50."""
        return self.power_level >= 50

    @property
    def is_banned(self) -> bool:
        """true if membership is ``"ban"``."""
        return self.membership == "ban"

    async def kick(self, *, reason: str = "") -> None:
        """
        kick this member from the room.

        parameters
        ----------
        reason : str, optional
            human-readable reason shown in the room timeline.

        example
        -------
        ::

            await member.kick(reason="spam")
        """
        await self._client._http.kick_user(self.room.id, self.id, reason)

    async def ban(self, *, reason: str = "") -> None:
        """
        ban this member from the room.

        parameters
        ----------
        reason : str, optional
            human-readable reason.

        example
        -------
        ::

            await member.ban(reason="repeated violations")
        """
        await self._client._http.ban_user(self.room.id, self.id, reason)
        self.membership = "ban"

    async def unban(self) -> None:
        """
        unban this member.

        example
        -------
        ::

            await member.unban()
        """
        await self._client._http.unban_user(self.room.id, self.id)
        self.membership = "leave"

    async def set_power_level(self, level: int) -> None:
        """
        set the power level for this member in the room.

        parameters
        ----------
        level : int
            new power level. common values: ``0`` (user),
            ``50`` (moderator), ``100`` (admin).

        example
        -------
        ::

            await member.set_power_level(50)
        """
        await self._client._http.set_power_level(self.room.id, self.id, level)
        self.power_level = level

    async def promote(self) -> None:
        """promote to moderator (power level 50)."""
        await self.set_power_level(50)

    async def demote(self) -> None:
        """demote to regular user (power level 0)."""
        await self.set_power_level(0)

    def __repr__(self) -> str:
        return (
            f"<Member id={self.id!r} name={self.name!r} "
            f"room={self.room.id!r} power={self.power_level}>"
        )
