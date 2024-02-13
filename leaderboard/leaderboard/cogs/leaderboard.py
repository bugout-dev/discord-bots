import logging
from typing import Any, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import actions, data
from ..settings import LEADERBOARD_DISCORD_BOT_NAME, MOONSTREAM_URL

logger = logging.getLogger(__name__)


class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self._slash_command_data = data.SlashCommandData(
            name="leaderboard",
            description="Leaderboard for on-chain activities",
            autocomplete_value="id",
        )

    def slash_command_data(self) -> data.SlashCommandData:
        return self._slash_command_data

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

        try:
            if l_info is None and l_scores is None:
                await channel.send(
                    embed=discord.Embed(description=data.MESSAGE_LEADERBOARD_NOT_FOUND)
                )
                return

            await channel.send(user.mention)
            await channel.send(
                embed=self.prepare_embed(l_info=l_info, l_scores=l_scores)
            )
        except discord.errors.Forbidden:
            await user.send(
                embed=discord.Embed(
                    description=f"Not enough permissions for **{LEADERBOARD_DISCORD_BOT_NAME}** bot to send messages in channel **{channel}** in **{channel.guild}** guild. Please communicate with bot in other channel or ask Discord server administrator to manage bot permissions."
                )
            )
            logger.warning(
                f"Not enough permissions for {LEADERBOARD_DISCORD_BOT_NAME} bot to send messages in channel {channel} - {channel.id} in {channel.guild} guild"
            )
        except Exception as e:
            logger.error(
                f"Unable to send leaderboard results with ID: {str(l_id)} to channel {channel} - {channel.id} in {channel.guild} guild, err: {e}"
            )

    # @app_commands.command(
    #     name="leaderboard",
    #     description="Leaderboard for on-chain activities",
    # )
    async def slash_command_handler(self, interaction: discord.Interaction, id: str):
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

    # @leaderboard.autocomplete("id")
    async def slash_command_autocompletion(
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
