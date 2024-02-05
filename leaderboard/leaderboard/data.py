import uuid
from datetime import datetime
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ConfigLeaderboard(BaseModel):
    leaderboard_id: uuid.UUID
    short_name: str
    thread_ids: List[int] = Field(default_factory=list)


class Config(BaseModel):
    type: str
    discord_server_id: int
    discord_roles: List[str] = Field(default_factory=list)
    leaderboards: List[ConfigLeaderboard] = Field(default_factory=list)


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
