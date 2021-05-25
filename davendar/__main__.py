from asyncio import create_task
import logging
from pathlib import Path
import sys

from aiohttp import web
import aiohttp_jinja2
from jinja2 import PackageLoader

from .collection import Collection
from .routes import router


LOG = logging.getLogger(__name__)


async def _init_collection(app: web.Application):
    LOG.info("Initialising collection")
    app["collection:watch"] = create_task(app["collection"].watch())


def main(port: int, root: Path):
    app = web.Application()
    coll = Collection(root)
    env = aiohttp_jinja2.setup(app, loader=PackageLoader(__package__))
    app["collection"] = env.globals["collection"] = coll
    app.add_routes(router)
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
