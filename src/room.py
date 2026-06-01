from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator, Optional

from .message import Message
from .embed import Embed

if TYPE_CHECKING:
    from .client import MatrixClient
    from .user import User, Member

log = logging.getLogger("trixc.room")


class Room:
    """represents a matrix room."""

    def __init__(self, client, room_id, *, name=None, topic=None):
        self._client = client
        self.id = room_id
        self.name = name
        self.topic = topic
        self.members: dict[str, "Member"] = {}
        self._message_cache: dict[str, Message] = {}
        self._prev_batch: Optional[str] = None
        self._power_levels: dict = {"users_default": 0}

    async def send(
        self,
        content: str = "",
        *,
        embed: Optional[Embed] = None,
        reply_to: Optional[str] = None,
        notice: bool = False,
        html: Optional[str] = None,
    ) -> Message:
        if embed is not None:
            html_body = embed.to_html()
            plain = content or embed.to_plain()
        else:
            html_body = html
            plain = content

        event_id = await self._client._http.send_message(
            self.id,
            plain,
            html_body=html_body,
            reply_to=reply_to,
            notice=notice,
        )

        author = self._client.user
        msg = Message(
            client=self._client,
            event_id=event_id,
            room=self,
            author=author,
            content=plain,
            html_content=html_body,
        )
        self._message_cache[event_id] = msg
        return msg

    async def fetch_message(self, event_id: str) -> Message:
        """fetch a single message by event id."""
        if event_id in self._message_cache:
            return self._message_cache[event_id]
        data = await self._client._http.get_event(self.id, event_id)
        return self._client._parse_message(data, self)

    async def history(self, limit: int = 50) -> AsyncIterator[Message]:
        token = self._prev_batch
        fetched = 0
        while fetched < limit:
            batch = limit - fetched
            data = await self._client._http.get_messages(
                self.id,
                limit=min(batch, 100),
                from_token=token,
            )
            events = data.get("chunk", [])
            if not events:
                break

            token = data.get("end")

            for event in events:
                if event.get("type") == "m.room.message":
                    msg = self._client._parse_message(event, self)
                    yield msg
                    fetched += 1
                    if fetched >= limit:
                        break

            if not token:
                break

    async def purge(self, limit: int = 10) -> int:
        """delete the last n messages sent by the bot. returns count deleted."""
        deleted = 0
        async for msg in self.history(limit=limit * 5):
            if msg.author.id == self._client.user.id:
                try:
                    await msg.delete()
                    deleted += 1
                except Exception as e:
                    log.error("Failed to delete message %s: %s", msg.id, e)
            if deleted >= limit:
                break
        return deleted

    async def fetch_members(self) -> list["Member"]:
        """fetch and cache all room members."""
        events = await self._client._http.get_members(self.id)
        for event in events:
            member = self._client._parse_member(event, self)
            self.members[member.id] = member
        return list(self.members.values())

    async def get_member(self, user_id: str) -> Optional["Member"]:
        """get a member by user id, fetching if not cached."""
        if user_id in self.members:
            return self.members[user_id]
        await self.fetch_members()
        return self.members.get(user_id)

    async def get_member_power_level(self, user_id: str) -> int:
        """get a member power level in this room."""
        member = await self.get_member(user_id)
        if member is not None:
            return member.power_level

        try:
            data = await self._client._http.request(
                "GET",
                f"rooms/{self.id}/state/m.room.power_levels",
            )
            users = data.get("users", {})
            return int(users.get(user_id, data.get("users_default", 0)))
        except Exception:
            return 0

    async def kick(self, user_id: str, reason: str = "") -> None:
        """kick a user from this room. requires power level >= 50."""
        await self._client._http.kick_user(self.id, user_id, reason)
        self.members.pop(user_id, None)
        log.info("Kicked %s from %s (reason: %s)", user_id, self.id, reason or "none")

    async def ban(self, user_id: str, reason: str = "") -> None:
        """ban a user from this room. requires power level >= 50."""
        await self._client._http.ban_user(self.id, user_id, reason)
        self.members.pop(user_id, None)
        log.info("Banned %s from %s (reason: %s)", user_id, self.id, reason or "none")

    async def unban(self, user_id: str) -> None:
        """unban a user from this room. requires power level >= 50."""
        await self._client._http.unban_user(self.id, user_id)
        log.info("Unbanned %s from %s", user_id, self.id)

    async def set_power_level(self, user_id: str, level: int) -> None:
        """set a user's power level in this room. requires power level >= 100."""
        await self._client._http.set_power_level(self.id, user_id, level)
        self._power_levels[user_id] = level
        member = self.members.get(user_id)
        if member:
            member.power_level = level
        log.info("Set power level of %s to %d in %s", user_id, level, self.id)

    async def set_name(self, name: str) -> None:
        """set the room name."""
        await self._client._http.set_room_name(self.id, name)
        self.name = name

    async def set_topic(self, topic: str) -> None:
        """set the room topic."""
        await self._client._http.set_room_topic(self.id, topic)
        self.topic = topic

    async def invite(self, user_id: str) -> None:
        """invite a user to this room."""
        await self._client._http.invite_user(self.id, user_id)

    async def leave(self) -> None:
        """leave this room."""
        await self._client._http.leave_room(self.id)

    @asynccontextmanager
    async def typing(self, *, duration: int = 4000):
        if not self._client.user:
            yield
            return
        try:
            await self._client._http.send_typing(self.id, self._client.user.id, True, duration)
            yield
        finally:
            await self._client._http.send_typing(self.id, self._client.user.id, False, 0)

    def __repr__(self) -> str:
        return f"<Room id={self.id!r} name={self.name!r}>"


class DMRoom(Room):
    """a direct message room with a single recipient."""

    def __init__(self, client: "MatrixClient", room_id: str, *, recipient: "User"):
        super().__init__(client, room_id, name=f"DM with {recipient.name}")
        self.recipient = recipient

    def __repr__(self) -> str:
        return f"<DMRoom id={self.id!r} recipient={self.recipient.id!r}>"