from asyncio import create_task, get_event_loop
import logging
from pathlib import Path
import sys

from aiohttp import web

from .collection import Collection


LOG = logging.getLogger(__name__)


async def _init_collection(app: web.Application):
    root = app["root"]
    LOG.debug("Creating collection (root: %s)", root)
    coll = Collection(root)
    app["collection"] = coll
    app["collection:watch"] = create_task(coll.watch())


def main(port: int, root: Path):
    app = web.Application()
    app["root"] = root
    app.on_startup.append(_init_collection)
    LOG.debug("Starting web server (port: %d)", port)
    web.run_app(app, port=port)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    try:
        port = int(sys.argv[1])
        root = Path(sys.argv[2]).absolute()
    except:
        print("Usage: {} <port> <root>".format(__package__), file=sys.stderr)
        exit(1)
    main(port, root)
