import asyncio
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

import aiohttp
from bugout.data import BugoutSearchResult, BugoutSearchResults

from .data import DispatchTypes
from .embeddings import prepare_embedding
from .settings import (
    BUGOUT_DISCORD_BOTS_ACCESS_TOKEN,
    BUGOUT_DISCORD_BOTS_JOURNAL_ID,
    DISCORD_BASE_API_URL,
    DISCORD_BOT_USERNAME,
    DISCORD_GUILD_ID,
    bugout,
)
from .version import VERSION

logger = logging.getLogger(__name__)


async def api_call(
    token: str, method: str, url: str, content_type: Optional[str] = None, **kwargs
) -> Dict[str, Any]:
    """
    Handles Discord REST API requests.
    """
    data = {
        "headers": {
            "Authorization": f"Bot {token}",
            "User-Agent": f"Moonstream.to DiscordBot {DISCORD_BOT_USERNAME}, v{VERSION}",
            "Content-Type": content_type,
        }
    }
    kwargs = dict(data, **kwargs)

    async with aiohttp.ClientSession() as session:
        async with session.request(method, url, **kwargs) as resp:
            resp.raise_for_status()
            return await resp.json()


async def get_gateway(token: str) -> Dict[str, Any]:
    response = await api_call(
        token=token,
        method="GET",
        url=f"{DISCORD_BASE_API_URL}/gateway",
        content_type="application/x-www-form-urlencoded",
    )

    return response


async def get_channel(token: str, channel_id: str) -> Dict[str, Any]:
    response = await api_call(
        token=token,
        method="GET",
        url=f"{DISCORD_BASE_API_URL}/channels/{channel_id}",
        content_type="application/json",
    )
    return response


async def send_message(token: str, channel_id: str, content: str) -> Dict[str, Any]:
    """
    Send {content} message to channel {channel_id}.
    """
    response = await api_call(
        token=token,
        method="POST",
        url=f"{DISCORD_BASE_API_URL}/channels/{channel_id}/messages",
        content_type="application/json",
        json={"content": content},
    )
    return response


async def ws_listener(
    bot,
) -> None:
    """
    10 - Hello, opcode 2 - Identify
    11 - Ack Heartbeat
    0 - Any data
    """
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(f"{bot.ws_url}?v=6&encoding=json") as ws:
            async for msg in ws:
                data = json.loads(msg.data)

                if data["op"] == 10:
                    logger.info("Recieved 10 - Hello Heartbeat")
                    asyncio.ensure_future(
                        heartbeat(ws, bot, data["d"]["heartbeat_interval"])
                    )
                    await ws.send_json(
                        {
                            "op": 2,
                            "d": {
                                "token": bot.token,
                                "properties": {},
                                "compress": False,
                                "large_threshold": 250,
                            },
                        }
                    )

                elif data["op"] == 11:
                    logger.info("Received 11 - Ack Heartbeat")

                elif data["op"] == 0:
                    logger.info(f"Received 0 - Dispatch")

                    t = data["t"]
                    if DispatchTypes.READY.value == t:
                        logger.info(
                            f"Bot established connection with Discord websockets, session_id is: {data['d']['session_id']}"
                        )
                    elif DispatchTypes.TYPING_START.value == t:
                        pass
                    elif DispatchTypes.MESSAGE_CREATE.value == t:
                        d = data["d"]
                        guild_id = d.get("guild_id", None)
                        if guild_id is None:
                            # Private message
                            channel_id = d.get("channel_id")
                            logger.warn(
                                f"Communicated with bot in private message via channel id: {channel_id} and author: {d.get('author')}"
                            )
                        elif guild_id != "" and guild_id != DISCORD_GUILD_ID:
                            # Wrong guild message if filter applied
                            logger.warn(
                                f"Communicated with bot in unknown guild: {guild_id}"
                            )
                        else:
                            # Guild message
                            mentions = d.get("mentions", [])
                            for m in mentions:
                                m_id = m.get("id", "")
                                m_username = m.get("username", "")
                                if m_id == bot.app_id and m_username == bot.username:
                                    await bot.handle_mention(d)
                    else:
                        logger.info(f"Unhandled Dispatch type: {t}")
                else:
                    logger.info(f"Received unknown opcode {data['op']}")


async def heartbeat(ws, bot, interval: int = 41250) -> None:
    """
    Send heartbeat.
    """
    d = 0
    while True:
        # To seconds from milliseconds: interval/1000
        await asyncio.sleep(interval / 1000)
        try:
            await ws.send_json({"op": 1, "d": d if d >= 1 else None})
            logger.info(f"Sending opcode 1 with last_sequence(d): {d}")
            d += 1
        except Exception as err:
            logger.error(f"Error sending heartbeat: {err}")

        try:
            update_data_with_prompt(bot)
            logger.info("Fetched data and prompt from Bugout")
        except Exception as err:
            logger.error(err)
            pass


async def run_listener(bot) -> None:
    gateway = await get_gateway(bot.token)
    ws_url = gateway.get("url")
    await bot.set_ws_url(ws_url)
    logger.info(f"Received ws_url:{ws_url}, starting ws listener...")

    await ws_listener(bot)


def update_data_with_prompt(bot):
    """
    Fetch updated data and prompt from Bugout journal.
    """
    response: BugoutSearchResults = bugout.search(
        token=BUGOUT_DISCORD_BOTS_ACCESS_TOKEN,
        journal_id=BUGOUT_DISCORD_BOTS_JOURNAL_ID,
        query="tag:bot_username:librarian",
    )
    total_results = response.total_results
    if total_results != 2:
        logger.error(
            f"Wrong number: {total_results} of entires fetch from Bugout journal"
        )
        raise Exception("Unable to fetch data from Bugout journal")

    results: List[BugoutSearchResult] = response.results
    for result in results:
        if "function:data" in result.tags:
            current_data_hash = hashlib.md5(bot.data.encode("UTF-8")).hexdigest()
            new_data_hash = hashlib.md5(result.content.encode("UTF-8")).hexdigest()
            if current_data_hash != new_data_hash:
                docsearch, qa_chain = prepare_embedding(result.content)
                bot.docsearch = docsearch
                bot.qa_chain = qa_chain
                bot.data = result.content
                logger.info("Regenerated embeddings for source data")
        if "function:prompt" in result.tags:
            content = result.content
            try:
                content_json = json.loads(content)
                bot.prompt.prefix = content_json.get("prefix", "")
                bot.prompt.postfix = content_json.get("postfix", "")
            except Exception as err:
                logger.error(
                    f"Unable to parse bugout entry with bot prompt, err: {err}"
                )
                raise Exception("Unable to parse Bugout journal entry with bot prompt")
