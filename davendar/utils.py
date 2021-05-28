from datetime import date, datetime
from typing import Any, Callable, Dict

from dateutil.relativedelta import relativedelta


Func = Callable[..., Any]


FILTERS: Dict[str, Func] = {}

GLOBALS: Dict[str, Any] = {
    "months": [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ],
    "now": datetime.now(),
}


def add_filter(fn: Func):
    FILTERS[fn.__name__] = fn

def add_global(fn: Func):
    GLOBALS[fn.__name__] = fn


@add_filter
def delta(value: date, **kwargs):
    return value + relativedelta(**kwargs)
