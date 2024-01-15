import argparse
import json
import logging
import os

from discord.ext import commands

from . import actions, data
from .bot import LeaderboardDiscordBot, configure_intents
from .settings import LEADERBOARD_DISCORD_BOT_TOKEN, discord_env_check

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def discord_run_handler(args: argparse.Namespace) -> None:
    config_path = os.path.join(os.getcwd(), args.config)
    with open(config_path) as ifp:
        config_json = json.load(ifp)
    config = data.Config(**config_json)

    discord_env_check()

    intents = configure_intents()
    bot = LeaderboardDiscordBot(
        command_prefix=commands.when_mentioned_or("?"), intents=intents, config=config
    )
    bot.run(token=LEADERBOARD_DISCORD_BOT_TOKEN)


def test_handler(args: argparse.Namespace) -> None:
    l_info, l_scores = actions.process_leaderboard_info_with_scores(id=args.id)

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
    parser_discord_run.add_argument(
        "-c",
        "--config",
        type=str,
        required=True,
        help="Path to configuration file",
    )
    parser_discord_run.set_defaults(func=discord_run_handler)

    parser_test = subcommands.add_parser("test", description="Test")
    parser_test.add_argument(
        "-i",
        "--id",
        type=str,
        help="Leaderboard id",
    )
    parser_test.set_defaults(func=test_handler)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
