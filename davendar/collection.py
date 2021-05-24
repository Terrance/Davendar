from collections import defaultdict
import logging
from pathlib import Path
from typing import Dict, Set

from asyncinotify import Inotify, Mask, Watch
from icalendar import Calendar, Event


LOG = logging.getLogger(__name__)


MASK_CHANGE = Mask.CREATE | Mask.MODIFY | Mask.DELETE | Mask.MOVE


class Collection:
    
    def __init__(self, root: Path):
        self._root = root
        self._paths: Dict[Path, Set[str]] = defaultdict(set)
        self._events: Dict[str, Event] = {}

    def add(self, path: Path):
        try:
            with open(path, "rb") as raw:
                cal = Calendar.from_ical(raw.read())
        except Exception:
            LOG.warning("Failed to read %s", path, exc_info=True)
            return
        for item in cal.subcomponents:
            if isinstance(item, Event):
                uid = str(item["uid"])
                self._paths[path].add(uid)
                self._events[uid] = item

    def add_dir(self, path: Path):
        count = 0
        LOG.debug("Scanning calendar: %s", path.name)
        for item in path.iterdir():
            if item.name.endswith(".ics"):
                self.add(item)
                count += 1
        if count:
            LOG.debug("Added %d events from %s", count, path.name)

    def add_all(self):
        LOG.debug("Scanning for calendars")
        for group in self._root.iterdir():
            if group.is_dir():
                self.add_dir(group)
        LOG.debug("Finished scan")

    def remove(self, path: Path):
        uids = self._paths[path]
        for uid in uids:
            del self._events[uid]
        uids.clear()

    def remove_dir(self, path: Path):
        count = 0
        LOG.debug("Cleaning calendar: %s", path.name)
        for known in list(self._paths):
            if known.parent == path:
                self.remove(known)
                count += 1
        if count:
            LOG.debug("Removed %d events from %s", count, path.name)

    async def watch(self):
        with Inotify() as inotify:
            watches: Dict[Path, Watch] = {}
            # Watch for new and removed calendar dirs in the root.
            top = inotify.add_watch(self._root, MASK_CHANGE)
            # Watch all current directories for new, changed and removed events.
            for group in self._root.iterdir():
                if group.is_dir():
                    LOG.debug("Adding calendar watch: %s", group.name)
                    watches[group] = inotify.add_watch(group, MASK_CHANGE)
            LOG.debug("Starting inotify")
            async for event in inotify:
                if not event.name:
                    continue
                path = event.watch.path / event.name
                if event.watch is top:
                    # Event relates to the group itself.
                    watched = path in watches
                    if watched and not path.exists():
                        # Calendar was deleted or moved out of the root.
                        LOG.debug("Removing old calendar watch: %s", path.name)
                        inotify.rm_watch(watches.pop(path))
                        self.remove_dir(path)
                    elif not watched and path.is_dir():
                        # Calendar was created or moved in to the group.
                        LOG.debug("Adding new calendar watch: %s", path.name)
                        watches[path] = inotify.add_watch(path, MASK_CHANGE)
                        self.add_dir(path)
                elif event.watch is not top and path.is_file():
                    LOG.debug("Notifying for file change: %s", path)
                    if path.exists():
                        self.add(path)
                    else:
                        self.remove(path)
