import logging
import uuid
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import actions, data

logger = logging.getLogger(__name__)


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
            actions.DynamicSelect(
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
    def __init__(self, bot):
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
                embed=discord.Embed(description=data.MESSAGE_GUILD_NOT_FOUND)
            )
            return

        if server_config is None:
            await interaction.response.send_message(
                embed=discord.Embed(description=data.MESSAGE_LEADERBOARD_NOT_FOUND)
            )
            return

        if interaction.channel is None:
            await interaction.response.send_message(
                embed=discord.Embed(description=data.MESSAGE_CHANNEL_NOT_FOUND)
            )
            return

        leaderboards: List[data.ConfigLeaderboard] = []
        for l in server_config.resource_data.leaderboards:
            for ch in l.channel_ids:
                if interaction.channel.id == ch:
                    leaderboards.append(l)

        leaderboard_id: Optional[uuid.UUID] = None
        if len(leaderboards) == 1:
            leaderboard_id = leaderboards[0].leaderboard_id
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"Looking for **{identity}** in leaderboard **{leaderboards[0].short_name}**"
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
                embed=discord.Embed(description=data.MESSAGE_LEADERBOARD_NOT_FOUND)
            )
            return

        l_info, l_score = await actions.process_leaderboard_info_with_position(
            l_id=leaderboard_id, address=identity
        )
        if l_score is None:
            await interaction.followup.send(
                embed=discord.Embed(description=data.MESSAGE_POSITION_NOT_FOUND)
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
