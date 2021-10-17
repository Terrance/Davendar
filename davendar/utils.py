from datetime import date, datetime, time
import os
from typing import Any, Callable, Dict, Iterable, List, Optional, overload, TypeVar, Union
from urllib.parse import quote

from aiohttp import web
import aiohttp_jinja2
from dateparser.date import DateDataParser
from dateutil.relativedelta import relativedelta
from isoweek import Week
# Because recurring_ical_events expects pytz timezones:
from pytz_deprecation_shim import timezone


T = TypeVar("T")
DateMaybeTime = Union[date, datetime]
Func = Callable[..., Any]


TZ_NAME = os.getenv("TZ", "UTC")
try:
    TZ = timezone(TZ_NAME)
except KeyError:
    raise RuntimeError("TZ environment variable not set to a valid timezone")


DATE_PARSER = DateDataParser(settings={"RETURN_TIME_AS_PERIOD": True})


FILTERS: Dict[str, Func] = {
    "urlencode": quote,
}

GLOBALS: Dict[str, Any] = {
    "months": [date(2000, month, 1).strftime("%B") for month in range(1, 13)],
}


def dynamic_globals(app: web.Application):
    now = datetime.now()
    tmpl = aiohttp_jinja2.get_env(app).get_template("icon.j2")
    icon = tmpl.render({"now": now})
    icon_line = "".join(line.strip() for line in icon.splitlines())
    return {
        "now": now,
        "now_week": Week.thisweek(),
        "favicon": icon_line,
    }


def tzify(value: datetime):
    return value.astimezone(TZ)


def parse_date(text: str) -> Optional[DateMaybeTime]:
    parsed = DATE_PARSER.get_date_data(text)
    value = parsed.date_obj
    if not value:
        return None
    elif parsed.period == "time":
        return value
    else:
        return as_date(value)


@overload
def as_datetime(value: DateMaybeTime) -> datetime: ...
@overload
def as_datetime(value: None) -> None: ...

def as_datetime(value: Optional[DateMaybeTime]) -> Optional[datetime]:
    if isinstance(value, datetime):
        return tzify(value)
    elif isinstance(value, date):
        return tzify(datetime(value.year, value.month, value.day))
    else:
        return value


@overload
def as_date(value: DateMaybeTime) -> date: ...
@overload
def as_date(value: None) -> None: ...

def as_date(value: Optional[DateMaybeTime]) -> Optional[date]:
    if isinstance(value, datetime):
        return tzify(value).date()
    else:
        return value


@overload
def as_time(value: DateMaybeTime) -> time: ...
@overload
def as_time(value: None) -> None: ...

def as_time(value: Optional[DateMaybeTime]) -> Optional[time]:
    if isinstance(value, datetime):
        return tzify(value).timetz()
    elif isinstance(value, date):
        return tzify(datetime(value.year, value.month, value.day)).timetz()
    else:
        return value


_PARSE_KEYWORDS = {
    "start": "start",
    "at": ("start", "location"),
    "from": "start",
    "end": "end",
    "to": "end",
    "until": "end",
    "for": "delta",
    "in": "location",
}


def text_parse(words: List[str]):
    """
    Parse a written string describing details of an event.  Start and end timestamps (or a start
    and duration) and locations can be resolved.  Use a backslash to avoid parsing a keyword.

        >>> text_parse(r"Theme park from tomorrow all day until Friday at Disneyland Paris".split())
        ("Theme park", date(2021, 6, 2), date(2021, 6, 4), "Disneyland Paris")
    """
    grouped = {}
    for key in ("title", "start", "end", "delta", "location"):
        grouped[key] = []
    current = "title"
    for word in words:
        if word.startswith("\\"):
            word = word[1:]
            grouped[current].append(word)
            continue
        group = _PARSE_KEYWORDS.get(word.lower())
        if isinstance(group, tuple):
            for option in group:
                if not grouped[option]:
                    group = option
                    break
            else:
                group = None
        if group:
            current = group
        else:
            grouped[current].append(word)
    values = {key: " ".join(words) or None for key, words in grouped.items()}
    title = values["title"]
    location = values["location"]
    start = end = None
    if values["start"]:
        start = parse_date(values["start"])
    if not start:
        raise ValueError(values["start"])
    if values["end"]:
        end = parse_date(values["end"])
    elif values["delta"]:
        offset = parse_date(values["delta"])
        if not offset:
            raise ValueError(values["delta"])
        elif isinstance(offset, datetime):
            delta = datetime.now() - offset
        else:
            delta = date.today() - offset
        end = start + delta
    if not end:
        raise ValueError(values["end"])
    return (title, start, end, location)


def repr_factory(parts: Callable[[T], Iterable[Optional[str]]]) -> Callable[[T], str]:
    def __repr__(self: T):
        items = " ".join(filter(None, parts(self)))
        inner = ": ".join(filter(None, (self.__class__.__name__, items)))
        return "<{}>".format(inner)
    return __repr__


def add_filter(fn: Func):
    FILTERS[fn.__name__] = fn
    return fn

def add_global(fn: Func):
    GLOBALS[fn.__name__] = fn
    return fn


@add_filter
def delta(value: date, **kwargs):
    return value + relativedelta(**kwargs)


@add_filter
def day_percent(value: Optional[time]):
    if value:
        return 100 * ((value.hour + (value.minute + value.second / 60) / 60) / 24)
    else:
        return None
