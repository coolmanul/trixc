from __future__ import annotations
import asyncio
import json
import logging
from typing import Any, Optional
import aiohttp


from .errors import (
    HTTPException, Forbidden, NotFound,
    RateLimited, LoginFailure
)


log = logging.getLogger("trixc.http")


class HTTPClient:
    BASE = "_matrix/client/v3"

    def __init__(self, homeserver: str, *, session: Optional[aiohttp.ClientSession] = None):
        self.homeserver = homeserver.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = session
        self.access_token: Optional[str] = None
        self._device_id: Optional[str] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _url(self, path: str) -> str:
        return f"{self.homeserver}/{self.BASE}/{path.lstrip('/')}"

    @property
    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.access_token:
            h["Authorization"] = f"Bearer {self.access_token}"
        return h

    async def request(
        self, method: str, path: str,
        payload: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Any:
        session = await self._get_session()
        url = self._url(path)

        for attempt in range(5):
            async with session.request(
                method, url,
                headers=self._headers,
                json=payload,
                params=params,
            ) as resp:
                data = await resp.json(content_type=None)

                if resp.status == 200:
                    return data
                if resp.status == 429:
                    retry_after = data.get("retry_after_ms", 1000) / 1000
                    log.warning("Rate limited. Retrying in %.1fs", retry_after)
                    await asyncio.sleep(retry_after)
                    continue
                if resp.status == 403:
                    raise Forbidden(data.get("error", ""))
                if resp.status == 404:
                    raise NotFound(data.get("error", ""))

                raise HTTPException(resp.status, data.get("error", str(data)))

        raise RateLimited(0)

    async def login_password(self, user_id: str, password: str) -> dict:
        data = await self.request("POST", "login", {
            "type": "m.login.password",
            "identifier": {"type": "m.id.user", "user": user_id},
            "password": password,
        })
        if "access_token" not in data:
            raise LoginFailure("Login failed: no access_token in response")
        self.access_token = data["access_token"]
        self._device_id = data.get("device_id")
        return data

    async def login_token(self, access_token: str) -> None:
        self.access_token = access_token

    async def sync(self, since: Optional[str] = None, timeout: int = 30000) -> dict:
        params: dict = {"timeout": timeout}
        if since:
            params["since"] = since
        else:

            params["full_state"] = "true"
            params["timeout"] = 0
        return await self.request("GET", "sync", params=params)

    async def send_message(
        self, room_id: str, body: str,
        html_body: Optional[str] = None,
        reply_to: Optional[str] = None,
        notice: bool = False,
    ) -> str:
        import time, uuid
        txn_id = f"trixc-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        msg_type = "m.notice" if notice else "m.text"

        content: dict = {"msgtype": msg_type, "body": body}
        if html_body:
            content["format"] = "org.matrix.custom.html"
            content["formatted_body"] = html_body
        if reply_to:
            content["m.relates_to"] = {
                "m.in_reply_to": {"event_id": reply_to}
            }

        data = await self.request(
            "PUT",
            f"rooms/{room_id}/send/m.room.message/{txn_id}",
            content,
        )
        return data["event_id"]

    async def send_reaction(self, room_id: str, event_id: str, emoji: str) -> str:
        import time, uuid
        txn_id = f"reaction-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        data = await self.request(
            "PUT",
            f"rooms/{room_id}/send/m.reaction/{txn_id}",
            {"m.relates_to": {"rel_type": "m.annotation", "event_id": event_id, "key": emoji}},
        )
        return data["event_id"]

    async def remove_reaction(self, room_id: str, event_id: str, emoji: str) -> None:
        pass

    async def edit_message(self, room_id: str, event_id: str, new_body: str) -> str:
        import time, uuid
        txn_id = f"edit-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        data = await self.request(
            "PUT",
            f"rooms/{room_id}/send/m.room.message/{txn_id}",
            {
                "msgtype": "m.text",
                "body": f"* {new_body}",
                "m.new_content": {"msgtype": "m.text", "body": new_body},
                "m.relates_to": {"rel_type": "m.replace", "event_id": event_id},
            },
        )
        return data["event_id"]

    async def redact_event(self, room_id: str, event_id: str, reason: str = "") -> str:
        import time, uuid
        txn_id = f"redact-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        data = await self.request(
            "PUT",
            f"rooms/{room_id}/redact/{event_id}/{txn_id}",
            {"reason": reason},
        )
        return data["event_id"]

    async def send_typing(self, room_id: str, user_id: str, typing: bool, timeout: int) -> None:
        await self.request(
            "PUT",
            f"rooms/{room_id}/typing/{user_id}",
            {"typing": typing, "timeout": timeout},
        )

    async def join_room(self, room_id_or_alias: str) -> str:
        data = await self.request("POST", f"join/{room_id_or_alias}")
        return data["room_id"]

    async def leave_room(self, room_id: str) -> None:
        await self.request("POST", f"rooms/{room_id}/leave")

    async def invite_user(self, room_id: str, user_id: str) -> None:
        await self.request("POST", f"rooms/{room_id}/invite", {"user_id": user_id})

    async def kick_user(self, room_id: str, user_id: str, reason: Optional[str] = None) -> None:
        await self.request("POST", f"rooms/{room_id}/kick",
                           {"user_id": user_id, "reason": reason or ""})

    async def ban_user(self, room_id: str, user_id: str, reason: Optional[str] = None) -> None:
        await self.request("POST", f"rooms/{room_id}/ban",
                           {"user_id": user_id, "reason": reason or ""})

    async def unban_user(self, room_id: str, user_id: str) -> None:
        await self.request("POST", f"rooms/{room_id}/unban", {"user_id": user_id})

    async def get_profile(self, user_id: str) -> dict:
        return await self.request("GET", f"profile/{user_id}")

    async def set_display_name(self, user_id: str, display_name: str) -> None:
        await self.request("PUT", f"profile/{user_id}/displayname",
                           {"displayname": display_name})

    async def get_messages(self, room_id: str, limit: int = 50) -> list:
        data = await self.request(
            "GET", f"rooms/{room_id}/messages",
            params={"dir": "b", "limit": limit},
        )
        return data.get("chunk", [])

    async def get_event(self, room_id: str, event_id: str) -> dict:
        return await self.request("GET", f"rooms/{room_id}/event/{event_id}")

    async def get_members(self, room_id: str) -> list:
        data = await self.request("GET", f"rooms/{room_id}/members")
        return data.get("chunk", [])

    async def create_room(self, name: str = "", topic: str = "",
                          invite: list = None, is_direct: bool = False) -> str:
        payload: dict = {"is_direct": is_direct}
        if name:
            payload["name"] = name
        if topic:
            payload["topic"] = topic
        if invite:
            payload["invite"] = invite
        data = await self.request("POST", "createRoom", payload)
        return data["room_id"]

    async def set_room_name(self, room_id: str, name: str) -> None:
        await self.request("PUT", f"rooms/{room_id}/state/m.room.name",
                           {"name": name})

    async def set_room_topic(self, room_id: str, topic: str) -> None:
        await self.request("PUT", f"rooms/{room_id}/state/m.room.topic",
                           {"topic": topic})

    async def set_power_level(self, room_id: str, user_id: str, level: int) -> None:
        current = await self.request("GET", f"rooms/{room_id}/state/m.room.power_levels")
        current.setdefault("users", {})[user_id] = level
        await self.request("PUT", f"rooms/{room_id}/state/m.room.power_levels", current)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
