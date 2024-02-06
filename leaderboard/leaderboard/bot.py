import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Union

import discord
from bugout.data import BugoutSearchResult, BugoutSearchResultAsEntity
from discord import app_commands
from discord.ext import commands
from discord.message import Message

from . import actions, data
from .settings import (
    BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG,
    COLORS,
    LEADERBOARD_DISCORD_BOT_NAME,
    LEADERBOARD_DISCORD_BOT_USERS_JOURNAL_ID,
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
        self.linked_users: Dict[int, data.User] = {}

        self.available_cogs = [
            PingCog,
            LeaderboardCog,
            PositionCog,
            ConfigureCog,
            UserCog,
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
        if message.guild is not None:
            if message.guild.owner == message.author:
                print("Owner is speaking")

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
            response = bc.search(
                token=MOONSTREAN_DISCORD_BOT_ACCESS_TOKEN,
                journal_id=LEADERBOARD_DISCORD_BOT_USERS_JOURNAL_ID,
                query="tag:type:user-link",
                limit=100,
                content=True,
                representation="entity",
            )
            logger.info(f"Fetched configuration of {response.total_results} users")
            results: List[BugoutSearchResultAsEntity] = response.results  # type: ignore
            for rec in results:
                try:
                    user_discord_id = int(
                        list(
                            filter(
                                lambda x: x.get("discord-user-id") is not None,
                                rec.required_fields,
                            )
                        )[0]["discord-user-id"]
                    )
                    user = self.linked_users[user_discord_id]
                except KeyError:
                    user = data.User(
                        discord_id=user_discord_id,
                        addresses=[],
                    )
                    self.linked_users[user_discord_id] = user
                except Exception:
                    logger.error(f"Wrong format of entity: {rec.entity_url}")
                    continue

                user.addresses.append(
                    data.UserAddress(
                        address=str(rec.address),
                        blockchain=str(rec.blockchain),
                        description=rec.secondary_fields.get("description", ""),
                    )
                )

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


class ConfigureView(discord.ui.View):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.leaderboard_id: Optional[str] = None
        self.short_name: Optional[str] = None
        self.thread_ids: Optional[str] = None

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
        await interaction.response.send_message(content="Unlink leaderboard pressed")


class ConfigureCog(commands.Cog):
    def __init__(self, bot: LeaderboardDiscordBot):
        self.bot = bot

    async def background_process(
        self, guild_id: int, server_config: data.ResourceConfig
    ) -> None:
        resource = await actions.push_server_config(
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

    @app_commands.command(
        name="configure", description=f"Configure {LEADERBOARD_DISCORD_BOT_NAME} bot"
    )
    async def configure(self, interaction: discord.Interaction):
        logger.info(
            f"{COLORS.GREEN}[SLASH COMMAND]{COLORS.RESET} {COLORS.BLUE}/configure{COLORS.RESET} Guild: {COLORS.BLUE}{interaction.guild}{COLORS.RESET} Channel: {COLORS.BLUE}{interaction.channel}{COLORS.RESET}"
        )

        server_config: Optional[data.ResourceConfig] = None
        if interaction.guild is not None:
            server_config = self.bot.server_configs.get(interaction.guild.id)
        else:
            await interaction.response.send_message(
                content="Could not find a guild to configure, please use command at Discord server"
            )
            return

        if server_config is not None:
            linked_leaderboards_str_list = [
                f"{l.leaderboard_id} - {l.short_name}"
                for l in server_config.resource_data.leaderboards
            ]
        else:
            server_config = data.ResourceConfig(
                id=uuid.uuid4(),
                resource_data=data.Config(
                    type=BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG,
                    discord_server_id=interaction.guild.id,
                    discord_roles=[],
                    leaderboards=[],
                ),
            )

        configure_view = ConfigureView()
        await interaction.response.send_message(
            content="\n".join(linked_leaderboards_str_list), view=configure_view
        )
        await configure_view.wait()

        if server_config is not None:
            for l in server_config.resource_data.leaderboards:
                if l.leaderboard_id == str(configure_view.leaderboard_id):
                    await interaction.followup.send(
                        content=f"Leaderboard with ID: {str(l.leaderboard_id)} already linked"
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
            f"Linked new leaderboard with ID: {str(l.leaderboard_id)} in discord server {interaction.guild.id}"
        )
        await interaction.followup.send(
            content=f"Linked leaderboard with ID: {str(l.leaderboard_id)}"
        )

        self.bot.loop.create_task(
            self.background_process(
                guild_id=interaction.guild.id,
                server_config=server_config,
            )
        )


class AddNewAddressModal(discord.ui.Modal, title="Add new address for user"):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.a_input = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label="Blockchain address",
            required=True,
            placeholder="0x...",
        )
        self.d_input = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label="Address short description",
            required=True,
            placeholder="My main address",
        )

        self.add_item(self.a_input)
        self.add_item(self.d_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.stop()
        await interaction.response.defer()


class UserView(discord.ui.View):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.address_input: Optional[str] = None
        self.description_input: Optional[str] = None

    @discord.ui.button(label="Add new address")
    async def button_add_new_address(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        add_new_address_modal = AddNewAddressModal()
        await interaction.response.send_modal(add_new_address_modal)
        await add_new_address_modal.wait()
        self.address_input = add_new_address_modal.a_input
        self.description_input = add_new_address_modal.d_input
        self.stop()

    @discord.ui.button(label="Delete address")
    async def button_delete_address(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(content="Delete address pressed")


class UserCog(commands.Cog):
    def __init__(self, bot: LeaderboardDiscordBot):
        self.bot = bot

    async def background_process(
        self, user_id: int, new_address: data.UserAddress
    ) -> None:
        entity = await actions.push_user_address(
            user_id=user_id,
            address=new_address.address,
            description=new_address.description,
        )
        if entity is None:
            logger.error(
                f"Unable to save entity for user with discord ID: {str(user_id)} and address: {new_address.address}"
            )
            return
        logger.info(f"Saved user address as entity with ID: {entity.id}")

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

        user: Optional[data.User] = None
        if interaction.user.id in self.bot.linked_users:
            user = self.bot.linked_users[interaction.user.id]

        content = "Unknown user"
        if user is not None:
            address = [f"{a.address} - {a.description}" for a in user.addresses]
            content = "\n".join(address)

        user_view = UserView()
        await interaction.response.send_message(
            content=content, view=user_view, ephemeral=True
        )
        await user_view.wait()

        if user is None:
            user = data.User(discord_id=interaction.user.id, addresses=[])
            self.bot.linked_users[interaction.user.id] = user

        if str(user_view.address_input).lower() not in [
            a.address.lower() for a in user.addresses
        ]:
            new_address = data.UserAddress(
                address=str(user_view.address_input),
                blockchain="any",
                description=str(user_view.description_input),
            )
        else:
            await interaction.followup.send(
                content="Address already attached to your profile", ephemeral=True
            )
            return

        user.addresses.append(new_address)
        logger.info(
            f"Added new address: {str(user_view.address_input)} by user {interaction.user} - {interaction.user.id}"
        )
        await interaction.followup.send(
            content=f"Added new address: {str(user_view.address_input)}", ephemeral=True
        )

        self.bot.loop.create_task(
            self.background_process(
                user_id=interaction.user.id,
                new_address=new_address,
            )
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

    async def background_process(
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
            self.background_process(
                user=interaction.user, channel=interaction.channel, l_id=id
            )
        )

    @leaderboard.autocomplete("id")
    async def leaderboard_autocompletion(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        autocompletion: List[app_commands.Choice[str]] = []

        server_config: Optional[data.ResourceConfig] = None
        if interaction.guild is not None:
            server_config = self.bot.server_configs.get(interaction.guild.id)
        else:
            return autocompletion

        if server_config is not None:
            for l in server_config.resource_data.leaderboards:
                if current.lower() in l.short_name.lower():
                    autocompletion.append(
                        app_commands.Choice(
                            name=l.short_name, value=str(l.leaderboard_id)
                        )
                    )
        return autocompletion


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
                content="Could not find a guild, please use command at Discord server"
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

        l_id: Optional[uuid.UUID] = None
        for l in server_config.resource_data.leaderboards:
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
