from datetime import date, datetime, time
import os
from typing import Any, Callable, Dict, Iterable, Optional, TypeVar, Union, overload

from dateutil.relativedelta import relativedelta
from isoweek import Week
# Because recurring_ical_events expects pytz timezones:
from pytz_deprecation_shim import timezone


T = TypeVar("T")
DateMaybeTime = Union[date, datetime]
Func = Callable[..., Any]


try:
    TZ = timezone(os.getenv("TZ", "UTC"))
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
