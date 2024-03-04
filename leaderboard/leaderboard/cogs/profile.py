import logging
import uuid
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import actions, data

logger = logging.getLogger(__name__)


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
            label="Name",
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


class ProfileCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self._slash_command_data = data.SlashCommandData(
            name="profile",
            description="Create and manage bot profile addresses and IDs",
        )

    @property
    def slash_command_data(self) -> data.SlashCommandData:
        return self._slash_command_data

    async def background_process_add_user_identity(
        self,
        interaction: discord.Interaction,
        discord_user_id: int,
        new_ident: data.UserIdentity,
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
            await interaction.followup.send(
                embed=discord.Embed(description=data.MESSAGE_INTERNAL_SERVER_ERROR)
            )
            return

        new_ident.resource_id = resource.id

        if self.bot.user_idents.get(discord_user_id) is None:
            self.bot.user_idents[discord_user_id] = [new_ident]
        else:
            self.bot.user_idents[discord_user_id].append(new_ident)

        await interaction.followup.send(
            embed=actions.prepare_dynamic_embed(
                title="New identity linked to Discord account",
                description="",
                fields=[
                    {
                        "field_name": "Identity",
                        "field_value": str(new_ident.identifier),
                    },
                    {
                        "field_name": "Name",
                        "field_value": str(new_ident.name),
                    },
                ],
            ),
            ephemeral=True,
        )

        logger.info(
            f"Added new identity: {new_ident.identifier} to user with ID: {discord_user_id}"
        )

    async def background_process_remove_user_identity(
        self,
        interaction: discord.Interaction,
        discord_user_id: int,
        ident_to_remove: data.UserIdentity,
        updated_identities: List[data.UserIdentity],
    ) -> None:
        removed_resource_id: Optional[uuid.UUID] = None
        if ident_to_remove.resource_id is not None:
            removed_resource_id = await actions.remove_user_identity(
                resource_id=ident_to_remove.resource_id
            )
        if removed_resource_id is None:
            logger.error(
                f"Unable to delete resource with ID: {str(ident_to_remove.resource_id)}"
            )
            await interaction.followup.send(
                embed=discord.Embed(description=data.MESSAGE_INTERNAL_SERVER_ERROR)
            )
            return

        self.bot.user_idents[discord_user_id] = updated_identities

        await interaction.followup.send(
            embed=actions.prepare_dynamic_embed(
                title="Unlinked identity from Discord account",
                description="",
                fields=[
                    {
                        "field_name": "Identity",
                        "field_value": str(ident_to_remove.name),
                    }
                ],
            ),
            ephemeral=True,
        )

        logger.info(
            f"Removed identity: {ident_to_remove.identifier} from user with ID: {discord_user_id}"
        )

    async def handle_add_user_identity(
        self,
        user_view: UserView,
        interaction: discord.Interaction,
        discord_user_id: int,
        user_identities: List[data.UserIdentity],
    ) -> None:
        if str(user_view.ident_input) in [i.identifier for i in user_identities]:
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

        self.bot.loop.create_task(
            self.background_process_add_user_identity(
                interaction=interaction,
                discord_user_id=discord_user_id,
                new_ident=new_ident,
            )
        )

    async def handle_remove_user_identity(
        self,
        user_view: UserView,
        interaction: discord.Interaction,
        discord_user_id: int,
        user_identities: List[data.UserIdentity],
    ) -> None:
        if len(user_identities) == 0:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="User does not have any identity linked to Discord account"
                ),
                ephemeral=True,
            )
            return

        ident_to_remove: Optional[data.UserIdentity] = None
        updated_identities: List[data.UserIdentity] = []
        for i in user_identities:
            if str(user_view.remove_ident_input) == i.identifier:
                ident_to_remove = i
                continue

            updated_identities.append(i)

        if ident_to_remove is None:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"Identity: **{str(user_view.remove_ident_input)}** not found in user list",
                ),
                ephemeral=True,
            )
            return

        self.bot.loop.create_task(
            self.background_process_remove_user_identity(
                interaction=interaction,
                discord_user_id=discord_user_id,
                ident_to_remove=ident_to_remove,
                updated_identities=updated_identities,
            )
        )

    # @app_commands.command(name="user", description=f"User settings")
    async def slash_command_handler(self, interaction: discord.Interaction):
        logger.info(
            actions.prepare_log_message(
                "/profile",
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
        # TODO(kompotkot): Pagination
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

        # Turn off Unpin the identification button if there are no identities attached to Discord user
        user_view.button_delete_identity.disabled = (
            True if len(user_identities) == 0 else False
        )

        await interaction.response.send_message(
            embed=actions.prepare_dynamic_embed(
                title="Identities linked to Discord user",
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
            await self.handle_remove_user_identity(
                user_view=user_view,
                interaction=interaction,
                discord_user_id=discord_user_id,
                user_identities=user_identities,
            )
            return
