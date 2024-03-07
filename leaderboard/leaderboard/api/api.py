import asyncio
import logging
import os
from typing import Dict, List, Optional

from bugout.data import BugoutResources
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .. import actions as bot_actions
from ..settings import (
    BUGOUT_BROOD_URL,
    BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG,
    DISCORD_API_URL,
    LEADERBOARD_DISCORD_BOT_TOKEN,
    MOONSTREAM_APPLICATION_ID,
    MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN,
)
from . import data
from .version import LEADERBOARD_DISCORD_BOT_API_VERSION

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def get_configs(semaphore: asyncio.Semaphore):
    """
    Returns map of guild, channel and linked to it leaderboards.
    If leaderboard does not linked to any channel, it returns under key channel_id = "".

    Returns:
    guild_id: {channel_id: [{leaderboard_id, short_name}]}
    """
    configs_dict: Dict[str, Dict[str, List[data.LeaderboardResponse]]] = {}

    url = f"{BUGOUT_BROOD_URL}/resources/?application_id={MOONSTREAM_APPLICATION_ID}&type={BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG}"
    response = await bot_actions.caller(
        url=url, semaphore=semaphore, token=MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN
    )
    if response is None:
        return configs_dict

    resources = BugoutResources(**response)

    for r in resources.resources:
        guild_id = r.resource_data.get("discord_server_id")

        if guild_id is None:
            logger.warning(f"Incorrect config resource with ID: {r.id}")
            continue

        leaderboards = r.resource_data.get("leaderboards", [])
        for l in leaderboards:
            guild_id_str = str(guild_id)

            # Ensure the guild ID exists in the dictionary
            if guild_id_str not in configs_dict:
                configs_dict[guild_id_str] = {}

            channel_ids = l.get("channel_ids", [])
            if len(channel_ids) == 0:
                # Ensure empty channel exists in the dictionary
                if "" not in configs_dict[guild_id_str]:
                    configs_dict[guild_id_str][""] = []
                # Append leaderboard without channel
                configs_dict[guild_id_str][""].append(
                    data.LeaderboardResponse(
                        leaderboard_id=l.get("leaderboard_id", ""),
                        short_name=l.get("short_name", ""),
                    )
                )
                continue

            for ch in channel_ids:
                ch_str = str(ch)
                # Ensure the channel ID exists in the dictionary
                if ch_str not in configs_dict[guild_id_str]:
                    configs_dict[guild_id_str][ch_str] = []
                # Append leaderboard to its channel
                configs_dict[guild_id_str][ch_str].append(
                    data.LeaderboardResponse(
                        leaderboard_id=l.get("leaderboard_id", ""),
                        short_name=l.get("short_name", ""),
                    )
                )

    return configs_dict


async def get_guilds(semaphore: asyncio.Semaphore):
    guilds = data.GuildsResponse(guilds=[])
    response = await bot_actions.caller(
        url=f"{DISCORD_API_URL}/users/@me/guilds",
        semaphore=semaphore,
        token=LEADERBOARD_DISCORD_BOT_TOKEN,
        auth_schema="Bot",
    )

    if response is None:
        return guilds

    guilds.guilds = [
        data.GuildResponse(id=g.get("id"), name=g.get("name", "")) for g in response
    ]

    return guilds


async def extent_guild_with_channels(
    semaphore: asyncio.Semaphore,
    guild: data.GuildResponse,
    config: Optional[Dict[str, List[data.LeaderboardResponse]]] = None,
):
    response = await bot_actions.caller(
        url=f"{DISCORD_API_URL}/guilds/{guild.id}/channels",
        semaphore=semaphore,
        token=LEADERBOARD_DISCORD_BOT_TOKEN,
        auth_schema="Bot",
    )
    if response is None:
        return guild

    if config is not None:
        if len(config.get("", [])) != 0:
            guild.channels.append(
                data.GuildChannelResponse(
                    id="", name="", leaderboards=config.get("", [])
                )
            )

    for ch in response:
        ch_id = ch.get("id")
        if ch_id is None:
            logger.warning(f"Strange channel without ID: {ch}")
            continue

        leaderboards = []
        if config is not None:
            leaderboards = config.get(ch_id, [])
        
        if len(leaderboards) == 0:
            continue

        guild.channels.append(
            data.GuildChannelResponse(
                id=ch_id, name=ch.get("name", ""), leaderboards=leaderboards
            )
        )

    return guild


def run_app() -> FastAPI:
    app = FastAPI(
        title=f"Moonstream leaderboard Discord bot API",
        description="Moonstream leaderboard Discord bot API endpoints.",
        version=LEADERBOARD_DISCORD_BOT_API_VERSION,
        openapi_tags=[],
        openapi_url="/openapi.json",
        docs_url=None,
        redoc_url=f"/docs",
    )

    if LEADERBOARD_DISCORD_BOT_TOKEN == "":
        raise Exception("LEADERBOARD_DISCORD_BOT_TOKEN environment variable is not set")

    if MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN == "":
        raise Exception(
            f"MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN environment variable is not set"
        )

    if MOONSTREAM_APPLICATION_ID == "":
        raise Exception(f"MOONSTREAM_APPLICATION_ID environment variable is not set")

    RAW_ORIGINS = os.environ.get("LEADERBOARD_DISCORD_BOT_API_CORS_ALLOWED_ORIGINS")
    if RAW_ORIGINS is None:
        raise ValueError(
            "LEADERBOARD_DISCORD_BOT_API_CORS_ALLOWED_ORIGINS environment variable must be set (comma-separated list of CORS allowed origins)"
        )
    ALLOWED_ORIGINS = RAW_ORIGINS.split(",")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/ping", response_model=data.PingResponse)
    async def get_ping_handler() -> data.PingResponse:
        return data.PingResponse(status="ok")

    @app.get("/version", response_model=data.VersionResponse)
    async def get_version_handler() -> data.VersionResponse:
        return data.VersionResponse(version=LEADERBOARD_DISCORD_BOT_API_VERSION)

    @app.get("/guilds", response_model=data.GuildsResponse)
    async def get_guilds_with_channels_handler():
        guilds = data.GuildsResponse(guilds=[])

        semaphore = asyncio.Semaphore(4)
        try:
            guilds_task = asyncio.create_task(get_guilds(semaphore=semaphore))
            configs_task = asyncio.create_task(get_configs(semaphore=semaphore))
            guilds = await guilds_task
            configs = await configs_task
        except Exception as e:
            logger.error(f"Unexpected error during get_guilds operation, error: {e}")
            return HTTPException(status_code=500)

        try:
            tasks = []
            for g in guilds.guilds:
                task = asyncio.create_task(
                    extent_guild_with_channels(
                        semaphore=semaphore, guild=g, config=configs.get(g.id)
                    )
                )
                tasks.append(task)
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(
                f"Unexpected error during get_guild_channels operation, error: {e}"
            )
            return HTTPException(status_code=500)

        return guilds

    return app
