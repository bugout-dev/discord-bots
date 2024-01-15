import uuid
from datetime import datetime
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ConfigLeaderboardThreads(BaseModel):
    leaderboard_id: uuid.UUID
    thread_id: int


class Config(BaseModel):
    leaderboard_threads: List[ConfigLeaderboardThreads] = Field(default_factory=list)


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
