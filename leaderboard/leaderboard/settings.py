import os

LEADERBOARD_DISCORD_BOT_NAME = "leaderboard-bot"
MOONSTREAM_URL = "https://moonstream.to"

MOONSTREAM_ENGINE_API_URL = os.environ.get(
    "MOONSTREAM_ENGINE_API_URL", "https://engineapi.moonstream.to"
)


class COLORS:
    RESET = "\033[0m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    RED = "\033[91m"


LEADERBOARD_DISCORD_BOT_TOKEN = os.environ.get("LEADERBOARD_DISCORD_BOT_TOKEN", "")


def discord_env_check():
    if LEADERBOARD_DISCORD_BOT_TOKEN == "":
        raise Exception("LEADERBOARD_DISCORD_BOT_TOKEN environment variable is not set")
