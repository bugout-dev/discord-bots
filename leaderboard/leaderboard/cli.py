import argparse
import asyncio
import json
import logging
from typing import Any, Dict, Optional

from discord.ext import commands

from . import actions
from .bot import LeaderboardDiscordBot, configure_intents
from .settings import (
    BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG,
    LEADERBOARD_DISCORD_BOT_TOKEN,
    LOG_LEVEL,
    MOONSTREAM_APPLICATION_ID,
    MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN,
)
from .settings import bugout_client as bc

logging.basicConfig(level=LOG_LEVEL)

logger = logging.getLogger(__name__)


def configs_list_handler(args: argparse.Namespace) -> None:
    try:
        params = {
            "application_id": MOONSTREAM_APPLICATION_ID,
            "type": BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG,
        }
        if args.discord_server_id is not None:
            params["discord_server_id"] = args.discord_server_id
        resources = bc.list_resources(
            token=MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN,
            params=params,
        )

        print(resources.json())
    except Exception as e:
        raise Exception(e)


def configs_set_commands_handler(args: argparse.Namespace) -> None:
    try:
        resources = bc.list_resources(
            token=MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN,
            params={
                "application_id": MOONSTREAM_APPLICATION_ID,
                "type": BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG,
                "discord_server_id": args.discord_server_id,
            },
        )

        if len(resources.resources) != 1:
            logger.error(
                f"Found {len(resources.resources)} resources for specified discord-server-id {args.discord_server_id}"
            )
            return

        resource_data: Dict[str, Any] = {
            "update": {},
            "drop_keys": [],
        }
        if args.commands is not None:
            commands_dict = json.loads(args.commands)
            resource_data = {
                "update": {"commands": commands_dict},
                "drop_keys": [],
            }
        else:
            resource_data = {
                "update": {},
                "drop_keys": ["commands"],
            }
        updated_resource = bc.update_resource(
            token=MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN,
            resource_id=resources.resources[0].id,
            resource_data=resource_data,
        )
        print(updated_resource.json())
    except Exception as e:
        raise Exception(e)


def configs_set_thumbnail_url_handler(args: argparse.Namespace) -> None:
    try:
        resources = bc.list_resources(
            token=MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN,
            params={
                "application_id": MOONSTREAM_APPLICATION_ID,
                "type": BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG,
                "discord_server_id": args.discord_server_id,
            },
        )

        if len(resources.resources) != 1:
            logger.error(
                f"Found {len(resources.resources)} resources for specified discord-server-id {args.discord_server_id}"
            )
            return

        resource_data: Dict[str, Any] = {
            "update": {},
            "drop_keys": [],
        }
        if args.thumbnail_url is not None:
            resource_data = {
                "update": {"thumbnail_url": args.thumbnail_url},
                "drop_keys": [],
            }
        else:
            resource_data = {
                "update": {},
                "drop_keys": ["thumbnail_url"],
            }
        updated_resource = bc.update_resource(
            token=MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN,
            resource_id=resources.resources[0].id,
            resource_data=resource_data,
        )
        print(updated_resource.json())
    except Exception as e:
        raise Exception(e)


def discord_run_handler(args: argparse.Namespace) -> None:
    if LEADERBOARD_DISCORD_BOT_TOKEN == "":
        raise Exception("LEADERBOARD_DISCORD_BOT_TOKEN environment variable is not set")

    intents = configure_intents()
    bot = LeaderboardDiscordBot(command_prefix=commands.when_mentioned, intents=intents)

    asyncio.run(bot.load_configs())

    bot.run(token=LEADERBOARD_DISCORD_BOT_TOKEN)


def test_table_handler(args: argparse.Namespace) -> None:
    l_info, l_scores = asyncio.run(
        actions.process_leaderboard_info_with_scores(l_id=args.id)
    )

    if l_info is not None:
        print(l_info.description)

    if l_scores is not None:
        table = actions.TabularData()
        table.set_columns(["rank", "address", "score"])
        table.add_scores(l_scores)
        print(table.render_rst())


def main() -> None:
    parser = argparse.ArgumentParser(description="Moonstream leaderboard bot CLI")
    parser.set_defaults(func=lambda _: parser.print_help())
    subcommands = parser.add_subparsers(description="Bot commands")

    parser_configs = subcommands.add_parser(
        "configs",
        description="Work with discord server configurations from Brood resources",
    )
    parser_configs.set_defaults(func=lambda _: parser_configs.print_help())
    subparsers_configs = parser_configs.add_subparsers(
        description="Brood resource configs for discord servers"
    )
    parser_configs_list = subparsers_configs.add_parser(
        "list", description="Get list of configurations"
    )
    parser_configs_list.add_argument(
        "--discord-server-id",
        type=int,
        help="Discord server ID to find",
    )
    parser_configs_list.set_defaults(func=configs_list_handler)

    parser_configs_set_commands = subparsers_configs.add_parser(
        "set-commands", description="Get list of configurations"
    )
    parser_configs_set_commands.add_argument(
        "--discord-server-id",
        type=int,
        required=True,
        help="Discord server ID",
    )
    parser_configs_set_commands.add_argument(
        "--commands",
        type=str,
        help="Commands map to rename",
    )
    parser_configs_set_commands.set_defaults(func=configs_set_commands_handler)

    parser_configs_set_thumbnail_url = subparsers_configs.add_parser(
        "set-thumbnail-url", description="Get list of configurations"
    )
    parser_configs_set_thumbnail_url.add_argument(
        "--discord-server-id",
        type=int,
        required=True,
        help="Discord server ID",
    )
    parser_configs_set_thumbnail_url.add_argument(
        "--thumbnail-url",
        type=str,
        help="Discord server thumbnail url",
    )
    parser_configs_set_thumbnail_url.set_defaults(
        func=configs_set_thumbnail_url_handler
    )

    parser_discord = subcommands.add_parser(
        "discord", description="Operate with discord bot"
    )
    parser_discord.set_defaults(func=lambda _: parser_discord.print_help())
    subparsers_discord = parser_discord.add_subparsers(
        description="Discord bot commands"
    )
    parser_discord_run = subparsers_discord.add_parser(
        "run", description="Run discord bot"
    )
    parser_discord_run.set_defaults(func=discord_run_handler)

    parser_test_table = subcommands.add_parser("test-table", description="Test")
    parser_test_table.add_argument(
        "-i",
        "--id",
        type=str,
        help="Leaderboard ID",
    )
    parser_test_table.set_defaults(func=test_table_handler)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
