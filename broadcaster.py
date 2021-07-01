import enum
from collections import defaultdict
from typing import Callable, NoReturn, Any, Dict, List

class Event(enum.Enum):
    All = '*'
    ManagerProtocolValid = 'ManagerProtocolValid'
    ManagerProtocolClose = 'ManagerProtocolClose'

TypeEventHandler = Callable[[Event, Any], NoReturn]


class BroadCaster(object):
    def __init__(self):
        from server.manager_server import ManagerProtocol
        self.watchers = defaultdict(set)
        self.handlers: Dict[Event,  List[TypeEventHandler]] = defaultdict(list)
        self.manager_protocol: ManagerProtocol = None


    def listen_events(self, event: Event, payload):
        if event == Event.ManagerProtocolValid:
            self.manager_protocol = payload
        elif event == Event.ManagerProtocolClose:
            if self.manager_protocol is payload:
                self.manager_protocol = None

    def fire(self, event: Event, payload=None):
        assert event != Event.All, 'Event All cannot be fired'
        self.listen_events(event, payload)
        for handler in (self.watchers[Event.All] | self.watchers[event]):
            handler(event, payload)

    def add_watcher(self, event: Event, handler: TypeEventHandler):
        self.watchers[event].add(handler)
        self.handlers[handler].append(event)

    def remove_watcher(self, handler: TypeEventHandler):
        event_list = self.handlers.pop(handler, None)
        for event in event_list:
            self.watchers[event].discard(handler)

