import json
import logging
import uuid
from typing import Any, Callable, Coroutine, Dict, List, Optional, Union

import discord
from bugout.data import BugoutSearchResult, BugoutSearchResultAsEntity
from discord import app_commands
from discord.ext import commands
from discord.member import Member
from discord.message import Message

from . import actions, data
from .settings import (
    BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG,
    BUGOUT_RESOURCE_TYPE_DISCORD_BOT_USER_IDENTIFIER,
    COLORS,
    LEADERBOARD_DISCORD_BOT_NAME,
    MOONSTREAM_APPLICATION_ID,
    MOONSTREAM_URL,
    MOONSTREAN_DISCORD_BOT_ACCESS_TOKEN,
)
from .settings import bugout_client as bc

logger = logging.getLogger(__name__)

MESSAGE_LEADERBOARD_NOT_FOUND = "Leaderboard not found"
MESSAGE_POSITION_NOT_FOUND = "Leaderboard position not found"
MESSAGE_CHANNEL_NOT_FOUND = "Discord channel not found"


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


class LinkLeaderboardModal(discord.ui.Modal, title="Link leaderboard to server"):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.l_id_input = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label="Leaderboard ID",
            required=True,
            placeholder="Leaderboard identification number in UUID format",
        )
        self.l_sn_input = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label="Leaderboard short name",
            required=True,
            placeholder="Leaderboard short name for autocomplete",
        )
        self.th_ids_input = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label="Discord thread ID",
            required=False,
            placeholder="Discord thread ID, could be nullable",
        )

        self.add_item(self.l_id_input)
        self.add_item(self.l_sn_input)
        self.add_item(self.th_ids_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.stop()
        await interaction.response.defer()


class UnlinkLeaderboardModal(discord.ui.Modal, title="Unlink leaderboard"):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.u_l_id_input = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label="Leaderboard ID",
            required=True,
            placeholder="Leaderboard identification number in UUID format",
        )
        self.add_item(self.u_l_id_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.stop()
        await interaction.response.defer()


class ConfigureView(discord.ui.View):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.leaderboard_id: Optional[str] = None
        self.short_name: Optional[str] = None
        self.thread_ids: Optional[str] = None

        self.unlink_leaderboard_id: Optional[str] = None

    @discord.ui.button(label="Link leaderboard")
    async def button_link_leaderboard(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        link_leaderboard_modal = LinkLeaderboardModal()
        await interaction.response.send_modal(link_leaderboard_modal)
        await link_leaderboard_modal.wait()
        self.leaderboard_id = link_leaderboard_modal.l_id_input
        self.short_name = link_leaderboard_modal.l_sn_input
        self.thread_ids = link_leaderboard_modal.th_ids_input
        self.stop()

    @discord.ui.button(label="Unlink leaderboard")
    async def button_unlink_leaderboard(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        unlink_leaderboard_modal = UnlinkLeaderboardModal()
        await interaction.response.send_modal(unlink_leaderboard_modal)
        await unlink_leaderboard_modal.wait()
        self.unlink_leaderboard_id = unlink_leaderboard_modal.u_l_id_input
        self.stop()


class ConfigureCog(commands.Cog):
    def __init__(self, bot: LeaderboardDiscordBot):
        self.bot = bot

    async def background_process_configure(
        self, guild_id: int, server_config: data.ResourceConfig, is_new_server: bool
    ) -> None:
        if is_new_server is True:
            resource = await actions.create_server_config(
                discord_server_id=guild_id,
                leaderboards=server_config.resource_data.leaderboards,
            )
            if resource is None:
                logger.error(
                    f"Unable to update resource with ID: {str(server_config.id)} for discord server with ID: {guild_id}"
                )
                return
            server_config.id = resource.id

            logger.info(
                f"Create server config in resource with ID: {str(server_config.id)} for guild with ID: {guild_id}"
            )
        else:
            resource = await actions.update_server_config(
                resource_id=server_config.id,
                leaderboards=server_config.resource_data.leaderboards,
            )
            if resource is None:
                logger.error(
                    f"Unable to update resource with ID: {str(server_config.id)} for discord server with ID: {guild_id}"
                )
                return

            logger.info(
                f"Updated server config in resource with ID: {str(server_config.id)} for guild with ID: {guild_id}"
            )

    async def handle_link_new_leaderboard(
        self,
        server_config: data.ResourceConfig,
        configure_view: ConfigureView,
        interaction: discord.Interaction,
        guild_id: int,
        is_new_server: bool,
    ) -> None:
        for l in server_config.resource_data.leaderboards:
            if str(l.leaderboard_id) == str(configure_view.leaderboard_id):
                await interaction.followup.send(
                    embed=discord.Embed(
                        description=f"Leaderboard with ID: {str(l.leaderboard_id)} already linked to this Discord server"
                    ),
                )
                return

        thread_ids_str_set = set()
        thread_ids_raw = configure_view.thread_ids
        if thread_ids_raw is not None:
            thread_ids_str_set = set(str(thread_ids_raw).replace(" ", "").split(","))
        thread_ids = []
        for x in thread_ids_str_set:
            try:
                thread_ids.append(int(x))
            except Exception as e:
                logger.warning(f"Unable to parse thread ID {x} from input to integer")
                continue

        server_config.resource_data.leaderboards.append(
            data.ConfigLeaderboard(
                leaderboard_id=uuid.UUID(str(configure_view.leaderboard_id)),
                short_name=str(configure_view.short_name),
                thread_ids=thread_ids,
            )
        )
        logger.info(
            f"Linked new leaderboard with ID: {str(configure_view.leaderboard_id)} in Discord server {guild_id}"
        )
        await interaction.followup.send(
            embed=actions.prepare_dynamic_embed(
                title="New leaderboard linked to Discord server",
                description="",
                fields=[
                    {
                        "field_name": "Leaderboard ID",
                        "field_value": str(configure_view.leaderboard_id),
                    },
                    {
                        "field_name": "Short name",
                        "field_value": str(configure_view.short_name),
                    },
                    {
                        "field_name": "Threads",
                        "field_value": ", ".join([str(i) for i in thread_ids]),
                    },
                ],
            ),
        )

        self.bot.loop.create_task(
            self.background_process_configure(
                guild_id=guild_id,
                server_config=server_config,
                is_new_server=is_new_server,
            )
        )

    async def handle_unlink_leaderboard(
        self,
        server_config: data.ResourceConfig,
        configure_view: ConfigureView,
        interaction: discord.Interaction,
        guild_id: int,
    ) -> None:
        is_unlink = False
        leaderboards: List[data.ConfigLeaderboard] = []
        for l in server_config.resource_data.leaderboards:
            if str(l.leaderboard_id) == str(configure_view.unlink_leaderboard_id):
                is_unlink = True
                continue

            leaderboards.append(l)

        if is_unlink is False:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"Leaderboard with ID: {str(configure_view.unlink_leaderboard_id)} not found in linked to this Discord server"
                ),
            )
            return

        server_config.resource_data.leaderboards.clear()
        server_config.resource_data.leaderboards = leaderboards
        self.bot.server_configs[guild_id] = server_config

        logger.info(
            f"Unlinked leaderboard with ID: {str(configure_view.unlink_leaderboard_id)} from Discord server with ID: {guild_id}"
        )
        await interaction.followup.send(
            embed=actions.prepare_dynamic_embed(
                title="Unlinked leaderboard from Discord server",
                description="",
                fields=[
                    {
                        "field_name": "Leaderboard ID",
                        "field_value": str(configure_view.unlink_leaderboard_id),
                    },
                ],
            ),
        )

        self.bot.loop.create_task(
            self.background_process_configure(
                guild_id=guild_id,
                server_config=server_config,
                is_new_server=False,
            )
        )

    @app_commands.command(
        name="configure", description=f"Configure {LEADERBOARD_DISCORD_BOT_NAME} bot"
    )
    async def configure(self, interaction: discord.Interaction):
        logger.info(
            actions.prepare_log_message(
                "/configure",
                "SLASH COMMAND",
                interaction.user,
                interaction.guild,
                interaction.channel,
            )
        )

        if interaction.guild is None:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="Could not find a guild to configure, please use command at Discord server"
                )
            )
            return

        server_config: Optional[data.ResourceConfig] = self.bot.server_configs.get(
            interaction.guild.id
        )

        is_allowed = actions.auth_middleware(
            user_id=interaction.user.id,
            user_roles=(
                interaction.user.roles if type(interaction.user) == Member else []
            ),
            server_config_roles=(
                server_config.resource_data.discord_roles
                if server_config is not None
                else []
            ),
            guild_owner_id=interaction.guild.owner_id,
        )

        if is_allowed is False:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="Restricted section only for Discord server administrators"
                )
            )
            return

        is_new_server = False
        if server_config is None:
            server_config = data.ResourceConfig(
                resource_data=data.Config(
                    type=BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG,
                    discord_server_id=interaction.guild.id,
                    discord_roles=[],
                    leaderboards=[],
                ),
            )
            self.bot.server_configs[interaction.guild.id] = server_config
            is_new_server = True

        configure_view = ConfigureView()
        await interaction.response.send_message(
            embed=actions.prepare_dynamic_embed(
                title="List of leaderboards linked to Discord server",
                description=f"Allowed roles to manage Discord server configuration: {[r.name for r in server_config.resource_data.discord_roles]}",
                fields=[
                    d
                    for l in server_config.resource_data.leaderboards
                    for d in [
                        {
                            "field_name": "Leaderboard ID",
                            "field_value": str(l.leaderboard_id),
                        },
                        {
                            "field_name": "Short name",
                            "field_value": l.short_name,
                        },
                        {"field_name": "Thread IDs", "field_value": l.thread_ids},
                    ]
                ],
            ),
            view=configure_view,
        )
        await configure_view.wait()

        if configure_view.leaderboard_id is not None:
            await self.handle_link_new_leaderboard(
                server_config=server_config,
                configure_view=configure_view,
                interaction=interaction,
                guild_id=interaction.guild.id,
                is_new_server=is_new_server,
            )
            return

        if configure_view.unlink_leaderboard_id is not None:
            await self.handle_unlink_leaderboard(
                server_config=server_config,
                configure_view=configure_view,
                interaction=interaction,
                guild_id=interaction.guild.id,
            )
            return


class AddNewIdentityModal(discord.ui.Modal, title="Add new identity for user"):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.i_input = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label="Field identifier (address, NFT, class, etc)",
            required=True,
            placeholder="0x...",
        )
        self.n_input = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label="Short name",
            required=True,
            placeholder="My main address",
        )

        self.add_item(self.i_input)
        self.add_item(self.n_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.stop()
        await interaction.response.defer()


class RemoveIdentityModal(discord.ui.Modal, title="Remove identity"):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.r_i_input = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label="Field identifier",
            required=True,
            placeholder="0x...",
        )
        self.add_item(self.r_i_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.stop()
        await interaction.response.defer()


class UserView(discord.ui.View):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.ident_input: Optional[str] = None
        self.name_input: Optional[str] = None

        self.remove_ident_input: Optional[str] = None

    @discord.ui.button(label="Link new identification")
    async def button_add_new_identity(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        add_new_ident_modal = AddNewIdentityModal()
        await interaction.response.send_modal(add_new_ident_modal)
        await add_new_ident_modal.wait()
        self.ident_input = add_new_ident_modal.i_input
        self.name_input = add_new_ident_modal.n_input
        self.stop()

    @discord.ui.button(label="Unpin the identification")
    async def button_delete_identity(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        remove_ident_modal = RemoveIdentityModal()
        await interaction.response.send_modal(remove_ident_modal)
        await remove_ident_modal.wait()
        self.remove_ident_input = remove_ident_modal.r_i_input
        self.stop()


class UserCog(commands.Cog):
    def __init__(self, bot: LeaderboardDiscordBot):
        self.bot = bot

    async def background_process_add_user_identity(
        self, discord_user_id: int, new_ident: data.UserIdentity
    ) -> None:
        resource = await actions.push_user_identity(
            discord_user_id=discord_user_id,
            identifier=new_ident.identifier,
            name=new_ident.name,
        )
        if resource is None:
            logger.error(
                f"Unable to save resource for user with Discord ID: {str(discord_user_id)} and identifier: {new_ident.identifier}"
            )
            return

        new_ident.resource_id = resource.id

        logger.info(f"Saved user identity as resource with ID: {resource.id}")

    async def background_process_remove_user_identity(
        self, resource_id: uuid.UUID
    ) -> None:
        removed_resource_id = await actions.remove_user_identity(
            resource_id=resource_id
        )

        if removed_resource_id is None:
            logger.error(f"Unable to delete resource with ID: {str(resource_id)}")
            return

        logger.info(
            f"Removed user identity represented as resource with ID: {str(removed_resource_id)}"
        )

    async def handle_add_user_identity(
        self,
        user_view: UserView,
        interaction: discord.Interaction,
        discord_user_id: int,
        user_identities: List[data.UserIdentity],
    ) -> None:
        if str(user_view.ident_input).lower() in [
            i.identifier.lower() for i in user_identities
        ]:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="Identity already attached to your profile"
                ),
                ephemeral=True,
            )
            return

        new_ident = data.UserIdentity(
            resource_id=None,
            identifier=str(user_view.ident_input),
            name=str(user_view.name_input),
        )
        self.bot.user_idents[discord_user_id].append(new_ident)

        logger.info(
            f"Added to {discord_user_id} new identity: {str(user_view.ident_input)} by user Discord {interaction.user} - {interaction.user.id}"
        )

        await interaction.followup.send(
            embed=actions.prepare_dynamic_embed(
                title="New identity linked to Discord account",
                description="",
                fields=[
                    {
                        "field_name": "Identity",
                        "field_value": str(user_view.ident_input),
                    },
                    {
                        "field_name": "Name",
                        "field_value": str(user_view.name_input),
                    },
                ],
            ),
            ephemeral=True,
        )

        self.bot.loop.create_task(
            self.background_process_add_user_identity(
                discord_user_id=discord_user_id,
                new_ident=new_ident,
            )
        )

    async def remove_user_identity(
        self,
        user_view: UserView,
        interaction: discord.Interaction,
        discord_user_id: int,
        user_identities: List[data.UserIdentity],
    ) -> None:
        if len(user_identities) == 0:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="User does not have identities linked to Discord account"
                ),
                ephemeral=True,
            )
            return

        resource_id_to_remove: Optional[uuid.UUID] = None
        updated_identities: List[data.UserIdentity] = []
        for i in user_identities:
            if str(user_view.remove_ident_input).lower() == i.identifier.lower():
                resource_id_to_remove = i.resource_id
                continue

            updated_identities.append(i)

        if resource_id_to_remove is None:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"Identity: {str(user_view.remove_ident_input)} not found in user list"
                ),
            )
            return

        self.bot.user_idents[discord_user_id] = updated_identities

        logger.info(
            f"Removed identity: {str(user_view.remove_ident_input)} from user list"
        )

        await interaction.followup.send(
            embed=actions.prepare_dynamic_embed(
                title="Unlinked identity from Discord account",
                description="",
                fields=[
                    {
                        "field_name": "Identity",
                        "field_value": str(user_view.remove_ident_input),
                    }
                ],
            ),
            ephemeral=True,
        )

        self.bot.loop.create_task(
            self.background_process_remove_user_identity(
                resource_id=resource_id_to_remove,
            )
        )

    @app_commands.command(name="user", description=f"User settings")
    async def user(self, interaction: discord.Interaction):
        logger.info(
            actions.prepare_log_message(
                "/user",
                "SLASH COMMAND",
                interaction.user,
                interaction.guild,
                interaction.channel,
            )
        )

        discord_user_id = interaction.user.id
        user_identities: List[data.UserIdentity] = self.bot.user_idents.get(
            discord_user_id, []
        )
        identity_fields = [
            [
                {
                    "field_name": "Identity",
                    "field_value": i.identifier,
                },
                {
                    "field_name": "Name",
                    "field_value": i.name,
                },
                {"field_name": "\u200B", "field_value": "\u200B"},
            ]
            for i in user_identities
        ]

        user_view = UserView()
        await interaction.response.send_message(
            embed=actions.prepare_dynamic_embed(
                title="Identities linked to current Discord user",
                description=(
                    ""
                    if len(user_identities) != 0
                    else "There are no linked identities"
                ),
                fields=[f for d in identity_fields for f in d],
            ),
            view=user_view,
            ephemeral=True,
        )
        await user_view.wait()

        if user_view.ident_input is not None:
            await self.handle_add_user_identity(
                user_view=user_view,
                interaction=interaction,
                discord_user_id=discord_user_id,
                user_identities=user_identities,
            )
            return

        if user_view.remove_ident_input is not None:
            await self.remove_user_identity(
                user_view=user_view,
                interaction=interaction,
                discord_user_id=discord_user_id,
                user_identities=user_identities,
            )
            return


class PingCog(commands.Cog):
    def __init__(self, bot: LeaderboardDiscordBot):
        self.bot = bot

    def prepare_embed(self) -> discord.Embed:
        return discord.Embed(
            title=f"Bot ping",
            description=f"Bot {LEADERBOARD_DISCORD_BOT_NAME} ping latency is {round(self.bot.latency * 1000)}ms",
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


class LeaderboardCog(commands.Cog):
    def __init__(self, bot: LeaderboardDiscordBot):
        self.bot = bot

    def prepare_embed(
        self,
        l_info: Optional[data.LeaderboardInfo] = None,
        l_scores: Optional[List[data.Score]] = None,
    ) -> discord.Embed:
        table: Optional[str] = None
        if l_scores is not None:
            tabular = actions.TabularData()
            tabular.set_columns(["rank", "address", "score"])
            tabular.add_scores(l_scores)
            table = tabular.render_rst()

        l_description = (
            l_info.description.replace("\\n", "\n") if l_info is not None else ""
        )
        description = f"""
{l_description}

`{table if table is not None else ''}`
"""
        embed = discord.Embed(
            title=l_info.title if l_info is not None else "",
            description=description,
        )

        if l_info is not None:
            embed.url = f"{MOONSTREAM_URL}/leaderboards/?leaderboard_id={l_info.id}"

        return embed

    async def background_process_leaderboard(
        self,
        user: Any,
        channel: Any,
        l_id: str,
    ):
        l_info, l_scores = await actions.process_leaderboard_info_with_scores(l_id=l_id)

        if l_info is None and l_scores is None:
            await channel.send(
                embed=discord.Embed(description=MESSAGE_LEADERBOARD_NOT_FOUND)
            )
            return

        await channel.send(user.mention)
        await channel.send(embed=self.prepare_embed(l_info=l_info, l_scores=l_scores))

    @app_commands.command(
        name="leaderboard",
        description="Leaderboard for on-chain activities",
    )
    async def leaderboard(self, interaction: discord.Interaction, id: str):
        logger.info(
            actions.prepare_log_message(
                "/leaderboard",
                "SLASH COMMAND",
                interaction.user,
                interaction.guild,
                interaction.channel,
            )
        )

        await interaction.response.send_message(
            embed=discord.Embed(description=f"Processing leaderboard with ID {id}")
        )

        self.bot.loop.create_task(
            self.background_process_leaderboard(
                user=interaction.user, channel=interaction.channel, l_id=id
            )
        )

    @leaderboard.autocomplete("id")
    async def leaderboard_autocompletion(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        autocompletion: List[app_commands.Choice[str]] = []

        server_config: Optional[data.ResourceConfig] = None
        if interaction.guild is None:
            return autocompletion

        server_config = self.bot.server_configs.get(interaction.guild.id)

        if server_config is not None:
            for l in server_config.resource_data.leaderboards:
                if current.lower() in l.short_name.lower():
                    autocompletion.append(
                        app_commands.Choice(
                            name=l.short_name, value=str(l.leaderboard_id)
                        )
                    )
        return autocompletion


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


class LeaderboardSelectView(discord.ui.View):
    def __init__(self, leaderboards: List[data.ConfigLeaderboard], *args, **kwargs):
        super().__init__(*args, **kwargs)

        async def select_callback(
            interaction: discord.Interaction, values: List[str]
        ) -> None:
            await self.respond_to_select_leaderboard(
                interaction=interaction, select_items=values
            )

        self.add_item(
            DynamicSelect(
                callback_func=select_callback,
                options=[
                    discord.SelectOption(
                        label=l.short_name, value=str(l.leaderboard_id)
                    )
                    for l in leaderboards
                ],
                placeholder="Choose a leaderboard",
            )
        )

        self.leaderboard_id: Optional[str] = None

    async def respond_to_select_leaderboard(
        self, interaction: discord.Interaction, select_items
    ):
        await interaction.response.defer()

        if len(select_items) != 1:
            logger.error("Wrong selection")
            self.stop()
            return

        self.leaderboard_id = select_items[0]
        self.stop()


class PositionCog(commands.Cog):
    def __init__(self, bot: LeaderboardDiscordBot):
        self.bot = bot

    def prepare_embed(
        self, l_score: data.Score, l_info: Optional[data.LeaderboardInfo] = None
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"Position {f'at {l_info.title} ' if l_info is not None else ''}leaderboard",
            description="",
        )
        embed.add_field(name="Address", value=l_score.address)
        embed.add_field(name="Rank", value=l_score.rank)
        embed.add_field(name="Score", value=l_score.score)

        embed.add_field(
            name="Links",
            value=f"[Address at Starkscan](https://starkscan.co/contract/{str(l_score.address)})",
        )

        return embed

    @app_commands.command(name="position", description="Show user results")
    async def position(self, interaction: discord.Interaction, identity: str):
        logger.info(
            actions.prepare_log_message(
                "/position",
                "SLASH COMMAND",
                interaction.user,
                interaction.guild,
                interaction.channel,
            )
        )

        server_config: Optional[data.ResourceConfig] = None
        if interaction.guild is not None:
            server_config = self.bot.server_configs.get(interaction.guild.id)
        else:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="Could not find a guild, please use command at Discord server"
                )
            )
            return

        if server_config is None:
            await interaction.response.send_message(
                embed=discord.Embed(description=MESSAGE_LEADERBOARD_NOT_FOUND)
            )
            return

        if interaction.channel is None:
            await interaction.response.send_message(
                embed=discord.Embed(description=MESSAGE_CHANNEL_NOT_FOUND)
            )
            return

        leaderboards: List[data.ConfigLeaderboard] = []
        for l in server_config.resource_data.leaderboards:
            for t in l.thread_ids:
                if interaction.channel.id == t:
                    leaderboards.append(l)

        leaderboard_id: Optional[uuid.UUID] = None
        if len(leaderboards) == 1:
            leaderboard_id = leaderboards[0].leaderboard_id
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"Looking for {identity} in leaderboard: {leaderboards[0].short_name}"
                ),
                ephemeral=True,
            )
        elif len(leaderboards) > 1:
            leaderboard_select_view = LeaderboardSelectView(leaderboards)
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="There are multiple leaderboards, pleas select one"
                ),
                view=leaderboard_select_view,
                ephemeral=True,
            )
            await leaderboard_select_view.wait()
            leaderboard_id = uuid.UUID(leaderboard_select_view.leaderboard_id)
        else:
            await interaction.response.send_message(
                embed=discord.Embed(description=MESSAGE_LEADERBOARD_NOT_FOUND)
            )
            return

        l_info, l_score = await actions.process_leaderboard_info_with_position(
            l_id=leaderboard_id, address=identity
        )
        if l_score is None:
            await interaction.followup.send(
                embed=discord.Embed(description=MESSAGE_POSITION_NOT_FOUND)
            )
            return

        await interaction.followup.send(
            embed=self.prepare_embed(
                l_info=l_info,
                l_score=l_score,
            )
        )

    @position.autocomplete("identity")
    async def position_autocompletion(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        autocompletion: List[app_commands.Choice[str]] = []

        if interaction.user is None:
            return autocompletion

        user_identities: List[data.UserIdentity] = self.bot.user_idents.get(
            interaction.user.id, []
        )

        for i in user_identities:
            if (
                current.lower() in i.name.lower()
                or current.lower() in i.identifier.lower()
            ):
                autocompletion.append(
                    app_commands.Choice(
                        name=f"{i.identifier} - {i.name}"[:99],
                        value=i.identifier,
                    )
                )
        return autocompletion
