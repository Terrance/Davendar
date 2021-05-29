from calendar import Calendar
from datetime import date, timedelta
import logging

from aiohttp import web
import aiohttp_jinja2
from isoweek import Week

from .collection import as_datetime, Collection, Entry


LOG = logging.getLogger(__name__)

CAL = Calendar()


router = web.RouteTableDef()


@router.get(r"/")
async def redirect(request: web.Request):
    today = date.today()
    url = request.app.router["month"].url_for(year=str(today.year), month=str(today.month))
    return web.HTTPTemporaryRedirect(url)


@router.get(r"/{year:\d{4}}/{month:\d{1,2}}", name="month")
@aiohttp_jinja2.template("month.j2")
async def month(request: web.Request):
    coll: Collection = request.app["collection"]
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


@router.get(r"/{year:\d{4}}/w{week:\d{1,2}}", name="week")
@aiohttp_jinja2.template("week.j2")
async def week(request: web.Request):
    coll: Collection = request.app["collection"]
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


@router.get(r"/{year:\d{4}}/{month:\d{1,2}}/{day:\d{1,2}}", name="day")
@aiohttp_jinja2.template("day.j2")
async def day(request: web.Request):
    coll: Collection = request.app["collection"]
    year = int(request.match_info["year"])
    month = int(request.match_info["month"])
    day = int(request.match_info["day"])
    start = as_datetime(date(year, month, day))
    end = start + timedelta(days=1)
    return {
        "entries": coll.slice(start, end),
        "selected": start,
    }
