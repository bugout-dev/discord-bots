import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Coroutine, Dict, List, Optional

from pydantic import BaseModel, Field

MESSAGE_LEADERBOARD_NOT_FOUND = "Leaderboard not found"
MESSAGE_POSITION_NOT_FOUND = "Leaderboard position not found"
MESSAGE_CHANNEL_NOT_FOUND = "Discord channel not found"
MESSAGE_GUILD_NOT_FOUND = "Discord guild not found"
MESSAGE_ACCESS_DENIED = "Access denied"


class RequestMethods(Enum):
    GET = "get"
    POST = "post"
    PUT = "put"
    DELETE = "delete"


class SlashCommandData(BaseModel):
    name: str
    description: str
    autocomplete_value: Optional[str] = None


class CogMap(BaseModel):
    cog: Any
    slash_command_name: str
    slash_command_description: str
    slash_command_callback: Any
    slash_command_autocompletion: Optional[Any] = None
    slash_command_autocomplete_value: Optional[str] = None


class LeaderboardInfo(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    users_count: int
    last_updated_at: Optional[datetime] = None


class Score(BaseModel):
    address: str
    rank: int
    score: int
    points_data: Dict[str, Any]


class ConfigCommands(BaseModel):
    origin: str
    renamed: str


class ConfigLeaderboard(BaseModel):
    leaderboard_id: uuid.UUID
    short_name: str
    channel_ids: List[int] = Field(default_factory=list)

    leaderboard_info: Optional[LeaderboardInfo] = None


class ConfigRole(BaseModel):
    id: int
    name: str


class Config(BaseModel):
    type: str
    discord_server_id: int
    discord_auth_roles: List[ConfigRole] = Field(default_factory=list)
    leaderboards: List[ConfigLeaderboard] = Field(default_factory=list)
    commands: List[ConfigCommands] = Field(default_factory=list)


class ResourceConfig(BaseModel):
    id: Optional[uuid.UUID] = None
    resource_data: Config


class UserIdentity(BaseModel):
    resource_id: Optional[uuid.UUID] = None
    identifier: str
    name: str
