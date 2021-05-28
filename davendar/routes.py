from calendar import Calendar
from datetime import date, datetime, timedelta
import logging
from pytz import UTC

from aiohttp import web
import aiohttp_jinja2

from .collection import as_datetime, Collection, Entry


LOG = logging.getLogger(__name__)

CAL = Calendar()


router = web.RouteTableDef()


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


@router.get(r"/{year:\d{4}}/{month:\d{1,2}}/{day:\d{1,2}}", name="day")
@aiohttp_jinja2.template("day.j2")
async def day(request: web.Request):
    coll: Collection = request.app["collection"]
    year = int(request.match_info["year"])
    month = int(request.match_info["month"])
    day = int(request.match_info["day"])
    start = datetime(year, month, day, tzinfo=UTC)
    end = start + timedelta(days=1)
    return {
        "entries": coll.slice(start, end),
        "selected": start,
    }
