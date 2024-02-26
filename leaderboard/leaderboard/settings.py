import logging
import os

from bugout.app import Bugout

logger = logging.getLogger(__name__)

BUGOUT_RESOURCE_TYPE_DISCORD_BOT_CONFIG = "discord-bot-leaderboard-config"
BUGOUT_RESOURCE_TYPE_DISCORD_BOT_USER_IDENTIFIER = (
    "discord-bot-leaderboard-user-identity"
)

LOG_LEVEL_RAW = os.environ.get("LOG_LEVEL")
LOG_LEVEL = 20  # logging.INFO
try:
    if LOG_LEVEL_RAW is not None:
        LOG_LEVEL = int(LOG_LEVEL_RAW)
except:
    raise Exception(f"Could not parse LOG_LEVEL as int: {LOG_LEVEL_RAW}")


# Bugout
BUGOUT_BROOD_URL = os.environ.get("BUGOUT_BROOD_URL", "https://auth.bugout.dev")
BUGOUT_SPIRE_URL = os.environ.get("BUGOUT_SPIRE_URL", "https://spire.bugout.dev")

bugout_client = Bugout(brood_api_url=BUGOUT_BROOD_URL, spire_api_url=BUGOUT_SPIRE_URL)


LEADERBOARD_DISCORD_BOT_NAME = "leaderboard"
MOONSTREAM_URL = "https://moonstream.to"
MOONSTREAM_DISCORD_LINK = "https://discord.gg/fqHyPppNEa"
MOONSTREAM_THUMBNAIL_LOGO_URL = "https://s3.amazonaws.com/static.simiotics.com/moonstream/assets/discord-transparent.png"

MOONSTREAM_ENGINE_API_URL = os.environ.get(
    "MOONSTREAM_ENGINE_API_URL", "https://engineapi.moonstream.to"
)


class COLORS:
    RESET = "\033[0m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    RED = "\033[91m"


LEADERBOARD_DISCORD_BOT_TOKEN = os.environ.get("LEADERBOARD_DISCORD_BOT_TOKEN", "")

MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN = os.environ.get(
    "MOONSTREAM_DISCORD_BOT_ACCESS_TOKEN", ""
)
MOONSTREAM_APPLICATION_ID = os.environ.get("MOONSTREAM_APPLICATION_ID", "")
