import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RequestMethods(Enum):
    GET = "get"
    POST = "post"
    PUT = "put"
    DELETE = "delete"


class ConfigLeaderboard(BaseModel):
    leaderboard_id: uuid.UUID
    short_name: str
    thread_ids: List[int] = Field(default_factory=list)


class Config(BaseModel):
    type: str
    discord_server_id: int
    discord_roles: List[str] = Field(default_factory=list)
    leaderboards: List[ConfigLeaderboard] = Field(default_factory=list)


class ResourceConfig(BaseModel):
    id: uuid.UUID
    resource_data: Config


class UserAddress(BaseModel):
    entity_id: Optional[uuid.UUID] = None
    address: str
    blockchain: str
    description: str


class User(BaseModel):
    discord_id: int
    addresses: List[UserAddress] = Field(default_factory=list)


class LeaderboardInfo(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    users_count: int
    last_updated_at: datetime


class Score(BaseModel):
    address: str
    rank: int
    score: int
    points_data: Dict[str, Any]
