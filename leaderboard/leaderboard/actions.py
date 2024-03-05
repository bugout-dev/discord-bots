import asyncio
import json
import logging
import re
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import aiohttp
import discord
from bugout.data import BugoutResource
from discord import Embed
from discord.guild import Guild
from discord.interactions import InteractionMessage
from discord.member import Member
from discord.role import Role
from discord.user import User

from . import data
from .settings import (
    BUGOUT_BROOD_URL,
    BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG,
    BUGOUT_RESOURCE_TYPE_DISCORD_BOT_USER_IDENTIFIER,
    COLORS,
    MOONSTREAM_APPLICATION_ID,
    MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN,
    MOONSTREAM_ENGINE_API_URL,
)

logger = logging.getLogger(__name__)

QUERY_REGEX = re.compile("[\[\]@#$%^&?;`/]")


class QueryNotValid(Exception):
    """
    Raised when query validation not passed.
    """


class PaginationView(discord.ui.View):
    def __init__(
        self,
        title: str,
        description: str,
        wrapped_fields: List[List[Any]],
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.message: InteractionMessage

        self.title = title
        self.description = description
        self.wrapped_fields = wrapped_fields

        self.current_page: int = 1
        self.offset: int = 5
        fields_len = len(wrapped_fields)
        self.total_pages = int(fields_len / self.offset)
        if fields_len == 0:
            self.total_pages = self.current_page
        elif fields_len % self.offset != 0:
            self.total_pages += 1

    async def send(self, interaction: discord.Interaction):
        await interaction.response.send_message(view=self, ephemeral=True)
        self.message = await interaction.original_response()
        await self.update_view(self.wrapped_fields[: self.offset])

    async def update_view(self, wrapped_fields: List[List[Any]]):
        """
        Update current view and navigation buttons to handle pagination.
        """
        if self.current_page == 1:
            self.button_previous.disabled = True
            self.button_previous.style = discord.ButtonStyle.gray
        else:
            self.button_previous.disabled = False
            self.button_previous.style = discord.ButtonStyle.primary

        if self.current_page == self.total_pages:
            self.button_next.disabled = True
            self.button_next.style = discord.ButtonStyle.gray
        else:
            self.button_next.disabled = False
            self.button_next.style = discord.ButtonStyle.primary

        await self.message.edit(
            embed=prepare_dynamic_embed_with_pagination(
                title=self.title,
                description=self.description,
                current_page=self.current_page,
                total_pages=self.total_pages,
                wrapped_fields=wrapped_fields,
            ),
            view=self,
        )

    @discord.ui.button(label="<", row=2)
    async def button_previous(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        self.current_page -= 1
        until_item = self.current_page * self.offset
        await self.update_view(
            wrapped_fields=self.wrapped_fields[until_item - self.offset : until_item]
        )

    @discord.ui.button(label=">", row=2)
    async def button_next(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        self.current_page += 1
        until_item = self.current_page * self.offset
        await self.update_view(
            wrapped_fields=self.wrapped_fields[until_item - self.offset : until_item]
        )


def score_converter(
    source: int, conversion: int, conversion_vector: str
) -> Union[int, float]:
    if conversion_vector == "divide":
        return source / conversion
    return source


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


def prepare_dynamic_embed(
    title: str, description: str, fields: List[Any] = []
) -> Embed:
    embed = Embed(
        title=title,
        description=description,
    )
    for f in fields:
        embed.add_field(name=f["field_name"], value=f["field_value"])

    return embed


def prepare_dynamic_embed_with_pagination(
    title: str,
    description: str,
    wrapped_fields: List[List[Any]],
    current_page: int,
    total_pages: int,
) -> Embed:
    description += "\n"
    description += f"Page: {current_page}/{total_pages}"
    embed = Embed(
        title=title,
        description=description,
    )
    for wf in wrapped_fields:
        for f in wf:
            embed.add_field(name=f["field_name"], value=f["field_value"])

    return embed


class DynamicSelect(discord.ui.Select):
    def __init__(
        self,
        callback_func: Callable,
        options: List[discord.SelectOption],
        placeholder: str = "",
        *args,
        **kwargs,
    ):
        super().__init__(options=options, placeholder=placeholder, *args, **kwargs)
        self.callback_func = callback_func

    async def callback(self, interaction: discord.Interaction):
        await self.callback_func(interaction, self.values)


def auth_middleware(
    user_id: int,
    user_roles: List[Role],
    server_config_roles: List[data.ConfigRole],
    guild_owner_id: Optional[int] = None,
) -> bool:
    """
    Allow access if:
    - user is guild owner
    - there are no auth roles in configuration yet
    - user has role specified in configuration
    """
    if guild_owner_id is not None:
        if user_id == guild_owner_id:
            return True

    if len(server_config_roles) == 0:
        return True

    server_config_role_ids_set = set([r.id for r in server_config_roles])
    user_role_ids_set = set([r.id for r in user_roles])

    if len(user_role_ids_set.intersection(server_config_role_ids_set)) >= 1:
        return True

    return False


async def caller(
    url: str,
    semaphore: asyncio.Semaphore,
    method: data.RequestMethods = data.RequestMethods.GET,
    request_data: Optional[Dict[str, Any]] = None,
    is_auth: bool = False,
    timeout: int = 5,
) -> Optional[Any]:
    async with semaphore:
        try:
            async with aiohttp.ClientSession() as session:
                request_method = getattr(session, method.value, session.get)
                request_kwargs: Dict[str, Any] = {"timeout": timeout, "headers": {}}
                if (
                    method == data.RequestMethods.POST
                    or method == data.RequestMethods.PUT
                ):
                    request_kwargs["json"] = request_data
                    request_kwargs["headers"]["Content-Type"] = "application/json"
                if is_auth is True:
                    request_kwargs["headers"][
                        "Authorization"
                    ] = f"Bearer {MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN}"
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
        url=f"{MOONSTREAM_ENGINE_API_URL}/leaderboard/info?leaderboard_id={str(l_id)}",
        semaphore=asyncio.Semaphore(1),
    )
    if response is not None:
        logger.debug(f"Received info for leaderboard with ID: {response.get('id')}")
        l_info = data.LeaderboardInfo(**response)
    return l_info


async def get_scores(l_id: uuid.UUID) -> Optional[List[data.Score]]:
    l_scores: Optional[List[data.Score]] = None
    response = await caller(
        url=f"{MOONSTREAM_ENGINE_API_URL}/leaderboard/?leaderboard_id={str(l_id)}&limit=10&offset=0",
        semaphore=asyncio.Semaphore(1),
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


async def get_score(l_id: uuid.UUID, address: str) -> Optional[data.Score]:
    l_score: Optional[data.Score] = None
    response = await caller(
        url=f"{MOONSTREAM_ENGINE_API_URL}/leaderboard/position?leaderboard_id={str(l_id)}&address={address}&normalize_addresses=False&window_size=0&limit=10&offset=0",
        semaphore=asyncio.Semaphore(1),
    )
    if response is not None:
        l_scores = [data.Score(**s) for s in response]
        if len(l_scores) == 1:
            l_score = l_scores[0]
    return l_score


async def process_leaderboard_info_with_score(
    l_id: uuid.UUID, address: str
) -> Tuple[Optional[data.LeaderboardInfo], Optional[data.Score]]:
    l_info, l_score = await asyncio.gather(
        get_leaderboard_info(l_id), get_score(l_id, address)
    )

    return l_info, l_score


async def push_user_identity(
    discord_user_id: int,
    identifier: str,
    name: str,
) -> Optional[BugoutResource]:
    resource: Optional[BugoutResource] = None
    response = await caller(
        url=f"{BUGOUT_BROOD_URL}/resources",
        semaphore=asyncio.Semaphore(1),
        method=data.RequestMethods.POST,
        request_data={
            "application_id": MOONSTREAM_APPLICATION_ID,
            "resource_data": {
                "type": BUGOUT_RESOURCE_TYPE_DISCORD_BOT_USER_IDENTIFIER,
                "discord_user_id": discord_user_id,
                "identifier": identifier,
                "name": name,
            },
        },
        is_auth=True,
    )

    if response is not None:
        resource = BugoutResource(**response)
        logger.info(
            f"Saved user {discord_user_id} identity as resource with ID: {resource.id}"
        )

    return resource


async def remove_user_identity(resource_id: uuid.UUID) -> Optional[uuid.UUID]:
    removed_resource_id: Optional[uuid.UUID] = None
    response = await caller(
        url=f"{BUGOUT_BROOD_URL}/resources/{str(resource_id)}",
        semaphore=asyncio.Semaphore(1),
        method=data.RequestMethods.DELETE,
        is_auth=True,
    )

    if response is not None:
        removed_resource_id = uuid.UUID(response["id"])
        logger.info(
            f"Removed user identity represented as resource with ID: {str(removed_resource_id)}"
        )

    return removed_resource_id


async def create_or_update_server_config(
    discord_server_id: int,
    leaderboards: Optional[List[data.ConfigLeaderboard]] = None,
    roles: Optional[List[data.ConfigRole]] = None,
    resource_id: Optional[uuid.UUID] = None,
) -> Optional[BugoutResource]:
    """
    Creates new resource if no server configuration presented in Brood resources.
    """
    resource: Optional[BugoutResource] = None

    if resource_id is None:
        resource = await create_server_config(
            discord_server_id=discord_server_id,
            leaderboards=leaderboards,
            roles=roles,
        )
        if resource is None:
            logger.error(
                f"Unable to create resource for new Discord server with ID: {discord_server_id}"
            )
            # del self.bot.server_configs[guild_id]
            return None
    else:
        resource = await update_server_config(
            resource_id=resource_id,
            leaderboards=leaderboards,
            roles=roles,
        )
        if resource is None:
            logger.error(
                f"Unable to update resource with ID: {str(resource_id)} for discord server with ID: {discord_server_id}"
            )
            return None

    return resource


async def create_server_config(
    discord_server_id: int,
    leaderboards: Optional[List[data.ConfigLeaderboard]] = None,
    roles: Optional[List[data.ConfigRole]] = None,
):
    resource: Optional[BugoutResource] = None
    response = await caller(
        url=f"{BUGOUT_BROOD_URL}/resources",
        semaphore=asyncio.Semaphore(1),
        method=data.RequestMethods.POST,
        request_data={
            "application_id": MOONSTREAM_APPLICATION_ID,
            "resource_data": {
                "type": BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG,
                "leaderboards": (
                    [json.loads(l.json()) for l in leaderboards]
                    if leaderboards is not None
                    else []
                ),
                "discord_auth_roles": (
                    [r.dict() for r in roles] if roles is not None else []
                ),
                "discord_server_id": discord_server_id,
            },
        },
        is_auth=True,
    )

    if response is not None:
        resource = BugoutResource(**response)
        logger.info(
            f"Created server config as resource with ID: {resource.id} for guild  {discord_server_id}"
        )

    return resource


async def update_server_config(
    resource_id: uuid.UUID,
    leaderboards: Optional[List[data.ConfigLeaderboard]] = None,
    roles: Optional[List[data.ConfigRole]] = None,
) -> Optional[BugoutResource]:
    resource: Optional[BugoutResource] = None
    if leaderboards is None and roles is None:
        return resource

    request_data: Dict[str, Any] = {"update": {}, "drop_keys": []}
    if leaderboards is not None:
        request_data["update"]["leaderboards"] = [
            json.loads(l.json()) for l in leaderboards
        ]
    if roles is not None:
        request_data["update"]["discord_auth_roles"] = [r.dict() for r in roles]

    response = await caller(
        url=f"{BUGOUT_BROOD_URL}/resources/{str(resource_id)}",
        semaphore=asyncio.Semaphore(1),
        method=data.RequestMethods.PUT,
        request_data=request_data,
        is_auth=True,
    )

    if response is not None:
        resource = BugoutResource(**response)
        logger.info(f"Updated server config at resource with ID: {resource.id}")

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
