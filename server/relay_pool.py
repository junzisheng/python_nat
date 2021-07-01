from typing import Set
from asyncio import Queue

from loguru import logger

from broadcaster import BroadCaster


class RelayPool(Queue):
    def __init__(self, broadcaster: BroadCaster, loop=None):
        super().__init__(loop=loop)
        self._watchers: Set[callable] = set()
        self.broadcaster = broadcaster

    def add_watcher(self, watcher: callable):
        self._watchers.add(watcher)

    def remove_watcher(self, watcher: callable):
        self._watchers.discard(watcher)

    def notify_watcher(self, event):
        for watcher in self._watchers:
            watcher(event)

    def put_nowait(self, item):
        super().put_nowait(item)
        self.notify_watcher({
            'event': 'new_replier',
            'payload': item,
        })

    def get_nowait(self):
        item = super().get_nowait()
        self.notify_watcher({
            'event': 'pop_replier',
            'payload': item,
        })
        return item

    def remove(self, item):
        try:
            self._queue.remove(item)
            self.notify_watcher({
                'event': 'pop_replier',
                'payload': item,
            })
        except ValueError:
            pass
