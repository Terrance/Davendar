from calendar import Calendar
from datetime import date, timedelta
from functools import wraps
import logging
from typing import Any, Awaitable, Callable, Mapping

from aiohttp import web
import aiohttp_jinja2
from isoweek import Week

from .collection import as_datetime, Collection, Entry
from .utils import dynamic_globals


LOG = logging.getLogger(__name__)

CAL = Calendar()


router = web.RouteTableDef()


def ui_route(path: str):
    def outer(fn: Callable[[web.Request, Collection], Awaitable[Mapping[str, Any]]]):
        @wraps(fn)
        async def inner(request: web.Request):
            coll = request.app["collection"]
            ctx = dynamic_globals()
            ctx.update(await fn(request, coll))
            return ctx
        templated = aiohttp_jinja2.template("{}.j2".format(fn.__name__))(inner)
        return router.get(path, name=fn.__name__)(templated)
    return outer


@router.get(r"/")
async def redirect(request: web.Request):
    today = date.today()
    url = request.app.router["month"].url_for(year=str(today.year), month=str(today.month))
    return web.HTTPTemporaryRedirect(url)


@ui_route(r"/{year:\d{4}}/{month:\d{1,2}}")
async def month(request: web.Request, coll: Collection):
    year = int(request.match_info["year"])
    month = int(request.match_info["month"])
    dates = CAL.monthdatescalendar(year, month)
    start = as_datetime(dates[0][0])
    end = as_datetime(dates[-1][-1] + timedelta(days=1))
    return {
        "entries": Entry.group(coll.slice(start, end)),
        "weeks": dates,
        "selected": date(year, month, 1),
    }


@ui_route(r"/{year:\d{4}}/w{week:\d{1,2}}")
async def week(request: web.Request, coll: Collection):
    year = int(request.match_info["year"])
    weeknum = int(request.match_info["week"])
    week = Week(year, weeknum)
    start = as_datetime(week.day(0))
    end = start + timedelta(days=7)
    return {
        "entries": Entry.group(coll.slice(start, end)),
        "selected": week,
        "prev": Week.withdate(start - timedelta(days=1)),
        "next": Week.withdate(end + timedelta(days=1)),
    }


@ui_route(r"/{year:\d{4}}/{month:\d{1,2}}/{day:\d{1,2}}")
async def day(request: web.Request, coll: Collection):
    year = int(request.match_info["year"])
    month = int(request.match_info["month"])
    day = int(request.match_info["day"])
    start = as_datetime(date(year, month, day))
    end = start + timedelta(days=1)
    return {
        "entries": coll.slice(start, end),
        "selected": start,
    }
