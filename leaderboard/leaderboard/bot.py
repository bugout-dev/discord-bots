import logging
from typing import Callable, Dict, List, Optional, Set

import discord
from discord import app_commands
from discord.ext import commands
from discord.guild import Guild
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

    async def on_ready(self):
        logger.info(
            f"Logged in {COLORS.BLUE}{str(len(self.guilds))}{COLORS.RESET} guilds on as {COLORS.BLUE}{self.user} - {self.user.id}{COLORS.RESET}"
        )

        for guild in self.guilds:
            await self.tree.sync(guild=discord.Object(id=guild.id))

        await self.tree.sync()

        logger.info(f"Slash commands synced for {len(self.guilds)} guilds")

    async def setup_hook(self):
        # Fetch list of guilds server connected to
        known_guilds: List[Guild] = []
        async for guild in self.fetch_guilds():
            self.tree.clear_commands(guild=guild)
            known_guilds.append(guild)

        # Prepare list of cog instances
        available_cogs_map: List[data.CogMap] = []
        for cog in [
            ConfigureCog(self),
            LeaderboardCog(self),
            PingCog(self),
            PositionCog(self),
            UserCog(self),
        ]:
            slash_command_data = cog.slash_command_data()
            cog_map = data.CogMap(
                cog=cog,
                slash_command_name=slash_command_data.name,
                slash_command_description=slash_command_data.description,
                slash_command_callback=cog.slash_command_handler,
            )
            try:
                cog_map.slash_command_autocompletion = cog.slash_command_autocompletion
                cog_map.slash_command_autocomplete_value = (
                    slash_command_data.autocomplete_value
                )
            except:
                logger.debug(
                    f"Passing cog with slash command {slash_command_data.name}, no autocompletion"
                )

            available_cogs_map.append(cog_map)

            await self.add_cog(cog)

        # Generate commands for specified guild and add it to command tree
        for cog in available_cogs_map:
            is_registered_command_for_cog = False

            for guild in known_guilds:
                is_command_for_guild_registered = False

                guild_config = self.server_configs.get(guild.id)
                if guild_config is not None:
                    for command in guild_config.resource_data.commands:
                        if command.origin == cog.slash_command_name:
                            # Generate unique slash command based on server configuration and register it
                            self.add_command_to_tree(
                                name=command.renamed, cog=cog, guild=guild
                            )
                            is_registered_command_for_cog = True
                            is_command_for_guild_registered = True
                            logger.debug(
                                f"1 Registered {command.renamed} command at {guild.name}"
                            )
                if is_command_for_guild_registered is False:
                    # Register for guild command
                    self.add_command_to_tree(
                        name=cog.slash_command_name, cog=cog, guild=guild
                    )
                    is_registered_command_for_cog = True
                    logger.debug(
                        f"2 Registered {cog.slash_command_name} command at {guild.name}"
                    )
            if is_registered_command_for_cog is False:
                # Register default cog and add to self.tree
                self.add_command_to_tree(name=cog.slash_command_name, cog=cog)
                logger.debug(
                    f"3 Registered {cog.slash_command_name} command at {guild.name}"
                )

    def add_command_to_tree(self, name: str, cog, guild: Optional[Guild] = None):
        com: app_commands.Command = app_commands.Command(
            name=name,
            description=cog.slash_command_description,
            callback=cog.slash_command_callback,
        )
        if cog.slash_command_autocompletion is not None:
            com.autocomplete(cog.slash_command_autocomplete_value)(
                cog.slash_command_autocompletion
            )

        self.tree.add_command(com, guild=guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        logger.info(
            f"Joined to new guild {COLORS.BLUE}{guild} - {guild.id}{COLORS.RESET}"
        )
        await self.tree.sync(guild=guild)

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

        self._slash_command_data = data.SlashCommandData(
            name="ping", description=f"Ping pong with {LEADERBOARD_DISCORD_BOT_NAME}"
        )

    def slash_command_data(self) -> data.SlashCommandData:
        return self._slash_command_data

    def prepare_embed(self) -> discord.Embed:
        return discord.Embed(
            description=f"Bot **{LEADERBOARD_DISCORD_BOT_NAME}** ping latency is **{round(self.bot.latency * 1000)}ms**",
        )

    # https://discordpy.readthedocs.io/en/stable/interactions/api.html?highlight=app_commands%20command#discord.app_commands.command
    # @app_commands.command(
    #     name="ping", description=f"Ping pong with {LEADERBOARD_DISCORD_BOT_NAME}"
    # )
    async def slash_command_handler(self, interaction: discord.Interaction):
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
