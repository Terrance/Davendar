from datetime import date, datetime, time
from typing import Any, Callable, Dict, Iterable, Optional, TypeVar, Union, overload

from dateutil.relativedelta import relativedelta
from isoweek import Week
from pytz import UTC


T = TypeVar("T")
DateMaybeTime = Union[date, datetime]
Func = Callable[..., Any]


FILTERS: Dict[str, Func] = {}

GLOBALS: Dict[str, Any] = {
    "months": [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ],
    "now": datetime.now(),
    "now_week": Week.thisweek(),
}


@overload
def as_datetime(value: DateMaybeTime) -> datetime: ...
@overload
def as_datetime(value: None) -> None: ...

def as_datetime(value: Optional[DateMaybeTime]) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.astimezone()
    elif isinstance(value, date):
        return datetime(value.year, value.month, value.day).astimezone()
    else:
        return value


@overload
def as_date(value: DateMaybeTime) -> date: ...
@overload
def as_date(value: None) -> None: ...

def as_date(value: Optional[DateMaybeTime]) -> Optional[date]:
    if isinstance(value, datetime):
        return value.astimezone().date()
    else:
        return value


@overload
def as_time(value: DateMaybeTime) -> time: ...
@overload
def as_time(value: None) -> None: ...

def as_time(value: Optional[DateMaybeTime]) -> Optional[time]:
    if isinstance(value, datetime):
        return value.astimezone().timetz()
    elif isinstance(value, date):
        return datetime(value.year, value.month, value.day).astimezone().timetz()
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

def add_global(fn: Func):
    GLOBALS[fn.__name__] = fn


@add_filter
def delta(value: date, **kwargs):
    return value + relativedelta(**kwargs)
