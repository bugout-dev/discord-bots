import logging
from typing import Any, Dict, List, Optional, Tuple

from langchain.chains.combine_documents.base import BaseCombineDocumentsChain
from langchain.vectorstores import FAISS

from . import connect
from .data import BotPrompt, DiscordTextToken, DiscordTextTokenType
from .settings import DISCORD_BOT_APP_ID, DISCORD_BOT_TOKEN, DISCORD_BOT_USERNAME

logger = logging.getLogger(__name__)


def words_parser(content_body: str) -> Tuple[List[List[str]], bool]:
    """
    Parse messages to bot.

    On each line, only process the final mention as issuing a command to the Discord
    This allows users to discuss the behavior of the Discord Bot and issue
    a command on the same line.
    """
    is_bot_mentioned = False
    lines = content_body.split("\n")
    words: List[List[str]] = []
    for line in lines:
        tokens = [parse_raw_text(raw_token) for raw_token in line.split()]
        bot_mention_index: List[int] = [
            index
            for index, token in enumerate(tokens)
            if token.token_type == DiscordTextTokenType.USER
        ]

        if len(tokens) > 0:
            plain_raw_args: List[str]
            if len(bot_mention_index) > 0:
                is_bot_mentioned = True
                plain_raw_args = [
                    token.raw for token in tokens[bot_mention_index[-1] + 1 :]
                ]
            else:
                plain_raw_args = [token.raw for token in tokens]

            words.append(plain_raw_args)

    return words, is_bot_mentioned


def parse_raw_text(raw_token: str) -> DiscordTextToken:
    """
    Parses raw text from a Discord comment into a DiscordTextToken object.
    """
    if raw_token == "":
        return DiscordTextToken(
            raw=raw_token, token_type=DiscordTextTokenType.PLAIN, token=raw_token
        )

    parsed_token = DiscordTextToken(
        raw=raw_token,
        token_type=DiscordTextTokenType.PLAIN,
        token=raw_token,
    )

    symbol_signifier = raw_token[0:3]
    if symbol_signifier.startswith("<@"):
        parsed_token.token_type = DiscordTextTokenType.USER
        parsed_token.token = raw_token[1:]

    return parsed_token


class Bot:
    def __init__(self) -> None:
        self.username: str = DISCORD_BOT_USERNAME
        self.app_id: str = str(DISCORD_BOT_APP_ID)
        self.token: str = DISCORD_BOT_TOKEN

        self.default_response = f"Very interesting, but not understandable.. :scream:\n"

        self.ws_url = ""

        self.prompt = BotPrompt
        self.data = ""

        self.docsearch: Optional[FAISS] = None
        self.qa_chain: Optional[BaseCombineDocumentsChain] = None

    async def set_ws_url(self, ws_url: str) -> None:
        self.ws_url = ws_url

    async def handle_mention(self, d: Dict[str, Any]) -> None:
        """
        Handle when bot is mentioned.
        """
        # Ensure we are working with guild or in private messages
        # Where 0 - guild and 1 - private
        channel_id = d.get("channel_id")
        # channel = await connect.get_channel(token=self.token, channel_id=channel_id)
        # channel_type = channel.get("type")

        content_body = d.get("content")

        author = d.get("author")
        author_id = author.get("id")
        author_username = author.get("username")
        if author_id == self.app_id and author_username == self.username:
            # Ignore messages from yourself to not fall in loop
            return None

        words, is_bot_mentioned = words_parser(content_body)
        c = " ".join(words[0])

        if is_bot_mentioned:
            final_c = f"{self.prompt.prefix} Source text: {c}.{self.prompt.postfix}"
            docs = self.docsearch.similarity_search(query=final_c)
            answer = self.qa_chain.run(input_documents=docs, question=final_c)

            await connect.send_message(
                token=self.token, channel_id=channel_id, content=answer
            )
