from abc import ABC
from asyncio.events import get_event_loop
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from enum import IntEnum
import json
import logging
from pathlib import Path
from pytz import UTC
from typing import cast, Dict, Generic, Iterable, List, Optional, Type, TypeVar, Union
from uuid import uuid4

from asyncinotify import Inotify, Mask, Watch
from icalendar import Calendar as vCalendar, Event as vEvent, Todo as vTodo, vText
from icalendar.cal import Component

from .utils import as_date, as_datetime, as_time, DateMaybeTime, repr_factory


T = TypeVar("T")
T2 = TypeVar("T2")


LOG = logging.getLogger(__name__)


class Entry(ABC):

    class Invalid(TypeError):
        pass

    class Property(Generic[T]):
        def __init__(self, field: str):
            self._field = field
        def __get__(self, instance: "Entry", _: Type["Entry"]) -> T:
            node = instance._core[self._field]
            if isinstance(node, vText):
                return cast(T, str(node))
            else:
                return instance._core.decoded(self._field)

    class _DefaultProperty(Property[T], Generic[T, T2]):
        def __init__(self, field: str, default: T2):
            super().__init__(field)
            self._default = default
        def __get__(self, instance: "Entry", owner: Type["Entry"]) -> Union[T, T2]:
            try:
                return super().__get__(instance, owner) or self._default
            except KeyError:
                return self._default

    class DefaultProperty(_DefaultProperty[T, T]):
        pass

    class MutableProperty(_DefaultProperty[T, None]):
        def __init__(self, field: str):
            super().__init__(field, None)
        def __set__(self, instance: "Entry", owner: Type["Entry"], value: Optional[T]):
            self.__del__(instance, owner)
            if value:
                instance._core.add(self._field, value, encode=True)
        def __del__(self, instance: "Entry", _: Type["Entry"]):
            try:
                del instance._core[self._field]
            except KeyError:
                pass

    _base: Type[Component]
    _types: Dict[str, Type["Entry"]] = {}

    def __init_subclass__(cls):
        cls._types[cls._base.name] = cls

    @classmethod
    def load(cls, calendar: "Calendar", filename: str):
        path = calendar.path / filename
        with open(path, "rb") as raw:
            component = Component.from_ical(raw.read())
        if component.name != "VCALENDAR":
            raise Entry.Invalid("Root component must be a VCALENDAR")
        for part in component.subcomponents:
            try:
                base = cls._types[part.name]
            except KeyError:
                continue
            else:
                return base(calendar, filename)
        else:
            raise Entry.Invalid("File does not contain any supported components")

    @classmethod
    def group(cls, entries: Iterable["Entry"]):
        grouped: Dict[date, List[Entry]] = defaultdict(list)
        for entry in entries:
            for day in entry.days:
                grouped[day].append(entry)
        return grouped

    __slots__ = ("_calendar", "_filename", "_component")

    def __init__(self, calendar: Optional["Calendar"] = None, filename: Optional[str] = None,
                 component: Optional[Component] = None):
        self._calendar = calendar
        self._filename = filename or "{}.ics".format(uuid4())
        if component:
            self._component = component
        elif filename and self.path and self.path.exists():
            self.reload()
        else:
            self._component = vCalendar()

    @property
    def _core(self) -> Component:  # TODO: multiple component parts in one VCALENDAR
        return next(iter(self._component.walk(self._base.name)))

    @property
    def calendar(self):
        return self._calendar

    @calendar.setter
    def calendar(self, calendar: "Calendar"):
        if self._calendar and self.path.exists():
            self.path.rename(calendar.path / self._filename)
        self._calendar = calendar

    @property
    def filename(self):
        return self._filename

    @property
    def path(self):
        return self._calendar.path / self._filename if self._calendar else None

    uid = Property[str]("UID")
    summary = MutableProperty[str]("SUMMARY")
    created = MutableProperty[datetime]("CREATED")
    start = MutableProperty[DateMaybeTime]("DTSTART")
    end: MutableProperty[DateMaybeTime]

    @property
    def start_dt(self):
        return as_datetime(self.start)

    @property
    def end_dt(self):
        return as_datetime(self.end)

    @property
    def start_d(self):
        return as_date(self.start)

    @property
    def end_d(self):
        return as_date(self.end)

    @property
    def start_t(self):
        return as_time(self.start)

    @property
    def end_t(self):
        return as_time(self.end)

    @property
    def all_day(self):
        return self.start == self.start_d

    @property
    def days(self):
        if self.start_d and self.end_d:
            length = self.end_d - self.start_d
            if self.end_t == time():
                length -= timedelta(days=1)
            span = range(1, length.days + 1)
            return [self.start_d] + [self.start_d + timedelta(days=days) for days in span]
        else:
            return list(filter(None, (self.start_d, self.end_d)))

    @property
    def times(self):
        return list(filter(None, (self.start_dt.time(), self.end_dt.time())))

    def reload(self):
        if not (self.path and self.path.exists()):
            return
        with open(self.path, "rb") as raw:
            component = Component.from_ical(raw.read())
        if component.name != "VCALENDAR":
            raise Entry.Invalid("Root component must be a VCALENDAR")
        for part in component.subcomponents:
            if isinstance(part, self._base):
                self._component = component
                break
        else:
            raise Entry.Invalid("File does not contain any supported components")

    def save(self):
        with open(self.filename, "wb") as raw:
            raw.write(self._component.to_ical())

    def __lt__(self, other: "Entry"):
        default = datetime.utcnow().replace(tzinfo=UTC)
        return (self.start_dt or default) < (other.start_dt or default)

    @repr_factory
    def __repr__(self):
        return [repr(self.summary),
                self.start.strftime("%Y-%m-%d %H:%M") if self.start else None,
                self.end.strftime("%Y-%m-%d %H:%M") if self.end else None]


class Event(Entry):

    _base = vEvent

    def __init__(self, calendar: Optional["Calendar"] = None, filename: Optional[str] = None):
        super().__init__(calendar, filename)
        try:
            self._core
        except StopIteration:
            event = vEvent()
            event["UID"] = str(uuid4())
            self._component.add_component(event)

    end = Entry.MutableProperty[DateMaybeTime]("DTEND")


class Task(Entry):

    class Priority(IntEnum):
        LOW = 4
        MEDIUM = 5
        HIGH = 6

    _base = vTodo

    def __init__(self, calendar: Optional["Calendar"] = None, filename: Optional[str] = None):
        super().__init__(calendar, filename)
        try:
            self._core
        except StopIteration:
            task = vTodo()
            task["UID"] = str(uuid4())
            self._component.add_component(task)

    end = Entry.MutableProperty[DateMaybeTime]("DUE")
    priority = Entry.DefaultProperty[int]("PRIORITY", 0)

    @property
    def priority_3(self) -> Optional[Priority]:
        if 1 <= self.priority <= 4:
            return self.Priority.LOW
        elif self.priority == 5:
            return self.Priority.MEDIUM
        elif 6 <= self.priority <= 9:
            return self.Priority.HIGH
        else:
            return None

    @priority_3.setter
    def priority_3(self, priority: Optional[Priority]):
        self.priority = priority.value if priority else 0


class Calendar:

    __slots__ = ("_collection", "_dirname", "_entries_by_uid", "_entries_by_filename",
                 "label", "colour")

    def __init__(self, collection: "Collection", dirname: str):
        self._collection = collection
        self._dirname = dirname
        self._entries_by_uid: Dict[str, Entry] = {}
        self._entries_by_filename: Dict[str, Entry] = {}
        self.label = self.colour = None
        if self.path.exists():
            self.scan_entries()
            self.scan_metadata()
        else:
            self.path.mkdir()

    @property
    def collection(self):
        return self._collection

    @property
    def dirname(self):
        return self._dirname

    @property
    def path(self):
        return self._collection.path / self._dirname

    @property
    def entries(self):
        return frozenset(self._entries_by_uid.values())

    @property
    def events(self):
        return sorted(entry for entry in self.entries if isinstance(entry, Event))

    @property
    def tasks(self):
        return sorted(entry for entry in self.entries if isinstance(entry, Task))

    def slice(self, not_before: Optional[datetime] = None, not_after: Optional[datetime] = None):
        selected: List[Entry] = []
        for entry in self.entries:
            if not entry.start_dt or not entry.end_dt:
                continue
            elif not_before and entry.end_dt < not_before:
                continue
            elif not_after and entry.start_dt >= not_after:
                continue
            else:
                selected.append(entry)
        return sorted(selected)

    def add_entry(self, entry: Entry):
        entry.calendar = self
        self._entries_by_uid[entry.uid] = entry
        self._entries_by_filename[entry.filename] = entry

    def move_entry(self, entry: Entry, target: "Calendar"):
        self.unload_entry(entry.filename)
        target.add_entry(entry)

    def drop_entry(self, entry: Entry):
        del self._entries_by_filename[entry.filename]
        del self._entries_by_uid[entry.uid]

    def load_entry(self, filename: str):
        path = self.path / filename
        try:
            event = Entry.load(self, filename)
        except Entry.Invalid as ex:
            LOG.warning("Skipping non-entry file: %s (%s)", path, ex.args[0])
        else:
            self.add_entry(event)

    def unload_entry(self, filename: str):
        self.drop_entry(self._entries_by_filename[filename])

    def scan_entries(self):
        count = 0
        LOG.debug("Scanning calendar: %s", self.dirname)
        for child in self.path.iterdir():
            if child.name.endswith(".ics"):
                self.load_entry(child.name)
                count += 1
        LOG.debug("Added %d entries from %s", count, self.dirname)

    def scan_metadata(self):
        radicale = self.path / ".Radicale.props"
        if radicale.exists():
            try:
                with open(radicale) as props:
                    meta = json.load(props)
            except Exception:
                pass
            else:
                self.label = meta.get("D:displayname")
                self.colour = meta.get("ICAL:calendar-color")
                LOG.debug("Identified calendar %r as %r", self.dirname, self.label)

    @repr_factory
    def __repr__(self):
        return [repr(self.dirname)]


class Collection:

    MASK_CHANGE = Mask.CREATE | Mask.MODIFY | Mask.DELETE | Mask.MOVE

    __slots__ = ("_path", "_calendars")

    def __init__(self, path: Path):
        self._path = path
        self._calendars: Dict[str, Calendar] = {}

    @property
    def path(self):
        return self._path

    @property
    def calendars(self):
        return frozenset(self._calendars.values())

    async def open_calendar(self, name: str):
        loop = get_event_loop()
        return await loop.run_in_executor(None, Calendar, self, name)

    def add_calendar(self, calendar: Calendar):
        self._calendars[calendar.dirname] = calendar

    def drop_calendar(self, calendar: Calendar):
        del self._calendars[calendar.dirname]

    def slice(self, not_before: Optional[datetime] = None, not_after: Optional[datetime] = None):
        selected: List[Entry] = []
        for calendar in self.calendars:
            selected += calendar.slice(not_before, not_after)
        return sorted(selected)

    async def watch(self):
        with Inotify() as inotify:
            watches: Dict[Path, Watch] = {}
            # Watch for new and removed calendar dirs in the root.
            top = inotify.add_watch(self.path, self.MASK_CHANGE)
            # Watch all current directories for new, changed and removed events.
            for child in self.path.iterdir():
                if child.is_dir():
                    watches[child] = inotify.add_watch(child, self.MASK_CHANGE)
            LOG.info("Running initial directory scan")
            for path in watches:
                if path.parent == self.path and path.name not in self._calendars:
                    calendar = await self.open_calendar(path.name)
                    self.add_calendar(calendar)
            LOG.info("Listening for filesystem changes")
            async for change in inotify:
                if not change.name:
                    continue
                name = str(change.name)
                path = change.watch.path / change.name
                if change.watch is top:
                    # Change relates to the group itself.
                    watched = path in watches
                    if not watched and path.is_dir():
                        # Calendar was created or moved in to the group.
                        LOG.debug("Adding new calendar: %s", path.name)
                        watches[path] = inotify.add_watch(path, self.MASK_CHANGE)
                        calendar = await self.open_calendar(name)
                        self.add_calendar(calendar)
                    elif watched and not path.is_dir():
                        # Calendar was deleted or moved out of the root.
                        LOG.debug("Removing old calendar: %s", path.name)
                        # Can't remove the watch if the watched dir was deleted.
                        if not change.mask & Mask.DELETE:
                            inotify.rm_watch(watches.pop(path))
                        calendar = self._calendars[name]
                        self.drop_calendar(calendar)
                elif path.is_file():
                    # Change relates to a calendar item.
                    dirname = change.watch.path.name
                    calendar = self._calendars[dirname]
                    if path.exists():
                        LOG.debug("Adding new event: %s/%s", dirname, path.name)
                        calendar.load_entry(name)
                    else:
                        LOG.debug("Removing old event: %s/%s", dirname, path.name)
                        calendar.unload_entry(name)

    @repr_factory
    def __repr__(self):
        return [repr(str(self.path))]
