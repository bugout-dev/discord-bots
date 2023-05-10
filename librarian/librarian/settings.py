import os

from bugout.app import Bugout

# Discord settings
DISCORD_BASE_API_URL = "https://discord.com/api"
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID", "")

# Discord bot settings
DISCORD_BOT_USERNAME = os.getenv("DISCORD_BOT_USERNAME", "")
if DISCORD_BOT_USERNAME == "":
    raise ValueError("DISCORD_BOT_USERNAME environment variable must be set")

DISCORD_BOT_APP_ID = os.getenv("DISCORD_BOT_APP_ID")
if DISCORD_BOT_APP_ID == "":
    raise ValueError("DISCORD_BOT_APP_ID environment variable must be set")

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
if DISCORD_BOT_TOKEN == "":
    raise ValueError("DISCORD_BOT_TOKEN environment variable must be set")

# OpenAI settings
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
if OPENAI_API_KEY == "":
    raise ValueError("OPENAI_API_KEY environment variable must be set")

# Bugout settings
BUGOUT_DISCORD_BOTS_ACCESS_TOKEN = os.getenv("BUGOUT_DISCORD_BOTS_ACCESS_TOKEN", "")
if BUGOUT_DISCORD_BOTS_ACCESS_TOKEN == "":
    raise ValueError(
        "BUGOUT_DISCORD_BOTS_ACCESS_TOKEN environment variable must be set"
    )

BUGOUT_DISCORD_BOTS_JOURNAL_ID = os.getenv("BUGOUT_DISCORD_BOTS_JOURNAL_ID", "")
if BUGOUT_DISCORD_BOTS_JOURNAL_ID == "":
    raise ValueError("BUGOUT_DISCORD_BOTS_JOURNAL_ID environment variable must be set")

bugout = Bugout()
