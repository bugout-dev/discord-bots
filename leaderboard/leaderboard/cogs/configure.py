import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Sequence

import discord
from discord import app_commands
from discord.ext import commands
from discord.member import Member
from discord.role import Role

from .. import actions, data
from ..settings import (
    BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG,
    LEADERBOARD_DISCORD_BOT_NAME,
    MOONSTREAM_URL,
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


class RoleSelectView(discord.ui.View):
    def __init__(self, guild_roles: Sequence[Role], *args, **kwargs):
        super().__init__(*args, **kwargs)

        async def select_callback(interaction: discord.Interaction, values: List[str]):
            await self.respond_to_select_role(
                interaction=interaction, select_items=values
            )

        self.add_item(
            actions.DynamicSelect(
                callback_func=select_callback,
                options=[
                    discord.SelectOption(
                        label=f"{r.name}",
                        value=json.dumps({"id": r.id, "name": r.name}),
                    )
                    for r in guild_roles
                ],
                placeholder="Choose a role",
                max_values=5,
            )
        )

        self.selected_roles: List[str] = []

    async def respond_to_select_role(
        self, interaction: discord.Interaction, select_items: List[str]
    ):
        await interaction.response.defer()
        self.selected_roles = select_items
        self.stop()


class ConfigureView(actions.PaginationView):
    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.authorized_roles: List[Dict[str, Any]] = []

        self.leaderboard_id: Optional[discord.ui.TextInput] = None
        self.short_name: Optional[discord.ui.TextInput] = None
        self.channel_ids: Optional[discord.ui.TextInput] = None

        self.unlink_leaderboard_id: Optional[discord.ui.TextInput] = None

    # @discord.ui.button(label="Authorize role")
    # async def button_auth_roles(
    #     self, interaction: discord.Interaction, button: discord.ui.Button
    # ):
    #     if interaction.guild is None:
    #         self.stop()
    #         return
    #     role_select_view = RoleSelectView(guild_roles=interaction.guild.roles)
    #     await interaction.response.send_message(view=role_select_view, ephemeral=True)
    #     await role_select_view.wait()
    #     self.authorized_roles = [json.loads(r) for r in role_select_view.selected_roles]
    #     self.stop()

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

        self._slash_command_data = data.SlashCommandData(
            name="configure",
            description=f"Admin: Configure {LEADERBOARD_DISCORD_BOT_NAME} bot",
        )

    @property
    def slash_command_data(self) -> data.SlashCommandData:
        return self._slash_command_data

    async def create_update_config(self, server_config, updated_leaderboards, guild_id):
        pass

    async def background_process_link_leaderboard(
        self,
        interaction: discord.Interaction,
        new_leaderboard: data.ConfigLeaderboard,
        guild_id: int,
        server_config: Optional[data.ResourceConfig] = None,
    ):
        # Fetch additional info about new leaderboard to link
        l_info = await actions.get_leaderboard_info(l_id=new_leaderboard.leaderboard_id)
        if l_info is None:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"Leaderboard with ID {str(new_leaderboard.leaderboard_id)} not found"
                ),
            )
            return

        new_leaderboard.leaderboard_info = l_info
        if server_config is not None:
            updated_leaderboards = server_config.resource_data.leaderboards[:]
        else:
            updated_leaderboards = []
        updated_leaderboards.append(new_leaderboard)

        resource = await actions.create_or_update_server_config(
            discord_server_id=guild_id,
            leaderboards=updated_leaderboards,
            resource_id=server_config.id if server_config is not None else None,
        )
        if resource is None:
            return

        if server_config is None:
            server_config = data.ResourceConfig(
                id=resource.id,
                resource_data=data.Config(
                    type=BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG,
                    discord_server_id=guild_id,
                    discord_auth_roles=[],
                    leaderboards=updated_leaderboards,
                ),
            )
            self.bot.server_configs[guild_id] = server_config
        else:
            server_config.resource_data.leaderboards.clear()
            server_config.resource_data.leaderboards = updated_leaderboards
            self.bot.server_configs[guild_id] = server_config

        await interaction.followup.send(
            embed=actions.prepare_dynamic_embed(
                title="New leaderboard linked to Discord server",
                description="",
                fields=[
                    {
                        "field_name": "Leaderboard ID",
                        "field_value": str(new_leaderboard.leaderboard_id),
                    },
                    {
                        "field_name": "Name",
                        "field_value": str(new_leaderboard.short_name),
                    },
                    {
                        "field_name": "Channel IDs",
                        "field_value": ", ".join(
                            [str(i) for i in new_leaderboard.channel_ids]
                        ),
                    },
                ],
            ),
        )

    async def background_process_unlink_leaderboard(
        self,
        interaction: discord.Interaction,
        updated_leaderboards: List[data.ConfigLeaderboard],
        unlink_leaderboard_id: str,
        guild_id: int,
        server_config: data.ResourceConfig,
    ):
        resource = await actions.create_or_update_server_config(
            discord_server_id=guild_id,
            leaderboards=updated_leaderboards,
            resource_id=server_config.id if server_config is not None else None,
        )
        if resource is None:
            return

        server_config.resource_data.leaderboards.clear()
        server_config.resource_data.leaderboards = updated_leaderboards

        self.bot.server_configs[guild_id] = server_config

        await interaction.followup.send(
            embed=actions.prepare_dynamic_embed(
                title="Unlinked leaderboard from Discord server",
                description="",
                fields=[
                    {
                        "field_name": "Leaderboard ID",
                        "field_value": str(unlink_leaderboard_id),
                    },
                ],
            ),
        )

    async def background_process_update_auth_roles(
        self,
        interaction: discord.Interaction,
        guild_id: int,
        updated_auth_roles: List[data.ConfigRole],
        server_config: Optional[data.ResourceConfig] = None,
    ) -> None:
        resource = await actions.create_or_update_server_config(
            discord_server_id=guild_id,
            roles=updated_auth_roles,
            resource_id=server_config.id if server_config is not None else None,
        )
        if resource is None:
            return

        if server_config is None:
            server_config = data.ResourceConfig(
                id=resource.id,
                resource_data=data.Config(
                    type=BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG,
                    discord_server_id=guild_id,
                    discord_auth_roles=updated_auth_roles,
                    leaderboards=[],
                ),
            )
            self.bot.server_configs[guild_id] = server_config
        else:
            server_config.resource_data.discord_auth_roles.clear()
            server_config.resource_data.discord_auth_roles = updated_auth_roles
            self.bot.server_configs[guild_id] = server_config

        await interaction.followup.send(
            embed=discord.Embed(
                description=f"Authorized roles: {', '.join([r.name for r in updated_auth_roles])}"
            ),
            ephemeral=True,
        )

    async def handle_update_auth_roles(
        self,
        interaction: discord.Interaction,
        configure_view: ConfigureView,
        guild_id: int,
        server_config: Optional[data.ResourceConfig] = None,
    ) -> None:
        """
        Process Authorize role button.
        """
        updated_auth_roles: List[data.ConfigRole] = []
        updated_auth_role_ids: List[int] = []
        if server_config is not None:
            for r in server_config.resource_data.discord_auth_roles:
                updated_auth_roles.append(r)
                updated_auth_role_ids.append(r.id)

        for new_role in configure_view.authorized_roles:
            if new_role["id"] not in updated_auth_role_ids:
                updated_auth_roles.append(
                    data.ConfigRole(id=new_role["id"], name=new_role["name"])
                )
                updated_auth_role_ids.append(new_role["id"])

        self.bot.loop.create_task(
            self.background_process_update_auth_roles(
                interaction=interaction,
                guild_id=guild_id,
                updated_auth_roles=updated_auth_roles,
                server_config=server_config,
            )
        )

    async def handle_link_new_leaderboard(
        self,
        interaction: discord.Interaction,
        configure_view: ConfigureView,
        guild_id: int,
        server_config: Optional[data.ResourceConfig] = None,
    ) -> None:
        """
        Process Link leaderboard button.
        """
        if server_config is not None:
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

        try:
            leaderboard_id_uuid = uuid.UUID(str(configure_view.leaderboard_id))
        except Exception as e:
            logger.error(e)
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"Incorrect leaderboard UUID format {str(configure_view.leaderboard_id)}"
                ),
            )
            return

        new_leaderboard = data.ConfigLeaderboard(
            leaderboard_id=leaderboard_id_uuid,
            short_name=str(configure_view.short_name),
            channel_ids=channel_ids,
        )

        self.bot.loop.create_task(
            self.background_process_link_leaderboard(
                interaction=interaction,
                new_leaderboard=new_leaderboard,
                guild_id=guild_id,
                server_config=server_config,
            )
        )

    async def handle_unlink_leaderboard(
        self,
        interaction: discord.Interaction,
        configure_view: ConfigureView,
        guild_id: int,
        server_config: Optional[data.ResourceConfig] = None,
    ) -> None:
        """
        Process Unlink leaderboard button.
        """
        if server_config is None:
            return

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

        self.bot.loop.create_task(
            self.background_process_unlink_leaderboard(
                interaction=interaction,
                updated_leaderboards=updated_leaderboards,
                unlink_leaderboard_id=str(configure_view.unlink_leaderboard_id),
                guild_id=guild_id,
                server_config=server_config,
            )
        )

    # @app_commands.command(
    #     name="configure", description=f"Configure {LEADERBOARD_DISCORD_BOT_NAME} bot"
    # )
    async def slash_command_handler(self, interaction: discord.Interaction):
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
                server_config.resource_data.discord_auth_roles
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

        allowed_roles: List[str] = []
        wrapped_fields = []
        if server_config is not None:
            allowed_roles = [
                r.name for r in server_config.resource_data.discord_auth_roles
            ]
            for leaderboard in server_config.resource_data.leaderboards:
                wrapped_fields.append(
                    [
                        {
                            "field_name": "Leaderboard ID",
                            "field_value": f"[{str(leaderboard.leaderboard_id)}]({MOONSTREAM_URL}/leaderboards/?leaderboard_id={leaderboard.leaderboard_id})",
                        },
                        {
                            "field_name": "Short name",
                            "field_value": leaderboard.short_name,
                        },
                        {
                            "field_name": "Channel IDs",
                            "field_value": ", ".join(
                                [str(i) for i in leaderboard.channel_ids]
                            ),
                        },
                    ]
                )

        configure_view = ConfigureView(
            title="Leaderboard bot configuration of Discord server",
            description=f"Allowed roles to manage Discord server configuration: {', '.join(allowed_roles) if len(allowed_roles) > 0 else '**-**'}",
            wrapped_fields=wrapped_fields,
            ephemeral=True,
        )

        # Turn off Unlink leaderboard button if there are no leaderboards attached to Discord server
        if (
            server_config is not None
            and len(server_config.resource_data.leaderboards) != 0
        ):
            configure_view.button_unlink_leaderboard.disabled = False
        else:
            configure_view.button_unlink_leaderboard.disabled = True

        await configure_view.send(interaction)

        await configure_view.wait()

        if len(configure_view.authorized_roles) != 0:
            await self.handle_update_auth_roles(
                interaction=interaction,
                configure_view=configure_view,
                guild_id=interaction.guild.id,
                server_config=server_config,
            )

        if configure_view.leaderboard_id is not None:
            await self.handle_link_new_leaderboard(
                interaction=interaction,
                configure_view=configure_view,
                guild_id=interaction.guild.id,
                server_config=server_config,
            )
            return

        if configure_view.unlink_leaderboard_id is not None:
            await self.handle_unlink_leaderboard(
                interaction=interaction,
                configure_view=configure_view,
                guild_id=interaction.guild.id,
                server_config=server_config,
            )
            return
