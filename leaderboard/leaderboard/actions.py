import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple

import requests

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


def get_leaderboard_info(l_id: uuid.UUID) -> Optional[data.LeaderboardInfo]:
    try:
        response = requests.request(
            "GET",
            url=f"{MOONSTREAM_ENGINE_API_URL}/leaderboard/info?leaderboard_id={str(l_id)}",
            timeout=10,
        )
        response.raise_for_status()
    except Exception as e:
        logger.error(str(e))
        return None

    return data.LeaderboardInfo(**response.json())


def get_scores(l_id: uuid.UUID) -> Optional[List[data.Score]]:
    try:
        response = requests.request(
            "GET",
            url=f"{MOONSTREAM_ENGINE_API_URL}/leaderboard/?leaderboard_id={str(l_id)}&limit=10&offset=0",
            timeout=10,
        )
        response.raise_for_status()
    except Exception as e:
        logger.error(str(e))
        return None

    return [data.Score(**s) for s in response.json()]


def process_leaderboard_info_with_scores(
    id: str,
) -> Tuple[Optional[data.LeaderboardInfo], Optional[List[data.Score]]]:
    l_info: Optional[data.LeaderboardInfo] = None
    l_scores: Optional[List[data.Score]] = None

    try:
        l_id = uuid.UUID(query_input_validation(id))
    except QueryNotValid as e:
        logger.error(e)
        return l_info, l_scores
    except Exception as e:
        logger.error(e)
        return l_info, l_scores

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_to_function = {
            executor.submit(get_leaderboard_info, l_id): "get_leaderboard_info",
            executor.submit(get_scores, l_id): "get_scores",
        }
        for future in as_completed(future_to_function):
            func_name = future_to_function[future]
            result = future.result()
            if result is not None:
                if func_name == "get_leaderboard_info":
                    l_info = result
                if func_name == "get_scores":
                    l_scores = result

    return l_info, l_scores


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
