from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DispatchTypes(Enum):
    """
    Types (t) of dispatch websocket messages.

    READY - connection between bot and discord websockets established.
    TYPING_START - user started typing in channel
    MESSAGE_CREATE - user send a message to channel
    """

    READY = "READY"
    TYPING_START = "TYPING_START"
    MESSAGE_CREATE = "MESSAGE_CREATE"


class DiscordTextTokenType(Enum):
    """
    Types of tokens that can be found in the text of a Discord comment.
    """

    PLAIN = 1
    USER = 2


class DiscordTextToken(BaseModel):
    """
    A token in the text of Discord comment.
    """

    raw: str
    token_type: DiscordTextTokenType
    token: str
    label: Optional[str] = None


class BotPrompt(BaseModel):
    prefix: str
    postfix: str
