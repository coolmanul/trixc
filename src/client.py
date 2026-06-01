from __future__ import annotations
import asyncio
import json
import logging
import os
import time
from typing import Callable, Dict, List, Optional


from .http import HTTPClient
from .user import User, Member
from .room import Room, DMRoom
from .message import Message, Attachment
from .enums import EventType


log = logging.getLogger("trixc.client")


SYNC_TOKEN_FILE = ".trixc_sync_token"


class MatrixClient:
    def __init__(self, homeserver: str, **options):
        self.homeserver = homeserver
        self._http = HTTPClient(homeserver)
        self._listeners: Dict[str, List[Callable]] = {}
        self._rooms: Dict[str, Room] = {}
        self._users: Dict[str, User] = {}
        self._dm_rooms: Dict[str, DMRoom] = {}
        self._next_batch: Optional[str] = None
        self.user: Optional[User] = None
        self._closed = False
        self._ready = asyncio.Event()
        self._sync_timeout: int = options.get("sync_timeout", 30000)
        self._start_ts: int = int(time.time() * 1000)
        self._seen_events: set[str] = set()


    async def login(self, username: str, password: str) -> None:
        data = await self._http.login_password(username, password)
        self.user = User(self, data["user_id"])
        await self.user.fetch()
        log.info("Logged in as %s", self.user.id)

    async def login_with_token(self, user_id: str, access_token: str) -> None:
        await self._http.login_token(access_token)
        self.user = User(self, user_id)
        await self.user.fetch()
        log.info("Logged in as %s (token)", self.user.id)


    def _load_sync_token(self) -> None:
        if os.path.exists(SYNC_TOKEN_FILE):
            try:
                with open(SYNC_TOKEN_FILE, "r") as f:
                    data = json.load(f)
                self._next_batch = data.get("next_batch")
                log.info("Resuming sync from saved token: %s", self._next_batch)
            except Exception as e:
                log.warning("Could not load sync token: %s", e)
                self._next_batch = None

    def _save_sync_token(self) -> None:
        try:
            with open(SYNC_TOKEN_FILE, "w") as f:
                json.dump({"next_batch": self._next_batch}, f)
        except Exception as e:
            log.warning("Could not save sync token: %s", e)


    async def _sync_forever(self) -> None:
        self._load_sync_token()
        log.info("Starting sync loop...")

        log.info("Loading rooms via full_state sync...")
        try:
            room_data = await self._http.sync(since=None, timeout=0)
            await self._process_sync(room_data)
            log.info("Rooms loaded: %d", len(self._rooms))
            if self._next_batch is None:
                self._next_batch = room_data.get("next_batch")
                self._save_sync_token()
        except Exception as e:
            log.error("Room preload failed: %s", e)

        self._ready.set()
        await self._dispatch("ready")

        while not self._closed:
            try:
                data = await self._http.sync(
                    since=self._next_batch,
                    timeout=self._sync_timeout,
                )
                self._next_batch = data.get("next_batch")
                self._save_sync_token()
                await self._process_sync(data)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Sync error: %s", e, exc_info=True)
                await asyncio.sleep(5)

    async def _process_sync(self, data: dict) -> None:
        rooms_data = data.get("rooms", {})

        for room_id, room_data in rooms_data.get("join", {}).items():
            room = self._get_or_create_room(room_id, room_data)
            timeline = room_data.get("timeline", {}).get("events", [])
            for event in timeline:
                await self._handle_room_event(room, event)

        for room_id, invite_data in rooms_data.get("invite", {}).items():
            await self._dispatch("room_invite", room_id, invite_data)

    def _get_or_create_room(self, room_id: str, room_data: dict) -> Room:
        if room_id not in self._rooms:
            name = None
            topic = None
            for ev in room_data.get("state", {}).get("events", []):
                if ev["type"] == "m.room.name":
                    name = ev["content"].get("name")
                elif ev["type"] == "m.room.topic":
                    topic = ev["content"].get("topic")
            self._rooms[room_id] = Room(self, room_id, name=name, topic=topic)

        room = self._rooms[room_id]
        state_events = room_data.get("state", {}).get("events", [])

        for ev in state_events:
            if ev["type"] == "m.room.power_levels":
                content = ev.get("content", {})
                room._power_levels = dict(content.get("users", {}))
                room._power_levels["users_default"] = content.get("users_default", 0)
                break

        for ev in state_events:
            if ev["type"] == "m.room.member":
                membership = ev.get("content", {}).get("membership")
                if membership == "join":
                    member = self._parse_member(ev, room)
                    room.members[member.id] = member

        return room

    async def _handle_room_event(self, room: Room, event: dict) -> None:
        event_id = event.get("event_id", "")
        if event_id:
            if event_id in self._seen_events:
                return
            self._seen_events.add(event_id)
            if len(self._seen_events) > 20_000:
                discard = list(self._seen_events)[:10_000]
                for eid in discard:
                    self._seen_events.discard(eid)

        event_ts = event.get("origin_server_ts", 0)
        if event_ts and event_ts < self._start_ts:
            return

        etype = event.get("type")

        if etype == EventType.MESSAGE:
            relates = event.get("content", {}).get("m.relates_to", {})
            if relates.get("rel_type") == "m.replace":
                msg = self._parse_message(event, room)
                await self._dispatch("message_edit", msg)
                return

            msg = self._parse_message(event, room)
            room._message_cache[msg.id] = msg
            await self._dispatch("message", msg)

        elif etype == EventType.REACTION:
            await self._dispatch("reaction_add", event, room)

        elif etype == EventType.REDACTION:
            await self._dispatch("message_delete", event["redacts"], room)

        elif etype == "m.room.power_levels":
            content = event.get("content", {})
            room._power_levels = dict(content.get("users", {}))
            room._power_levels["users_default"] = content.get("users_default", 0)
            for uid, member in room.members.items():
                member.power_level = room._power_levels.get(
                    uid, room._power_levels.get("users_default", 0)
                )

        elif etype == EventType.MEMBER:
            membership = event["content"].get("membership")
            member = self._parse_member(event, room)
            if membership in ("leave", "ban"):
                room.members.pop(member.id, None)
            else:
                room.members[member.id] = member
            event_map = {
                "join":   "member_join",
                "leave":  "member_leave",
                "invite": "member_invite",
                "ban":    "member_ban",
            }
            if membership in event_map:
                await self._dispatch(event_map[membership], member)

        elif etype == EventType.ROOM_NAME:
            room.name = event["content"].get("name")
            await self._dispatch("room_update", room)

        elif etype == EventType.ROOM_TOPIC:
            room.topic = event["content"].get("topic")
            await self._dispatch("room_update", room)

    def _get_or_create_user(self, user_id: str) -> User:
        if user_id not in self._users:
            self._users[user_id] = User(self, user_id)
        return self._users[user_id]

    def _parse_message(self, event: dict, room: Room) -> Message:
        from datetime import datetime

        content = event.get("content", {})
        sender_id = event.get("sender", "")
        author = self._get_or_create_user(sender_id)

        if not author.display_name:
            member = room.members.get(sender_id)
            if member and member.display_name:
                author.display_name = member.display_name

        if not author.display_name:
            author.display_name = sender_id.split(":")[0].lstrip("@")

        attachments = []
        if content.get("msgtype") in ("m.image", "m.file", "m.audio", "m.video"):
            url = content.get("url", "")
            info = content.get("info", {})
            attachments.append(Attachment(
                url=url,
                filename=content.get("body", ""),
                content_type=info.get("mimetype", ""),
                size=info.get("size", 0),
            ))

        reference = None
        relates = content.get("m.relates_to", {})
        if "m.in_reply_to" in relates:
            ref_id = relates["m.in_reply_to"]["event_id"]
            reference = room._message_cache.get(ref_id)

        ts = event.get("origin_server_ts", 0)
        created_at = datetime.utcfromtimestamp(ts / 1000) if ts else datetime.utcnow()

        return Message(
            client=self,
            event_id=event.get("event_id", ""),
            room=room,
            author=author,
            content=content.get("body", ""),
            html_content=content.get("formatted_body"),
            created_at=created_at,
            reference=reference,
            attachments=attachments,
            msg_type=content.get("msgtype", "m.text"),
        )

    def _parse_member(self, event: dict, room: Room) -> Member:
        user_id = event.get("state_key") or event.get("sender", "")
        content = event.get("content", {})

        user = self._get_or_create_user(user_id)
        dn = content.get("displayname")
        if dn and not user.display_name:
            user.display_name = dn

        power_level = room._power_levels.get(
            user_id,
            room._power_levels.get("users_default", 0)
        )
        return Member(
            client=self,
            user_id=user_id,
            room=room,
            display_name=dn,
            avatar_url=content.get("avatar_url"),
            membership=content.get("membership", "join"),
            power_level=power_level,
        )

    def add_listener(self, event: str, callback: Callable) -> None:
        self._listeners.setdefault(event, []).append(callback)

    def remove_listener(self, event: str, callback: Callable) -> None:
        if event in self._listeners:
            self._listeners[event].remove(callback)

    async def _dispatch(self, event: str, *args, **kwargs) -> None:
        for cb in self._listeners.get(event, []):
            try:
                await cb(*args, **kwargs)
            except Exception as e:
                log.error("Error in %s listener: %s", event, e, exc_info=True)
                for eh in self._listeners.get("error", []):
                    await eh(e, event)

    async def create_dm(self, user_id: str) -> DMRoom:
        if user_id in self._dm_rooms:
            return self._dm_rooms[user_id]
        room_id = await self._http.create_room(invite=[user_id], is_direct=True)
        user = self._get_or_create_user(user_id)
        dm = DMRoom(self, room_id, recipient=user)
        self._rooms[room_id] = dm
        self._dm_rooms[user_id] = dm
        return dm

    def get_room(self, room_id: str) -> Optional[Room]:
        return self._rooms.get(room_id)

    async def fetch_room(self, room_id: str) -> Room:
        if room_id in self._rooms:
            return self._rooms[room_id]
        room = Room(self, room_id)
        await room.fetch_members()
        self._rooms[room_id] = room
        return room

    async def join_room(self, room_id_or_alias: str) -> Room:
        room_id = await self._http.join_room(room_id_or_alias)
        return self._get_or_create_room(room_id, {})

    async def close(self) -> None:
        self._closed = True
        await self._http.close()
        log.info("Client closed.")