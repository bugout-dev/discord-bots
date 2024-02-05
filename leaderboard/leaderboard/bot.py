import logging
import uuid
from typing import List, Optional, Union

import discord
from discord import app_commands
from discord.ext import commands
from discord.message import Message

from . import actions, data
from .settings import (
    COLORS,
    MOONSTREAM_APPLICATION_ID,
    MOONSTREAN_DISCORD_BOT_ACCESS_TOKEN,
    LEADERBOARD_DISCORD_BOT_NAME,
    MOONSTREAM_URL,
    BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG,
    bugout_client as bc,
)

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

        self.configs: List[data.Config] = []
        self.available_cogs = [
            PingCog,
            LeaderboardCog,
            PositionCog,
            ConfigureCog,
            AccountCog,
        ]

    async def on_ready(self):
        logger.info(
            f"Logged in {COLORS.BLUE}{str(len(self.guilds))}{COLORS.RESET} guilds on as {COLORS.BLUE}{self.user}{COLORS.RESET}"
        )

    async def setup_hook(self):
        for c in self.available_cogs:
            await self.add_cog(c(self))

        synced = await self.tree.sync()
        logger.info(f"Slash commands synced: {len(synced)}")

    async def on_message(self, message: Message):
        print("wtf", message.guild.id)
        config = await self.get_server_bugout_config(message.guild.id)
        if config is not None:
            print(config.discord_roles)

        logger.debug(
            f"{COLORS.GREEN}[MESSAGE]{COLORS.RESET} Guild: {COLORS.BLUE}{message.guild}{COLORS.RESET} Channel: {COLORS.BLUE}{message.channel}{COLORS.RESET}"
            f"Author: {COLORS.BLUE}{message.author}{COLORS.RESET} Content: {message.content}"
        )

        await self.process_commands(message)

    def load_bugout_configs(self) -> None:
        try:
            response = bc.list_resources(
                token=MOONSTREAN_DISCORD_BOT_ACCESS_TOKEN,
                params={
                    "application_id": MOONSTREAM_APPLICATION_ID,
                    "type": BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG,
                },
            )

            configs = [data.Config(**r.resource_data) for r in response.resources]
        except Exception as e:
            raise Exception(e)

        self.configs = configs

    async def get_server_bugout_config(self, server_id: str) -> Optional[data.Config]:
        for c in self.configs:
            if c.discord_server_id == server_id:
                return c
        return None


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
        self.th_id_input = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label="Discord thread ID",
            required=False,
            placeholder="Discord thread ID, could be nullable",
        )

        self.add_item(self.l_id_input)
        self.add_item(self.l_sn_input)
        self.add_item(self.th_id_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.stop()
        await interaction.response.defer()

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        self.stop()
        await interaction.response.send_message(content="Error!")


class ConfigureView(discord.ui.View):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.leaderboard_id: Optional[str] = None
        self.short_name: Optional[str] = None
        self.thread_id: Optional[str] = None

    @discord.ui.button(label="Link leaderboard")
    async def button_link_leaderboard(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        link_leaderboard_modal = LinkLeaderboardModal()
        await interaction.response.send_modal(link_leaderboard_modal)
        await link_leaderboard_modal.wait()
        self.leaderboard_id = link_leaderboard_modal.l_id_input
        self.short_name = link_leaderboard_modal.l_sn_input
        self.thread_id = link_leaderboard_modal.th_id_input
        self.stop()

    @discord.ui.button(label="Unlink leaderboard")
    async def button_unlink_leaderboard(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(content="Unlink leaderboard pressed")


class ConfigureCog(commands.Cog):
    def __init__(self, bot: LeaderboardDiscordBot):
        self.bot = bot

    @app_commands.command(
        name="configure", description=f"Configure {LEADERBOARD_DISCORD_BOT_NAME} bot"
    )
    async def configure(self, interaction: discord.Interaction):
        logger.info(
            f"{COLORS.GREEN}[SLASH COMMAND]{COLORS.RESET} {COLORS.BLUE}/configure{COLORS.RESET} Guild: {COLORS.BLUE}{interaction.guild}{COLORS.RESET} Channel: {COLORS.BLUE}{interaction.channel}{COLORS.RESET}"
        )

        server_config = await self.bot.get_server_bugout_config(
            server_id=interaction.guild.id
        )
        if server_config is not None:
            linked_leaderboards_str_list = [
                f"{l.leaderboard_id} - {l.short_name}"
                for l in server_config.leaderboards
            ]

        configure_view = ConfigureView()
        await interaction.response.send_message(
            content="\n".join(linked_leaderboards_str_list), view=configure_view
        )
        await configure_view.wait()

        is_linked = False
        if server_config is not None:
            for l in server_config.leaderboards:
                if l.leaderboard_id == configure_view.leaderboard_id:
                    is_linked = True
                    print("Leaderboard already linked")

        if is_linked is False:
            server_config.leaderboards.append(
                data.ConfigLeaderboard(
                    leaderboard_id=uuid.UUID(str(configure_view.leaderboard_id)),
                    short_name=str(configure_view.short_name),
                    thread_ids=[],
                )
            )
            print("Linked new leaderboard")


class AccountCog(commands.Cog):
    def __init__(self, bot: LeaderboardDiscordBot):
        self.bot = bot

    @app_commands.command(name="account", description=f"Account settings")
    async def account(self, interaction: discord.Interaction):
        logger.info(
            f"{COLORS.GREEN}[SLASH COMMAND]{COLORS.RESET} {COLORS.BLUE}/account{COLORS.RESET} Guild: {COLORS.BLUE}{interaction.guild}{COLORS.RESET} Channel: {COLORS.BLUE}{interaction.channel}{COLORS.RESET}"
        )
        await interaction.response.send_message(
            content="Account here", view=ConfigureView()
        )


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
            f"{COLORS.GREEN}[COMMAND]{COLORS.RESET} {COLORS.BLUE}/ping{COLORS.RESET} Guild: {COLORS.BLUE}{ctx.guild}{COLORS.RESET} Channel: {COLORS.BLUE}{ctx.channel}{COLORS.RESET}"
        )
        await ctx.send(embed=self.prepare_embed())

    # https://discordpy.readthedocs.io/en/stable/interactions/api.html?highlight=app_commands%20command#discord.app_commands.command
    @app_commands.command(
        name="ping", description=f"Ping pong with {LEADERBOARD_DISCORD_BOT_NAME}"
    )
    async def _ping(self, interaction: discord.Interaction):
        logger.info(
            f"{COLORS.GREEN}[SLASH COMMAND]{COLORS.RESET} {COLORS.BLUE}/ping{COLORS.RESET} Guild: {COLORS.BLUE}{interaction.guild}{COLORS.RESET} Channel: {COLORS.BLUE}{interaction.channel}{COLORS.RESET}"
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
    async def leaderboard(self, interaction: discord.Interaction, id: str):
        logger.info(
            f"{COLORS.GREEN}[SLASH COMMAND]{COLORS.RESET} {COLORS.BLUE}/leaderboard{COLORS.RESET} Guild: {COLORS.BLUE}{interaction.guild}{COLORS.RESET} Channel: {COLORS.BLUE}{interaction.channel}{COLORS.RESET}"
        )

        await interaction.response.send_message(
            embed=discord.Embed(description=f"Processing leaderboard with ID {id}")
        )

        self.bot.loop.create_task(
            self.background_process(
                user=interaction.user, channel=interaction.channel, l_id=id
            )
        )

    @leaderboard.autocomplete("id")
    async def leaderboard_autocompletion(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        data = []
        server_config = await self.bot.get_server_bugout_config(
            server_id=interaction.guild.id
        )
        if server_config is not None:
            for l in server_config.leaderboards:
                if current.lower() in l.short_name.lower():
                    data.append(
                        app_commands.Choice(
                            name=l.short_name, value=str(l.leaderboard_id)
                        )
                    )
        return data


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
            f"{COLORS.GREEN}[SLASH COMMAND]{COLORS.RESET} {COLORS.BLUE}/position{COLORS.RESET} Guild: {COLORS.BLUE}{interaction.guild}{COLORS.RESET} Channel: {COLORS.BLUE}{interaction.channel}{COLORS.RESET}"
        )
        server_config = await self.bot.get_server_bugout_config(
            server_id=interaction.guild.id
        )

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

        l_id: Optional[uuid.UUID] = None
        for l in server_config.leaderboards:
            for t in l.thread_ids:
                if interaction.channel.id == t:
                    l_id = l.leaderboard_id
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
