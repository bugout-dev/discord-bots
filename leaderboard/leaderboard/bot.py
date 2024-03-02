import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Set

import discord
from bugout.data import BugoutResource, BugoutResources
from discord import app_commands
from discord.ext import commands
from discord.guild import Guild
from discord.message import Message

from . import actions, data
from .cogs.configure import ConfigureCog
from .cogs.leaderboard import LeaderboardCog
from .cogs.leaderboards import LeaderboardsCog
from .cogs.position import PositionCog
from .cogs.user import UserCog
from .settings import (
    BUGOUT_BROOD_URL,
    BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG,
    BUGOUT_RESOURCE_TYPE_DISCORD_BOT_USER_IDENTIFIER,
    COLORS,
    LEADERBOARD_DISCORD_BOT_ACTIVITY_STATUS,
    LEADERBOARD_DISCORD_BOT_NAME,
    MOONSTREAM_APPLICATION_ID,
    MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN,
    MOONSTREAM_DISCORD_LINK,
    MOONSTREAM_ENGINE_API_URL,
    MOONSTREAM_THUMBNAIL_LOGO_URL,
)
from .settings import bugout_client as bc
from .version import VERSION

logger = logging.getLogger(__name__)


def configure_intents() -> discord.flags.Intents:
    intents = discord.Intents.default()
    intents.message_content = True

    return intents


class LeaderboardDiscordBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.bugout_connection_init()

        self._server_configs: Dict[int, data.ResourceConfig] = {}
        self._user_idents: Dict[int, List[data.UserIdentity]] = {}

    def bugout_connection_init(self):
        if MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN == "":
            raise Exception(
                f"MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN environment variable is not set, configuration fetch unavailable"
            )

        if MOONSTREAM_APPLICATION_ID == "":
            raise Exception(
                f"MOONSTREAM_APPLICATION_ID environment variable is not set, configuration fetch unavailable"
            )

        try:
            bugout_application = bc.get_application(
                token=MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN,
                application_id=MOONSTREAM_APPLICATION_ID,
            )
            logger.info(
                f"Connected to Bugout application {bugout_application.name} with ID {bugout_application.id}"
            )
        except Exception as e:
            raise Exception(
                f"Unable to establish connection with Bugout application, err: {e}"
            )

    @property
    def server_configs(self):
        return self._server_configs

    def set_server_configs_from_resource(self, resource: BugoutResource):
        try:
            discord_server_id = resource.resource_data["discord_server_id"]
            self._server_configs[discord_server_id] = data.ResourceConfig(
                id=resource.id, resource_data=data.Config(**resource.resource_data)
            )
        except KeyError:
            logger.warning(f"Malformed resource with ID: {str(resource.id)}")
        except Exception as e:
            logger.error(e)

    def set_server_configs_leaderboard_info(
        self, leaderboard: data.ConfigLeaderboard, leaderboard_info: Any
    ):
        try:
            leaderboard.leaderboard_info = data.LeaderboardInfo(**leaderboard_info)
        except Exception as e:
            logger.error(e)

    @property
    def user_idents(self):
        return self._user_idents

    def set_user_idents_from_resource(self, resource: BugoutResource):
        try:
            discord_user_id = resource.resource_data["discord_user_id"]
            fetched_identity = data.UserIdentity(
                resource_id=resource.id,
                identifier=resource.resource_data["identifier"],
                name=resource.resource_data["name"],
            )
            existing_identities = self._user_idents.get(discord_user_id)
            if existing_identities is None:
                self._user_idents[discord_user_id] = [fetched_identity]
            else:
                self._user_idents[discord_user_id].append(fetched_identity)
        except KeyError:
            logger.warning(f"Malformed resource with ID: {str(resource.id)}")
        except Exception as e:
            logger.error(e)

    async def on_ready(self):
        logger.info(
            f"Logged in {COLORS.BLUE}{str(len(self.guilds))}{COLORS.RESET} guilds on as {COLORS.BLUE}{self.user} - {self.user.id}{COLORS.RESET}"
        )

        activity = discord.Activity(
            name=LEADERBOARD_DISCORD_BOT_ACTIVITY_STATUS,
            type=discord.ActivityType.playing,
        )
        await self.change_presence(activity=activity)

        for guild in self.guilds:
            await self.tree.sync(guild=discord.Object(id=guild.id))

        await self.tree.sync()

        logger.info(f"Slash commands synced for {len(self.guilds)} guilds")

    async def setup_hook(self):
        # Prepare list of cog instances
        available_cogs_map: List[data.CogMap] = []
        for cog in [
            ConfigureCog(self),
            LeaderboardCog(self),
            LeaderboardsCog(self),
            PingCog(self),
            PositionCog(self),
            UserCog(self),
        ]:
            cog_map = data.CogMap(
                cog=cog,
                slash_command_name=cog.slash_command_data.name,
                slash_command_description=cog.slash_command_data.description,
                slash_command_callback=cog.slash_command_handler,
            )
            try:
                cog_map.slash_command_autocompletion = cog.slash_command_autocompletion
                cog_map.slash_command_autocomplete_value = (
                    cog.slash_command_data.autocomplete_value
                )
            except:
                logger.debug(
                    f"Passing cog with slash command {cog.slash_command_data.name}, no autocompletion"
                )

            available_cogs_map.append(cog_map)

            await self.add_cog(cog)

        # Fetch list of guilds server connected to
        known_guilds: List[Guild] = []
        async for guild in self.fetch_guilds():
            self.tree.clear_commands(guild=guild)
            known_guilds.append(guild)

        # Generate commands for specified guild and add it to command tree
        for cog in available_cogs_map:
            for guild in known_guilds:
                is_command_for_guild_registered = False

                guild_config = self.server_configs.get(guild.id)
                if guild_config is not None:
                    for command in guild_config.resource_data.commands:
                        if command.origin == cog.slash_command_name:
                            # Generate unique slash command based on server configuration and register it
                            await self.add_command_to_tree(
                                name=command.renamed, cog=cog, guild=guild
                            )
                            is_command_for_guild_registered = True
                            logger.debug(
                                f"Registered unique command  {command.renamed} at {guild.name}"
                            )
                if is_command_for_guild_registered is False:
                    # Register common command in guild
                    await self.add_command_to_tree(
                        name=cog.slash_command_name, cog=cog, guild=guild
                    )
                    logger.debug(
                        f"Registered command {cog.slash_command_name} at {guild.name}"
                    )

    async def add_command_to_tree(self, name: str, cog, guild: Optional[Guild] = None):
        """
        Add application command to the command tree.
        """
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

    async def load_bugout_configs(self, semaphore: asyncio.Semaphore) -> int:
        url = f"{BUGOUT_BROOD_URL}/resources/?application_id={MOONSTREAM_APPLICATION_ID}&type={BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG}"
        response = await actions.caller(url=url, semaphore=semaphore, is_auth=True)

        if response is None:
            logger.warning("Unable to fetch configurations from Bugout resources")
            return 0

        resources = BugoutResources(**response)
        num_of_configs = len(resources.resources)
        logger.info(f"Fetched {num_of_configs} Discord server configurations")

        if num_of_configs == 0:
            return num_of_configs

        for r in resources.resources:
            self.set_server_configs_from_resource(resource=r)

        return num_of_configs

    async def load_bugout_users_tasks(
        self, semaphore: asyncio.Semaphore
    ) -> List[asyncio.Task]:
        async def load_bugout_users() -> None:
            response = await actions.caller(
                url=f"{BUGOUT_BROOD_URL}/resources/?application_id={MOONSTREAM_APPLICATION_ID}&type={BUGOUT_RESOURCE_TYPE_DISCORD_BOT_USER_IDENTIFIER}",
                semaphore=semaphore,
                is_auth=True,
            )
            if response is not None:
                resources = BugoutResources(**response)
                logger.info(f"Fetched identities of {len(resources.resources)} users")
                for r in resources.resources:
                    self.set_user_idents_from_resource(resource=r)

        return [asyncio.create_task(load_bugout_users())]

    async def load_leaderboards_info_tasks(
        self, semaphore: asyncio.Semaphore
    ) -> List[asyncio.Task]:
        async def load_leaderboard_info(leaderboard: data.ConfigLeaderboard) -> None:
            url = f"{MOONSTREAM_ENGINE_API_URL}/leaderboard/info?leaderboard_id={str(leaderboard.leaderboard_id)}"
            response = await actions.caller(url=url, semaphore=semaphore)
            if response is not None:
                self.set_server_configs_leaderboard_info(
                    leaderboard=leaderboard, leaderboard_info=response
                )

        all_leaderboards: List[data.ConfigLeaderboard] = []
        for g_id in self.server_configs:
            leaderboards = self.server_configs[g_id].resource_data.leaderboards
            all_leaderboards.extend(leaderboards)

        tasks = []
        for l in all_leaderboards:
            task = asyncio.create_task(load_leaderboard_info(leaderboard=l))
            tasks.append(task)

        return tasks

    async def load_configs(self):
        # TODO(kompotkot): Add pagination for resources
        num_of_configs = await self.load_bugout_configs(semaphore=asyncio.Semaphore(1))
        logger.info(f"Loaded {num_of_configs} configurations")

        semaphore = asyncio.Semaphore(4)
        l_info_tasks = await self.load_leaderboards_info_tasks(semaphore=semaphore)
        u_tasks = await self.load_bugout_users_tasks(semaphore=semaphore)

        await asyncio.gather(*[*l_info_tasks, *u_tasks])


class PingCog(commands.Cog):
    def __init__(self, bot: LeaderboardDiscordBot):
        self.bot = bot

        self._slash_command_data = data.SlashCommandData(
            name="ping", description=f"Ping pong with {LEADERBOARD_DISCORD_BOT_NAME}"
        )

    @property
    def slash_command_data(self) -> data.SlashCommandData:
        return self._slash_command_data

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
        description = f"""**Pong**
- Bot name: {LEADERBOARD_DISCORD_BOT_NAME}
- Version: {VERSION}
- Latency: {round(self.bot.latency * 1000)}ms

**Support Discord**: {MOONSTREAM_DISCORD_LINK}
"""
        embed = discord.Embed(
            description=description,
        )
        embed.set_thumbnail(url=MOONSTREAM_THUMBNAIL_LOGO_URL)

        await interaction.response.send_message(embed=embed)
