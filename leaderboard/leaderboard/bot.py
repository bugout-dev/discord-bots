import logging
import uuid
from typing import List, Optional, Union

import discord
from discord import app_commands
from discord.ext import commands
from discord.message import Message

from . import actions, data
from .settings import COLORS, LEADERBOARD_DISCORD_BOT_NAME, MOONSTREAM_URL

logger = logging.getLogger(__name__)

MESSAGE_LEADERBOARD_NOT_FOUND = "Leaderboard not found"
MESSAGE_POSITION_NOT_FOUND = "Leaderboard position not found"
MESSAGE_CHANNEL_NOT_FOUND = "Discord channel not found"


def configure_intents() -> discord.flags.Intents:
    intents = discord.Intents.default()
    intents.message_content = True

    return intents


class LeaderboardDiscordBot(commands.Bot):
    def __init__(self, config: data.Config, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.config: data.Config = config
        self.available_cogs = [PingCog, LeaderboardCog, PositionCog]

    async def on_ready(self):
        logger.info(
            f"Logged in {COLORS.BLUE}{str(len(self.guilds))}{COLORS.RESET} guilds on as {COLORS.BLUE}{self.user}{COLORS.RESET} "
        )

    async def setup_hook(self):
        for c in self.available_cogs:
            await self.add_cog(c(self))

        synced = await self.tree.sync()
        logger.info(f"Slash commands synced: {len(synced)}")

    async def on_message(self, message: Message):
        logger.debug(
            f"{COLORS.GREEN}[MESSAGE]{COLORS.RESET} Guild: {COLORS.BLUE}{message.guild}{COLORS.RESET} Channel: {COLORS.BLUE}{message.channel}{COLORS.RESET} "
            f"Author: {COLORS.BLUE}{message.author}{COLORS.RESET} Content: {message.content}"
        )
        await self.process_commands(message)


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
            f"{COLORS.GREEN}[COMMAND]{COLORS.RESET} {COLORS.BLUE}/ping{COLORS.RESET} Guild: {COLORS.BLUE}{ctx.guild}{COLORS.RESET} Channel: {COLORS.BLUE}{ctx.channel}{COLORS.RESET} "
        )
        await ctx.send(embed=self.prepare_embed())

    # https://discordpy.readthedocs.io/en/stable/interactions/api.html?highlight=app_commands%20command#discord.app_commands.command
    @app_commands.command(
        name="ping", description=f"Ping pong with {LEADERBOARD_DISCORD_BOT_NAME}"
    )
    async def _ping(self, interaction: discord.Interaction):
        logger.info(
            f"{COLORS.GREEN}[SLASH COMMAND]{COLORS.RESET} {COLORS.BLUE}/ping{COLORS.RESET} Guild: {COLORS.BLUE}{interaction.guild}{COLORS.RESET} Channel: {COLORS.BLUE}{interaction.channel}{COLORS.RESET} "
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

    async def background_process(
        self,
        user: discord.user.User,
        channel: discord.channel.TextChannel,
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
    async def leaderboard(self, interaction: discord.Interaction, leaderboard_id: str):
        logger.info(
            f"{COLORS.GREEN}[SLASH COMMAND]{COLORS.RESET} {COLORS.BLUE}/leaderboard{COLORS.RESET} Guild: {COLORS.BLUE}{interaction.guild}{COLORS.RESET} Channel: {COLORS.BLUE}{interaction.channel}{COLORS.RESET} "
        )

        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"Processing leaderboard with ID {leaderboard_id}"
            )
        )

        self.bot.loop.create_task(
            self.background_process(
                user=interaction.user, channel=interaction.channel, l_id=leaderboard_id
            )
        )


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

    @app_commands.command(name="position", description=f"Show user results")
    async def position(self, interaction: discord.Interaction, address: str):
        logger.info(
            f"{COLORS.GREEN}[SLASH COMMAND]{COLORS.RESET} {COLORS.BLUE}/position{COLORS.RESET} Guild: {COLORS.BLUE}{interaction.guild}{COLORS.RESET} Channel: {COLORS.BLUE}{interaction.channel}{COLORS.RESET} "
        )
        if self.bot.config == []:
            await interaction.response.send_message(
                embed=discord.Embed(description=MESSAGE_LEADERBOARD_NOT_FOUND)
            )
            return

        if interaction.channel is None:
            await interaction.response.send_message(
                embed=discord.Embed(description=MESSAGE_CHANNEL_NOT_FOUND)
            )
            return

        l_id: Optional[uuid.UUID] = None
        for th in self.bot.config.leaderboard_threads:
            if interaction.channel.id == th.thread_id:
                l_id = th.leaderboard_id
        if l_id is None:
            await interaction.response.send_message(
                embed=discord.Embed(description=MESSAGE_LEADERBOARD_NOT_FOUND)
            )
            return

        l_info, l_score = await actions.process_leaderboard_info_with_position(
            l_id=l_id, address=address
        )
        if l_score is None:
            await interaction.response.send_message(
                embed=discord.Embed(description=MESSAGE_POSITION_NOT_FOUND)
            )
            return

        await interaction.response.send_message(
            embed=self.prepare_embed(
                l_info=l_info,
                l_score=l_score,
            )
        )
