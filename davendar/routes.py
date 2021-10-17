from calendar import Calendar
from datetime import date, timedelta
from functools import wraps
import logging
from typing import Any, Awaitable, Callable, cast, Mapping, Union

from aiohttp import web
import aiohttp_jinja2
from isoweek import Week
from yarl import URL

from .collection import as_datetime, Collection, Entry, Event
from .utils import dynamic_globals, text_parse


FormView = Awaitable[Union[str, URL]]
UIView = Awaitable[Mapping[str, Any]]


LOG = logging.getLogger(__name__)

CAL = Calendar()


router = web.RouteTableDef()


def ui_route(path: str):
    def outer(fn: Callable[[web.Request, Collection], UIView]):
        @wraps(fn)
        async def inner(request: web.Request) -> Mapping[str, Any]:
            coll = request.app["collection"]
            ctx = dynamic_globals(request.app)
            ctx["request"] = request
            ctx.update(await fn(request, coll))
            return ctx
        templated = aiohttp_jinja2.template("{}.j2".format(fn.__name__))(inner)
        return router.get(path, name=fn.__name__)(templated)
    return outer


def form_route(path: str):
    def outer(fn: Callable[[web.Request, Mapping[str, str], Collection], FormView]):
        @wraps(fn)
        async def inner(request: web.Request) -> web.StreamResponse:
            form = cast(Mapping[str, str], await request.post())
            coll = request.app["collection"]
            redirect = await fn(request, form, coll)
            raise web.HTTPFound(redirect)
        return router.post(path, name=fn.__name__)(inner)
    return outer


@router.get(r"/")
async def redirect(request: web.Request):
    today = date.today()
    url = request.app.router["month"].url_for(year=str(today.year), month=str(today.month))
    return web.HTTPTemporaryRedirect(url)


@form_route(r"/create")
async def create(request: web.Request, form: Mapping[str, str], coll: Collection):
    words = form["text"].split()
    name = None
    for word in words:
        if word.startswith("@"):
            name = word[1:].lower()
            words.remove(word)
            break
    for cal in coll.calendars:
        if not name or (cal.label and name in cal.label.lower()):
            break
    else:
        raise web.HTTPBadRequest
    try:
        title, start, end, location = text_parse(words)
    except ValueError:
        LOG.debug("Failed to parse %r", form["text"], exc_info=True)
        raise web.HTTPBadRequest
    event = Event(cal)
    event.summary = title
    event.start = start
    event.end = end
    event.location = location
    LOG.info("Adding new event: %r", event)
    event.save()
    target = start or end or date.today()
    try:
        route = request.app.router[form["route"]]
    except KeyError:
        route = request.app.router["month"]
    if route.name == "day":
        return route.url_for(year=str(target.year), month=str(target.month), date=str(target.day))
    elif route.name == "week":
        week = Week.withdate(target)
        return route.url_for(year=str(week.year), week=str(week.week))
    else:
        return request.app.router["month"].url_for(year=str(target.year), month=str(target.month))


@ui_route(r"/entry/{cal}/{entry}")
async def entry(request: web.Request, coll: Collection):
    cal = coll[request.match_info["cal"]]
    entry = cal[request.match_info["entry"]]
    return {
        "entry": entry,
    }


@form_route(r"/entry/{cal}/{entry}/delete")
async def entry_delete(request: web.Request, form: Mapping[str, str], coll: Collection):
    cal = coll[request.match_info["cal"]]
    entry = cal[request.match_info["entry"]]
    entry.delete()
    today = date.today()
    return request.app.router["month"].url_for(year=str(today.year), month=str(today.month))


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
