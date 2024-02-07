import asyncio
import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp
from bugout.data import BugoutJournalEntity, BugoutResource
from discord.guild import Guild
from discord.member import Member
from discord.user import User

from . import data
from .settings import (
    BUGOUT_BROOD_URL,
    BUGOUT_SPIRE_URL,
    COLORS,
    LEADERBOARD_DISCORD_BOT_USERS_JOURNAL_ID,
    MOONSTREAM_ENGINE_API_URL,
    MOONSTREAN_DISCORD_BOT_ACCESS_TOKEN,
)

logger = logging.getLogger(__name__)

QUERY_REGEX = re.compile("[\[\]@#$%^&?;`/]")


class QueryNotValid(Exception):
    """
    Raised when query validation not passed.
    """


def prepare_log_message(
    action: str,
    action_type: str,
    user: Optional[Union[User, Member]] = None,
    guild: Optional[Guild] = None,
    channel: Optional[Any] = None,
) -> str:
    msg = f"{COLORS.GREEN}[{action_type}]{COLORS.RESET} {COLORS.BLUE}{action}{COLORS.RESET}"
    if user is not None:
        msg += f" User: {COLORS.BLUE}{f'{user} - {user.id}' if user is not None else user}{COLORS.RESET}"
    msg += f" Guild: {COLORS.BLUE}{f'{guild} - {guild.id}' if guild is not None else guild}{COLORS.RESET} Channel: {COLORS.BLUE}{f'{channel} - {channel.id}' if channel is not None else channel}{COLORS.RESET}"

    return msg


def query_input_validation(query_input: str) -> str:
    """
    Sanitize provided input for query.
    """
    if QUERY_REGEX.search(query_input) != None:
        raise QueryNotValid("Query contains restricted symbols")

    return query_input


async def caller(
    url: str,
    method: data.RequestMethods = data.RequestMethods.GET,
    request_data: Optional[Dict[str, Any]] = None,
    is_auth: bool = False,
    timeout: int = 5,
) -> Optional[Any]:
    try:
        async with aiohttp.ClientSession() as session:
            request_method = getattr(session, method.value, session.get)
            request_kwargs: Dict[str, Any] = {"timeout": timeout, "headers": {}}
            if method == data.RequestMethods.POST or method == data.RequestMethods.PUT:
                request_kwargs["json"] = request_data
                request_kwargs["headers"]["Content-Type"] = "application/json"
            if is_auth is True:
                request_kwargs["headers"][
                    "Authorization"
                ] = f"Bearer {MOONSTREAN_DISCORD_BOT_ACCESS_TOKEN}"
            async with request_method(url, **request_kwargs) as response:
                response.raise_for_status()
                json_response = await response.json()
                return json_response
    except Exception as e:
        logger.error(str(e))
        return None


async def get_leaderboard_info(l_id: uuid.UUID) -> Optional[data.LeaderboardInfo]:
    l_info: Optional[data.LeaderboardInfo] = None
    response = await caller(
        url=f"{MOONSTREAM_ENGINE_API_URL}/leaderboard/info?leaderboard_id={str(l_id)}"
    )
    if response is not None:
        logger.debug(f"Received info for leaderboard with ID: {response.get('id')}")
        l_info = data.LeaderboardInfo(**response)
    return l_info


async def get_scores(l_id: uuid.UUID) -> Optional[List[data.Score]]:
    l_scores: Optional[List[data.Score]] = None
    response = await caller(
        url=f"{MOONSTREAM_ENGINE_API_URL}/leaderboard/?leaderboard_id={str(l_id)}&limit=10&offset=0",
        timeout=30,
    )
    if response is not None:
        l_scores = [data.Score(**s) for s in response]
    return l_scores


async def process_leaderboard_info_with_scores(
    l_id: str,
) -> Tuple[Optional[data.LeaderboardInfo], Optional[List[data.Score]]]:
    try:
        leaderboard_id = uuid.UUID(query_input_validation(l_id))
    except QueryNotValid as e:
        logger.error(e)
        return None, None
    except Exception as e:
        logger.error(e)
        return None, None

    l_info, l_scores = await asyncio.gather(
        get_leaderboard_info(leaderboard_id), get_scores(leaderboard_id)
    )

    return l_info, l_scores


async def get_position(l_id: uuid.UUID, address: str) -> Optional[data.Score]:
    l_position: Optional[data.Score] = None
    response = await caller(
        url=f"{MOONSTREAM_ENGINE_API_URL}/leaderboard/position?leaderboard_id={str(l_id)}&address={address}&normalize_addresses=False&window_size=0&limit=10&offset=0",
    )
    if response is not None:
        l_scores = [data.Score(**s) for s in response]
        if len(l_scores) == 1:
            l_position = l_scores[0]
    return l_position


async def process_leaderboard_info_with_position(
    l_id: uuid.UUID, address: str
) -> Tuple[Optional[data.LeaderboardInfo], Optional[data.Score]]:
    l_info, l_position = await asyncio.gather(
        get_leaderboard_info(l_id), get_position(l_id, address)
    )

    return l_info, l_position


async def push_user_address(
    user_id: int,
    address: str,
    description: str,
) -> Optional[BugoutJournalEntity]:
    entity: Optional[BugoutJournalEntity] = None
    response = await caller(
        url=f"{BUGOUT_SPIRE_URL}/journals/{LEADERBOARD_DISCORD_BOT_USERS_JOURNAL_ID}/entities",
        method=data.RequestMethods.POST,
        request_data={
            "address": address,
            "blockchain": "any",
            "title": f"{str(user_id)} - {address[0:5]}..{address[-3:]}",
            "required_fields": [
                {
                    "type": "user-link",
                    "discord-bot": "leaderboard",
                    "discord-user-id": user_id,
                }
            ],
            "description": description,
        },
        is_auth=True,
    )

    if response is not None:
        entity = BugoutJournalEntity(**response)

    return entity


async def remove_user_address(entity_id: uuid.UUID) -> Optional[uuid.UUID]:
    removed_entry_id: Optional[uuid.UUID] = None
    response = await caller(
        url=f"{BUGOUT_SPIRE_URL}/journals/{LEADERBOARD_DISCORD_BOT_USERS_JOURNAL_ID}/entities/{str(entity_id)}",
        method=data.RequestMethods.DELETE,
        is_auth=True,
    )

    if response is not None:
        removed_entry_id = uuid.UUID(response["id"])

    return removed_entry_id


async def push_server_config(
    resource_id: uuid.UUID, leaderboards: List[data.ConfigLeaderboard]
) -> Optional[BugoutResource]:
    resource: Optional[BugoutResource] = None
    response = await caller(
        url=f"{BUGOUT_BROOD_URL}/resources/{str(resource_id)}",
        method=data.RequestMethods.PUT,
        request_data={
            "update": {"leaderboards": [json.loads(l.json()) for l in leaderboards]},
            "drop_keys": [],
        },
        is_auth=True,
    )

    if response is not None:
        resource = BugoutResource(**response)

    return resource


class TabularData:
    def __init__(self) -> None:
        self.max_len = 30  # Mobile discord max width is 30 if thumbnail not set

        self._widths: List[int] = []
        self._columns: List[str] = []
        self._rows: List[List[str]] = []

    def set_columns(self, columns: List[str]) -> None:
        self._columns = columns

        columns_lens = [len(c) for c in columns]
        self._widths = columns_lens

    def add_row(self, row_raw: List[str]) -> None:
        row = [r for r in row_raw]
        self._rows.append(row)

    def add_scores(self, scores: List[data.Score]) -> None:
        shortcut = "..."
        rows = []
        for score in scores:
            row = [str(score.rank), str(score.address), str(score.score)]
            for i, elem in enumerate(row):
                if len(elem) > self._widths[i]:
                    self._widths[i] = len(elem)
            rows.append(row)

        available: Optional[int] = None
        if sum(self._widths) > self.max_len:
            available = self.max_len - self._widths[0] - self._widths[2] - len(shortcut)
            self._widths[1] = available + len(shortcut)

        for row in rows:
            if available is not None:
                row[1] = f"{row[1][0:available//2]}{shortcut}{row[1][-available//2:]}"
            self.add_row(row)

    def render_rst(self) -> str:
        """Renders a table in rST format.

        +----+---------------------+-----+
         rank        address        score
        +----+---------------------+-----+
          1    0x15650b...ffb56321   16
          2    0x825080...3052a123    9
        """

        sep = "+".join("-" * w for w in self._widths)
        sep = f"+{sep}+"

        to_draw = [sep]

        def get_entry(d: List[str]) -> str:
            elem = " ".join(f"{e:^{self._widths[i]}}" for i, e in enumerate(d))
            return f" {elem} "

        to_draw.append(get_entry(self._columns))
        to_draw.append(sep)

        for row in self._rows:
            to_draw.append(get_entry(row))

        return "\n".join(to_draw)
