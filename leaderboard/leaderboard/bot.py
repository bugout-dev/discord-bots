import logging
from typing import Callable, Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands
from discord.message import Message

from . import actions, data
from .cogs.configure import ConfigureCog
from .cogs.leaderboard import LeaderboardCog
from .cogs.position import PositionCog
from .cogs.user import UserCog
from .settings import (
    BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG,
    BUGOUT_RESOURCE_TYPE_DISCORD_BOT_USER_IDENTIFIER,
    COLORS,
    LEADERBOARD_DISCORD_BOT_NAME,
    MOONSTREAM_APPLICATION_ID,
    MOONSTREAN_DISCORD_BOT_ACCESS_TOKEN,
)
from .settings import bugout_client as bc

logger = logging.getLogger(__name__)


def configure_intents() -> discord.flags.Intents:
    intents = discord.Intents.default()
    intents.message_content = True

    return intents


class LeaderboardDiscordBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.server_configs: Dict[int, data.ResourceConfig] = {}
        self.user_idents: Dict[int, List[data.UserIdentity]] = {}

        self.available_cogs = [
            PingCog,
            LeaderboardCog,
            PositionCog,
            ConfigureCog,
            UserCog,
        ]

    async def on_ready(self):
        logger.info(
            f"Logged in {COLORS.BLUE}{str(len(self.guilds))}{COLORS.RESET} guilds on as {COLORS.BLUE}{self.user} - {self.user.id}{COLORS.RESET}"
        )

    async def setup_hook(self):
        for c in self.available_cogs:
            await self.add_cog(c(self))

        synced = await self.tree.sync()
        logger.info(f"Slash commands synced: {len(synced)}")

    async def on_message(self, message: Message):
        logger.debug(
            actions.prepare_log_message(
                "-",
                "MESSAGE",
                message.author,
                message.guild,
                message.channel,
            )
        )

        await self.process_commands(message)

    def load_bugout_users(self) -> None:
        try:
            response = bc.list_resources(
                token=MOONSTREAN_DISCORD_BOT_ACCESS_TOKEN,
                params={
                    "application_id": MOONSTREAM_APPLICATION_ID,
                    "type": BUGOUT_RESOURCE_TYPE_DISCORD_BOT_USER_IDENTIFIER,
                },
            )

            logger.info(f"Fetched identities of {len(response.resources)} users")

            for r in response.resources:
                try:
                    discord_user_id = r.resource_data["discord_user_id"]
                    fetched_identity = data.UserIdentity(
                        resource_id=r.id,
                        identifier=r.resource_data["identifier"],
                        name=r.resource_data["name"],
                    )

                    identities = self.user_idents.get(discord_user_id)
                    if identities is None:
                        self.user_idents[discord_user_id] = [fetched_identity]
                    else:
                        self.user_idents[discord_user_id].append(fetched_identity)
                except KeyError as e:
                    logger.warning(f"Malformed resource with ID: {str(r.id)}")
                    continue
                except Exception as e:
                    logger.error(e)
        except Exception as e:
            raise Exception(e)

    def load_bugout_configs(self) -> None:
        try:
            response = bc.list_resources(
                token=MOONSTREAN_DISCORD_BOT_ACCESS_TOKEN,
                params={
                    "application_id": MOONSTREAM_APPLICATION_ID,
                    "type": BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG,
                },
            )

            logger.info(
                f"Fetched {len(response.resources)} Discord server configurations"
            )

            for r in response.resources:
                try:
                    discord_server_id = r.resource_data["discord_server_id"]
                    self.server_configs[discord_server_id] = data.ResourceConfig(
                        id=r.id, resource_data=data.Config(**r.resource_data)
                    )
                except KeyError:
                    logger.warning(f"Malformed resource with ID: {str(r.id)}")
                    continue
                except Exception as e:
                    logger.error(e)
        except Exception as e:
            raise Exception(e)


class PingCog(commands.Cog):
    def __init__(self, bot: LeaderboardDiscordBot):
        self.bot = bot

    def prepare_embed(self) -> discord.Embed:
        return discord.Embed(
            description=f"Bot **{LEADERBOARD_DISCORD_BOT_NAME}** ping latency is **{round(self.bot.latency * 1000)}ms**",
        )

    @commands.command()
    async def ping(self, ctx: commands.Context):
        logger.info(
            actions.prepare_log_message(
                "ping", "COMMAND", ctx.author, ctx.guild, ctx.channel
            )
        )
        await ctx.send(embed=self.prepare_embed())

    # https://discordpy.readthedocs.io/en/stable/interactions/api.html?highlight=app_commands%20command#discord.app_commands.command
    @app_commands.command(
        name="ping", description=f"Ping pong with {LEADERBOARD_DISCORD_BOT_NAME}"
    )
    async def _ping(self, interaction: discord.Interaction):
        logger.info(
            actions.prepare_log_message(
                "/ping",
                "SLASH COMMAND",
                interaction.user,
                interaction.guild,
                interaction.channel,
            )
        )
        await interaction.response.send_message(embed=self.prepare_embed())
