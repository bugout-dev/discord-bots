import logging
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands
from discord.message import Message

from . import actions, data
from .settings import COLORS, LEADERBOARD_DISCORD_BOT_NAME, MOONSTREAM_URL

logger = logging.getLogger(__name__)

MESSAGE_LEADERBOARD_NOT_FOUND = "Leaderboard not found"


def configure_intents() -> discord.flags.Intents:
    intents = discord.Intents.default()
    intents.message_content = True

    return intents


class LeaderboardDiscordBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.available_cogs = [PingCog, LeaderboardCog]

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
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def prepare_embed(self) -> discord.Embed:
        return discord.Embed(
            title=f"Bot ping",
            description=f"Bot {LEADERBOARD_DISCORD_BOT_NAME} ping latency is {round(self.bot.latency * 1000)}ms",
            color=discord.Color.darker_grey(),
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
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def prepare_leaderboard_embed(
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
            color=discord.Color.darker_grey(),
        )
        # embed.set_thumbnail(
        #     url="https://s3.amazonaws.com/static.simiotics.com/moonstream/assets/favicon.png"
        # )

        # 1 row
        if l_info is not None:
            embed.add_field(
                name="Links",
                value=f"[Leaderboard at Moonstream.to]({MOONSTREAM_URL}/leaderboards/?leaderboard_id={l_info.id})",
            )

        # embed.set_image(url="")

        return embed

    @app_commands.command(
        name="leaderboard",
        description="Leaderboard for on-chain activities",
    )
    async def leaderboard(self, interaction: discord.Interaction, id: str):
        l_info, l_scores = actions.process_leaderboard_info_with_scores(id=id)

        if l_info is None and l_scores is None:
            await interaction.response.send_message(MESSAGE_LEADERBOARD_NOT_FOUND)
            return

        await interaction.response.send_message(
            embed=self.prepare_leaderboard_embed(
                l_info=l_info,
                l_scores=l_scores,
            )
        )
