from abc import ABC
from asyncio.events import get_event_loop
from enum import IntEnum
import logging
from pathlib import Path
from typing import Dict, Optional, Type
from uuid import uuid4

from asyncinotify import Inotify, Mask, Watch
from icalendar import Calendar as vCalendar, Event as vEvent, Todo as vTodo
from icalendar.cal import Component


LOG = logging.getLogger(__name__)


MASK_CHANGE = Mask.CREATE | Mask.MODIFY | Mask.DELETE | Mask.MOVE


class MissingEntryError(TypeError):
    pass


class Entry(ABC):

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
            raise MissingEntryError("Root component must be a VCALENDAR")
        for part in component.subcomponents:
            try:
                base = cls._types[part.name]
            except KeyError:
                continue
            else:
                return base(calendar, filename)
        else:
            raise MissingEntryError("File does not contain any supported components")

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

    @property
    def uid(self):
       return str(self._core["UID"])

    @uid.setter
    def uid(self, uid):
        self._core["UID"] = uid

    def reload(self):
        if not (self.path and self.path.exists()):
            return
        with open(self.path, "rb") as raw:
            component = Component.from_ical(raw.read())
        if component.name != "VCALENDAR":
            raise MissingEntryError("Root component must be a VCALENDAR")
        for part in component.subcomponents:
            if isinstance(part, self._base):
                self._component = component
                break
        else:
            raise MissingEntryError("File does not contain any supported components")

    def save(self):
        with open(self.filename, "wb") as raw:
            raw.write(self._component.to_ical())


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

    __slots__ = ("_collection", "_dirname", "_entries_by_uid", "_entries_by_filename")

    def __init__(self, collection: "Collection", dirname: str):
        self._collection = collection
        self._dirname = dirname
        self._entries_by_uid: Dict[str, Entry] = {}
        self._entries_by_filename: Dict[str, Entry] = {}
        if self.path.exists():
            self.scan_entries()
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
        return frozenset(entry for entry in self.entries if isinstance(entry, Event))

    @property
    def tasks(self):
        return frozenset(entry for entry in self.entries if isinstance(entry, Task))

    def add_entry(self, event: Entry):
        event.calendar = self
        self._entries_by_uid[event.uid] = event
        self._entries_by_filename[event.filename] = event

    def move_entry(self, event: Entry, target: "Calendar"):
        del self._entries_by_uid[event.uid]
        del self._entries_by_filename[event.filename]
        target.add_entry(event)

    def load_entry(self, filename: str):
        path = self.path / filename
        try:
            event = Entry.load(self, filename)
        except MissingEntryError as ex:
            LOG.warning("Skipping non-entry file: %s (%s)", path, ex.args[0])
        else:
            self.add_entry(event)

    def unload_entry(self, filename: str):
        event = self._entries_by_filename.pop(filename)
        del self._entries_by_uid[event.uid]

    def scan_entries(self):
        count = 0
        LOG.debug("Scanning calendar: %s", self.dirname)
        for child in self.path.iterdir():
            if child.name.endswith(".ics"):
                self.load_entry(child.name)
                count += 1
        LOG.debug("Added %d events from %s", count, self.dirname)


class Collection:

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

    async def watch(self):
        with Inotify() as inotify:
            watches: Dict[Path, Watch] = {}
            # Watch for new and removed calendar dirs in the root.
            top = inotify.add_watch(self.path, MASK_CHANGE)
            # Watch all current directories for new, changed and removed events.
            for child in self.path.iterdir():
                if child.is_dir():
                    watches[child] = inotify.add_watch(child, MASK_CHANGE)
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
                        watches[path] = inotify.add_watch(path, MASK_CHANGE)
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
