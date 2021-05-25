from calendar import Calendar
from datetime import date, timedelta
import logging

from aiohttp import web
import aiohttp_jinja2

from .collection import as_datetime, Collection, Entry


LOG = logging.getLogger(__name__)

CAL = Calendar()


router = web.RouteTableDef()


@router.get(r"/{year:\d{4}}/{month:\d{2}}")
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
        "month": month,
        "today": date.today(),
    }
