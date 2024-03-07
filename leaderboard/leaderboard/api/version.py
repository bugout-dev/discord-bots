import os

LEADERBOARD_DISCORD_BOT_API_VERSION = "UNKNOWN"

try:
    PATH = os.path.abspath(os.path.dirname(__file__))
    VERSION_FILE = os.path.join(PATH, "version.txt")
    with open(VERSION_FILE) as ifp:
        LEADERBOARD_DISCORD_BOT_API_VERSION = ifp.read().strip()
except:
    pass
