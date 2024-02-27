import argparse
import asyncio
import logging

from discord.ext import commands

from . import actions
from .bot import LeaderboardDiscordBot, configure_intents
from .settings import LEADERBOARD_DISCORD_BOT_TOKEN, LOG_LEVEL

logging.basicConfig(level=LOG_LEVEL)

logger = logging.getLogger(__name__)


def discord_run_handler(args: argparse.Namespace) -> None:
    if LEADERBOARD_DISCORD_BOT_TOKEN == "":
        raise Exception("LEADERBOARD_DISCORD_BOT_TOKEN environment variable is not set")

    intents = configure_intents()
    bot = LeaderboardDiscordBot(command_prefix=commands.when_mentioned, intents=intents)

    bot.load_bugout_configs()
    asyncio.run(bot.load_leaderboards_info())
    bot.load_bugout_users()

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
        help="Leaderboard id",
    )
    parser_test_table.set_defaults(func=test_table_handler)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
