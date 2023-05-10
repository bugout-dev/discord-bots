import argparse
import asyncio
import json
import logging
import platform
import signal
from typing import Any, List

from bugout.data import BugoutSearchResult, BugoutSearchResults

from .bot import Bot
from .connect import run_listener
from .embeddings import prepare_embedding
from .settings import (
    BUGOUT_DISCORD_BOTS_ACCESS_TOKEN,
    BUGOUT_DISCORD_BOTS_JOURNAL_ID,
    bugout,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def shutdown(signal, loop):
    """
    Graceful services shutdown.

    Reference:
    https://www.roguelynn.com/words/asyncio-graceful-shutdowns/
    """
    logging.info(f"Received exit signal {signal.name}...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    [task.cancel() for task in tasks]

    logging.info(f"Cancelling {len(tasks)} outstanding tasks")

    await asyncio.gather(*tasks, return_exceptions=True)

    logging.info(f"Flushing metrics")
    loop.stop()


def handle_run(args: argparse.Namespace) -> None:
    """
    Start async loop with bot WS.
    """
    bot = Bot()

    # Fetch data and prompt
    response: BugoutSearchResults = bugout.search(
        token=BUGOUT_DISCORD_BOTS_ACCESS_TOKEN,
        journal_id=BUGOUT_DISCORD_BOTS_JOURNAL_ID,
        query="tag:bot_username:librarian",
    )
    total_results = response.total_results
    if total_results != 2:
        logger.error(
            f"Wrong number: {total_results} of entires fetch from Bugout journal"
        )
        return

    results: List[BugoutSearchResult] = response.results
    for result in results:
        if "function:data" in result.tags:
            bot.data = result.content
        if "function:prompt" in result.tags:
            content = result.content
            try:
                content_json = json.loads(content)
                bot.prompt.prefix = content_json.get("prefix", "")
                bot.prompt.postfix = content_json.get("postfix", "")
            except Exception as err:
                logger.error(
                    f"Unable to parse bugout entry with bot prompt, err: {err}"
                )
                return

    # Prepare embeddings
    docsearch, qa_chain = prepare_embedding(bot.data)
    bot.docsearch = docsearch
    bot.qa_chain = qa_chain

    loop = asyncio.get_event_loop()

    # Handle shutdown signals
    signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
    for s in signals:
        loop.add_signal_handler(s, lambda s=s: asyncio.create_task(shutdown(s, loop)))

    try:
        loop.create_task(run_listener(bot))
        loop.run_forever()
    except Exception as err:
        logger.error("An error occurred during running event loop")
        raise Exception(err)
    finally:
        loop.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Librarian Discord bot CLI")
    parser.set_defaults(func=lambda _: parser.print_help())
    subcommands = parser.add_subparsers(description="Librarian commands")

    parser.add_argument("--dry-run", action="store_true", help="Run bot in test mode")

    parser_run = subcommands.add_parser("run", description="Run bot command")
    parser_run.set_defaults(func=lambda _: parser_run.print_help())
    parser_run.set_defaults(func=handle_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
