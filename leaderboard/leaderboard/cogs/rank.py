import logging
import uuid
from typing import List, Optional, Union

import discord
from discord import app_commands
from discord.ext import commands

from .. import actions, data
from ..settings import MOONSTREAM_LOGO_URL

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
        self, interaction: discord.Interaction, select_items: List[str]
    ):
        await interaction.response.defer()

        if len(select_items) != 1:
            logger.error("Wrong selection")
            self.stop()
            return

        self.leaderboard_id = select_items[0]
        self.stop()


class RankCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self._slash_command_data = data.SlashCommandData(
            name="rank",
            description="Check current rank on a leaderboard",
            autocomplete_value="identity",
        )

    @property
    def slash_command_data(self) -> data.SlashCommandData:
        return self._slash_command_data

    def prepare_embed(
        self, l_score: data.Score, l_info: Optional[data.LeaderboardInfo] = None
    ) -> discord.Embed:
        # TODO(kompotkot): Write normal score_details parser

        score_details_raw = l_score.points_data.get("score_details", {})

        address_name = "Identity"
        score = str(l_score.score)
        try:
            # Score field render
            score_details = data.ScoreDetails(**score_details_raw)
            score_updated = ""
            if score_details.prefix is not None:
                score_updated += score_details.prefix
            if (
                score_details.conversion is not None
                and score_details.conversion_vector is not None
            ):
                score_converted = actions.score_converter(
                    source=l_score.score,
                    conversion=score_details.conversion,
                    conversion_vector=score_details.conversion_vector,
                )
                score_updated += str(score_converted)
            else:
                score_updated += str(l_score.score)

            if score_details.postfix is not None:
                score_updated += score_details.postfix

            score = score_updated
        except:
            pass

        try:
            # Identity render
            if score_details.address_name is not None:
                address_name = score_details.address_name
        except:
            pass

        description = ""
        is_complete = l_score.points_data.get("complete")
        if is_complete is not None:
            description += "Requirement: Complete\n"

        must_reach = l_score.points_data.get("must_reach")
        must_reach_counter = l_score.points_data.get("must_reach_counter")
        must_reach_line = ""
        if must_reach is not None and must_reach_counter is not None:
            must_reach_line += f"Must Reach: {must_reach_counter} / {must_reach}"
            must_reach_line += "\n"

        cap = l_score.points_data.get("cap")
        cap_line = ""
        if cap is not None:
            cap_line += f"Cap: {cap}"

        try:
            # Description render
            score_details = data.ScoreDetails(**score_details_raw)
            if (
                score_details.conversion is not None
                and score_details.conversion_vector is not None
            ):
                if must_reach is not None and must_reach_counter is not None:
                    must_reach_converted = actions.score_converter(
                        source=must_reach,
                        conversion=score_details.conversion,
                        conversion_vector=score_details.conversion_vector,
                    )
                    must_reach_counter_converted = actions.score_converter(
                        source=must_reach_counter,
                        conversion=score_details.conversion,
                        conversion_vector=score_details.conversion_vector,
                    )
                cap_converted = actions.score_converter(
                    source=cap,
                    conversion=score_details.conversion,
                    conversion_vector=score_details.conversion_vector,
                )

                must_reach_line = f"Must Reach: {must_reach_counter_converted} / {int(must_reach_converted)}"
                cap_line = f"Cap: {int(cap_converted)}"
                if score_details.postfix is not None:
                    must_reach_line += score_details.postfix
                    cap_line += score_details.postfix
                must_reach_line += "\n"
        except:
            pass

        description += must_reach_line
        description += cap_line

        embed = discord.Embed(
            title=f"Rank{f' at {l_info.title}' if l_info is not None else ''}",
            description=description,
        )
        embed.add_field(name="Rank", value=l_score.rank)
        embed.add_field(name=address_name, value=l_score.address)
        embed.add_field(name="Score", value=score)

        embed.set_footer(text="Powered by Moonstream")

        return embed

    # @app_commands.command(name="rank", description="Show user results")
    async def slash_command_handler(
        self, interaction: discord.Interaction, identity: str
    ):
        logger.info(
            actions.prepare_log_message(
                "/rank",
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
        leaderboards_len = len(leaderboards)
        if leaderboards_len == 1:
            leaderboard_id = leaderboards[0].leaderboard_id
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"Looking for **{identity}** in **{leaderboards[0].short_name}**"
                ),
                ephemeral=True,
            )
        elif leaderboards_len > 1:
            if leaderboards_len >= 25:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description="Too many leaderboards linked to channel, please connect to Discord server administrator"
                    )
                )
                return
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

        l_info, l_score = await actions.process_leaderboard_info_with_score(
            l_id=leaderboard_id, address=identity
        )
        if l_score is None:
            await interaction.followup.send(
                embed=discord.Embed(description=data.MESSAGE_RANK_NOT_FOUND),
                ephemeral=True,
            )
            return

        embed = self.prepare_embed(
            l_info=l_info,
            l_score=l_score,
        )

        if server_config.resource_data.thumbnail_url is not None:
            embed.set_thumbnail(url=server_config.resource_data.thumbnail_url)

        await interaction.followup.send(
            embed=embed,
        )

    # @slash_command_handler.autocomplete("identity")
    async def slash_command_autocompletion(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        autocompletion: List[app_commands.Choice[str]] = []

        if interaction.user is None:
            return autocompletion

        user_identities: List[data.UserIdentity] = self.bot.user_idents.get(
            interaction.user.id, []
        )

        cnt = 0
        for i in user_identities:
            if cnt >= 20:
                break
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
                cnt += 1
        return autocompletion
