import logging
import uuid
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands
from discord.member import Member

from .. import actions, data
from ..settings import (
    BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG,
    LEADERBOARD_DISCORD_BOT_NAME,
)

logger = logging.getLogger(__name__)


class LinkLeaderboardModal(discord.ui.Modal, title="Link leaderboard to server"):
    def __init__(self, current_channel_id: Optional[int] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.l_id_input: discord.ui.TextInput = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label="Leaderboard ID",
            required=True,
            placeholder="Leaderboard identification number in UUID format",
        )
        self.l_sn_input: discord.ui.TextInput = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label="Leaderboard name",
            required=True,
            placeholder="Leaderboard short name for autocomplete",
        )
        self.ch_ids_input: discord.ui.TextInput = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label="Comma-separated list of Discord channel IDs ",
            required=False,
            placeholder="Discord channel ID, could be nullable",
            default=str(current_channel_id),
        )

        self.add_item(self.l_id_input)
        self.add_item(self.l_sn_input)
        self.add_item(self.ch_ids_input)

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
    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.leaderboard_id: Optional[discord.ui.TextInput] = None
        self.short_name: Optional[discord.ui.TextInput] = None
        self.channel_ids: Optional[discord.ui.TextInput] = None

        self.unlink_leaderboard_id: Optional[discord.ui.TextInput] = None

    @discord.ui.button(label="Link leaderboard")
    async def button_link_leaderboard(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        link_leaderboard_modal = LinkLeaderboardModal(
            current_channel_id=interaction.channel_id
        )
        await interaction.response.send_modal(link_leaderboard_modal)
        await link_leaderboard_modal.wait()
        self.leaderboard_id = link_leaderboard_modal.l_id_input
        self.short_name = link_leaderboard_modal.l_sn_input
        self.channel_ids = link_leaderboard_modal.ch_ids_input
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
    def __init__(self, bot):
        self.bot = bot

    async def background_process_configure(
        self,
        guild_id: int,
        server_config: data.ResourceConfig,
        updated_leaderboards: List[data.ConfigLeaderboard],
    ) -> None:
        if server_config.id is None:
            resource = await actions.create_server_config(
                discord_server_id=guild_id,
                leaderboards=updated_leaderboards,
            )
            if resource is None:
                logger.error(
                    f"Unable to create resource for new Discord server with ID: {guild_id}"
                )
                del self.bot.server_configs[guild_id]
                return
            server_config.id = resource.id
        else:
            resource = await actions.update_server_config(
                resource_id=server_config.id,
                leaderboards=updated_leaderboards,
            )
            if resource is None:
                logger.error(
                    f"Unable to update resource with ID: {str(server_config.id)} for discord server with ID: {guild_id}"
                )
                return

        server_config.resource_data.leaderboards.clear()
        server_config.resource_data.leaderboards = updated_leaderboards
        self.bot.server_configs[guild_id] = server_config

        logger.info(
            f"Updated server config in resource with ID: {str(server_config.id)} for guild with ID: {guild_id}"
        )

    async def handle_link_new_leaderboard(
        self,
        server_config: data.ResourceConfig,
        configure_view: ConfigureView,
        interaction: discord.Interaction,
        guild_id: int,
    ) -> None:
        """
        Process Link leaderboard button.
        """
        for l in server_config.resource_data.leaderboards:
            if str(l.leaderboard_id) == str(configure_view.leaderboard_id):
                await interaction.followup.send(
                    embed=discord.Embed(
                        description=f"Leaderboard with ID: **{str(l.leaderboard_id)}** already linked to this Discord server"
                    ),
                )
                return

        channel_ids_str_set = set()
        channel_ids_raw = configure_view.channel_ids
        if channel_ids_raw is not None:
            channel_ids_str_set = set(str(channel_ids_raw).replace(" ", "").split(","))
        channel_ids = []
        for x in channel_ids_str_set:
            try:
                channel_ids.append(int(x))
            except Exception as e:
                logger.warning(f"Unable to parse channel ID {x} from input to integer")
                continue

        updated_leaderboards = server_config.resource_data.leaderboards[:]
        updated_leaderboards.append(
            data.ConfigLeaderboard(
                leaderboard_id=uuid.UUID(str(configure_view.leaderboard_id)),
                short_name=str(configure_view.short_name),
                channel_ids=channel_ids,
            )
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
                        "field_name": "Name",
                        "field_value": str(configure_view.short_name),
                    },
                    {
                        "field_name": "Channel IDs",
                        "field_value": ", ".join([str(i) for i in channel_ids]),
                    },
                ],
            ),
        )

        self.bot.loop.create_task(
            self.background_process_configure(
                guild_id=guild_id,
                server_config=server_config,
                updated_leaderboards=updated_leaderboards,
            )
        )

    async def handle_unlink_leaderboard(
        self,
        server_config: data.ResourceConfig,
        configure_view: ConfigureView,
        interaction: discord.Interaction,
        guild_id: int,
    ) -> None:
        """
        Process Unlink leaderboard button.
        """
        is_unlink = False
        updated_leaderboards: List[data.ConfigLeaderboard] = []
        for l in server_config.resource_data.leaderboards:
            if str(l.leaderboard_id) == str(configure_view.unlink_leaderboard_id):
                is_unlink = True
                continue

            updated_leaderboards.append(l)

        if is_unlink is False:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"Leaderboard with ID: **{str(configure_view.unlink_leaderboard_id)}** not found in linked to this Discord server"
                ),
            )
            return

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
                updated_leaderboards=updated_leaderboards,
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
                embed=discord.Embed(description=data.MESSAGE_GUILD_NOT_FOUND)
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
                embed=discord.Embed(description=data.MESSAGE_ACCESS_DENIED)
            )
            return

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

        configure_view = ConfigureView()

        # Turn off Unlink leaderboard button if there are no leaderboards attached to Discord server
        configure_view.button_unlink_leaderboard.disabled = (
            True if len(server_config.resource_data.leaderboards) == 0 else False
        )

        allowed_roles: List[str] = [
            r.name for r in server_config.resource_data.discord_roles
        ]

        await interaction.response.send_message(
            embed=actions.prepare_dynamic_embed(
                title="Leaderboard bot configuration of Discord server",
                description=f"Allowed roles to manage Discord server configuration: {', '.join(allowed_roles) if len(allowed_roles) > 0 else '**-**'}",
                fields=[
                    d
                    for l in server_config.resource_data.leaderboards
                    for d in [
                        {
                            "field_name": "Leaderboard ID",
                            "field_value": str(l.leaderboard_id),
                        },
                        {
                            "field_name": "Name",
                            "field_value": l.short_name,
                        },
                        {
                            "field_name": "Channel IDs",
                            "field_value": ", ".join([str(i) for i in l.channel_ids]),
                        },
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
