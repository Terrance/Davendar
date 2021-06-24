from datetime import date, datetime, time
import os
from typing import Any, Callable, Dict, Iterable, List, Optional, overload, TypeVar, Union

from dateparser import parse
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


FILTERS: Dict[str, Func] = {}

GLOBALS: Dict[str, Any] = {
    "months": [date(2000, month, 1).strftime("%B") for month in range(1, 13)],
}


def dynamic_globals():
    return {
        "now": datetime.now(),
        "now_week": Week.thisweek(),
    }


def tzify(value: datetime):
    return value.astimezone(TZ)


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
    all_day = False
    current = "title"
    skip = 0
    for word, after in zip(words, words[1:] + [""]):
        if skip:
            skip -= 1
            continue
        elif word.startswith("\\"):
            word = word[1:]
            grouped[current].append(word)
            continue
        elif word.lower() == "all" and after.lower() == "day":
            all_day = True
            skip = 1
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
        start = parse(values["start"])
        if not start:
            raise ValueError(values["start"])
        start = as_date(start) if all_day else as_datetime(start)
    if values["end"]:
        end = parse(values["end"])
        if not end:
            raise ValueError(values["end"])
    elif values["delta"]:
        offset = parse(values["delta"])
        if not offset:
            raise ValueError(values["delta"])
        delta = datetime.now() - offset
        end = start + delta
    if end:
        end = as_date(end) if all_day else as_datetime(end)
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
