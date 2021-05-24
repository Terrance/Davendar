from asyncio.events import get_event_loop
import logging
from pathlib import Path
from typing import Dict, Optional
from uuid import uuid4

from asyncinotify import Inotify, Mask, Watch
from icalendar.cal import Component, Calendar as vCalendar, Event as vEvent


LOG = logging.getLogger(__name__)


MASK_CHANGE = Mask.CREATE | Mask.MODIFY | Mask.DELETE | Mask.MOVE


class NoEventError(TypeError):
    pass


class Event:

    __slots__ = ("_calendar", "_filename", "_component")

    def __init__(self, calendar: Optional["Calendar"] = None, filename: Optional[str] = None):
        self._calendar = calendar
        self._filename = filename or "{}.ics".format(uuid4())
        if self._calendar and filename and self.path.exists():
            self._component = self._load()
        else:
            event = vEvent()
            event["UID"] = str(uuid4())
            self._component = vCalendar()
            self._component.add_component(event)

    @property
    def _event(self):
        return next(iter(self._component.walk("VEVENT")))  # TODO: multiple VEVENTs in one VCALENDAR

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
        return str(self._event["UID"])

    @uid.setter
    def uid(self, uid):
        self._event["UID"] = uid

    def _load(self):
        if not self.path:
            raise NoEventError("File does not exist")
        with open(self.path, "rb") as raw:
            component = Component.from_ical(raw.read())
            try:
                next(iter(component.walk("VEVENT")))
            except StopIteration:
                raise NoEventError("Component does not contain an event") from None
            else:
                return component

    def reload(self):
        self._component = self._load()

    def save(self):
        with open(self.filename, "wb") as raw:
            raw.write(self._component.to_ical())


class Calendar:

    __slots__ = ("_collection", "_dirname", "_events_by_uid", "_events_by_filename")

    def __init__(self, collection: "Collection", dirname: str):
        self._collection = collection
        self._dirname = dirname
        self._events_by_uid: Dict[str, Event] = {}
        self._events_by_filename: Dict[str, Event] = {}
        if self.path.exists():
            self.scan_events()
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
    def events(self):
        return frozenset(self._events_by_uid.values())

    def add_event(self, event: Event):
        event.calendar = self
        self._events_by_uid[event.uid] = event
        self._events_by_filename[event.filename] = event

    def move_event(self, event: Event, target: "Calendar"):
        del self._events_by_uid[event.uid]
        del self._events_by_filename[event.filename]
        target.add_event(event)

    def load_event(self, filename: str):
        path = self.path / filename
        try:
            event = Event(self, filename)
        except NoEventError:
            LOG.warning("Skipping non-event file: %s", path)
        else:
            self.add_event(event)

    def unload_event(self, filename: str):
        event = self._events_by_filename.pop(filename)
        del self._events_by_uid[event.uid]

    def scan_events(self):
        count = 0
        LOG.debug("Scanning calendar: %s", self.dirname)
        for child in self.path.iterdir():
            if child.name.endswith(".ics"):
                self.load_event(child.name)
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
                        calendar.load_event(name)
                    else:
                        LOG.debug("Removing old event: %s/%s", dirname, path.name)
                        calendar.unload_event(name)
