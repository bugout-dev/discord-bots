import asyncio
import logging
import re
import uuid
from typing import Any, List, Optional, Tuple

import aiohttp

from . import data
from .settings import MOONSTREAM_ENGINE_API_URL

logger = logging.getLogger(__name__)

QUERY_REGEX = re.compile("[\[\]@#$%^&?;`/]")


class QueryNotValid(Exception):
    """
    Raised when query validation not passed.
    """


def query_input_validation(query_input: str) -> str:
    """
    Sanitize provided input for query.
    """
    if QUERY_REGEX.search(query_input) != None:
        raise QueryNotValid("Query contains restricted symbols")

    return query_input


async def caller_get(url: str, timeout: int = 5) -> Optional[Any]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url=url, timeout=timeout) as response:
                response.raise_for_status()
                json_response = await response.json()
                return json_response
    except Exception as e:
        logger.error(str(e))
        return None


async def get_leaderboard_info(l_id: uuid.UUID) -> Optional[data.LeaderboardInfo]:
    l_info: Optional[data.LeaderboardInfo] = None
    response = await caller_get(
        url=f"{MOONSTREAM_ENGINE_API_URL}/leaderboard/info?leaderboard_id={str(l_id)}"
    )
    if response is not None:
        l_info = data.LeaderboardInfo(**response)
    return l_info


async def get_scores(l_id: uuid.UUID) -> Optional[List[data.Score]]:
    l_scores: Optional[List[data.Score]] = None
    response = await caller_get(
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
    response = await caller_get(
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
