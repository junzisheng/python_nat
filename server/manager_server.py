from typing import NoReturn, Optional, Dict, Any
import asyncio
from asyncio.futures import Future
from asyncio.base_events import Server

from loguru import logger

from settings import Settings
from utils.sockets import get_remote_addr, set_socket_keepalive
from utils.decorators import future_add_callback
from utils.tools import uid_base64
from protocols import ImitateHttpProtocol, CommandEnum, ProtocolAuthState, AuthProtocol
from broadcaster import BroadCaster, Event

MANAGER_SOCKET_IS_CLOSED = 'manager socket is closed'
MANAGER_UNCONNECTED = 'manager unconnected'


class ManagerProtocol(AuthProtocol):
    def __init__(self, epoch: int):
        super().__init__()
        self.epoch = epoch
        self.close_waiter = Future()
        self.session_id: Optional[str] = None

    def get_close_waiter(self):
        return self.close_waiter

    def connection_lost(self, exc: Optional[Exception]):
        super().connection_lost(exc)
        if self.state == ProtocolAuthState.AuthSuccess:
            self.close_waiter.set_result(self)
            logger.info(f'Manager Client<{"%s:%s" % get_remote_addr(self.transport)}> connect lost')

    def on_auth_success(self, headers):
        self.session_id = uid_base64()
        sock = self.transport.get_extra_info('socket')
        set_socket_keepalive(sock)
        logger.success(f'Manager Client<{"%s:%s" % get_remote_addr(self.transport)}> auth success')

    def on_auth_fail(self):
        logger.info(f'Manager Client<{"%s:%s" % get_remote_addr(self.transport)}> auth fail')

    def apply_new_replier(self, num=1):
        self.check_auth()
        self.send(
            CommandEnum.NewReplier,
            headers={
                'ReplierNum': num,
                'ManagerSessionId': self.session_id
            }
        )


class ManagerServer(object):
    def __init__(self, broadcaster: BroadCaster):
        self.server: Optional[Server] = None
        self.broadcaster = broadcaster
        self.epoch = 1

    def build_protocol(self) -> ManagerProtocol:
        protocol = ManagerProtocol(self.epoch)

        @future_add_callback(protocol.get_auth_waiter())
        def on_auth_done(f):
            self.epoch += 1
            # kick out active manager
            if self.broadcaster.manager_protocol:
                self.broadcaster.manager_protocol.send(CommandEnum.ManagerKickOut)
                self.broadcaster.manager_protocol.transport.close()
                self.broadcaster.fire(Event.ManagerProtocolClose, self.broadcaster.manager_protocol)

            # broadcast new manager connect
            self.broadcaster.fire(Event.ManagerProtocolValid, protocol)
            if Settings.idle_replier_num > 0:
                protocol.apply_new_replier(Settings.idle_replier_num)

        @future_add_callback(protocol.get_close_waiter())
        def on_close_done(f):
            if self.broadcaster.manager_protocol is protocol:
                self.broadcaster.fire(Event.ManagerProtocolClose, protocol)
        return protocol

    async def start(self) -> NoReturn:
        loop = asyncio.get_event_loop()
        self.server = await loop.create_server(
            self.build_protocol,
            host='0.0.0.0',
            port=Settings.manager_port,
        )
        logger.info(f'ManagerServer serving on {"%s:%s" % self.server.sockets[0].getsockname()}')


