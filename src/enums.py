from __future__ import annotations


class EventType:
    """matrix event type strings."""
    MESSAGE      = "m.room.message"
    REACTION     = "m.reaction"
    REDACTION    = "m.room.redaction"
    MEMBER       = "m.room.member"
    ROOM_NAME    = "m.room.name"
    ROOM_TOPIC   = "m.room.topic"
    ROOM_AVATAR  = "m.room.avatar"
    ROOM_CREATE  = "m.room.create"
    POWER_LEVELS = "m.room.power_levels"
    ENCRYPTION   = "m.room.encryption"
    STICKER      = "m.sticker"
    CALL_INVITE  = "m.call.invite"
    TYPING       = "m.typing"
    RECEIPT      = "m.receipt"
    PRESENCE     = "m.presence"


class MessageType:
    """m.room.message msgtype values."""
    TEXT    = "m.text"
    NOTICE  = "m.notice"
    EMOTE   = "m.emote"
    IMAGE   = "m.image"
    FILE    = "m.file"
    AUDIO   = "m.audio"
    VIDEO   = "m.video"
    LOCATION = "m.location"


class RoomType:
    """known matrix room types."""
    DEFAULT = ""
    DM      = "m.dm"
    SPACE   = "m.space"


class Membership:
    """room membership states."""
    JOIN    = "join"
    INVITE  = "invite"
    LEAVE   = "leave"
    BAN     = "ban"
    KNOCK   = "knock"


class PowerLevel:
    """default matrix power level constants."""
    USER      = 0
    MODERATOR = 50
    ADMIN     = 100


class Presence:
    """user presence states."""
    ONLINE      = "online"
    OFFLINE     = "offline"
    UNAVAILABLE = "unavailable"