from typing import NoReturn, Optional, Dict, Any, List, Union
import asyncio
from asyncio.futures import Future
from asyncio.base_events import Server
from asyncio.selector_events import _SelectorSocketTransport

from loguru import logger

from settings import Settings
from utils.decorators import future_add_callback
from utils.sockets import set_socket_keepalive, get_remote_addr
from protocols import ImitateHttpProtocol, ForbiddenProtocol, CommandEnum, ProtocolAuthState, UnAuthError, AuthProtocol
from tunnel import Tunnel, TunnelPoint
from server.relay_pool import RelayPool
from broadcaster import BroadCaster, Event


class RelayProtocol(AuthProtocol, TunnelPoint):
    def __init__(self, manager_protocol):
        super().__init__()
        self.close_waiter = Future()
        self.manager_protocol = manager_protocol

    def get_close_waiter(self):
        return self.close_waiter

    def on_auth_token_checked(self, headers):
        if headers.get('ManagerSessionId') != self.manager_protocol.session_id:
            self.send(CommandEnum.ManagerEpochChange)
            self.transport.close()
            self.state = ProtocolAuthState.Expired
            return False
        return True

    def on_auth_success(self, headers):
        sock = self.transport.get_extra_info('socket')
        set_socket_keepalive(sock)

    def connection_lost(self, exc: Optional[Exception]):
        super().connection_lost(exc)
        if self.state == ProtocolAuthState.AuthSuccess:
            self.close_waiter.set_result(self)

    def on_tunnel_build(self, tunnel: Tunnel):
        super().on_tunnel_build(tunnel)
        self.send(CommandEnum.NewTunnel, headers={'Endpoint': '%s:%s' % tunnel.endpoint})

    def on_tunnel_close(self, exc: Optional[Exception]):
        self.transport.close()

    def on_tunnel_write(self, data: bytes):
        self.send(CommandEnum.Forward, body=data)

    def on_body_stream(self, body: bytes):
        self.tunnel.write(self, body)


class RelayServer(object):
    def __init__(self, pool: RelayPool, broadcaster: BroadCaster):
        self.server: Optional[Server] = None
        self.pool = pool
        self.broadcaster = broadcaster
        self.protocols: List[RelayProtocol] = []
        self.broadcaster.add_watcher(Event.ManagerProtocolClose, self.broadcaster_handle)

    def broadcaster_handle(self, event: Event, payload):
        if event == Event.ManagerProtocolClose:
            for p in self.protocols:
                p.transport.close()
                self.pool.remove(p)

    def build_protocol(self) -> Union[RelayProtocol, ForbiddenProtocol]:
        manager_protocol = self.broadcaster.manager_protocol
        if manager_protocol is None:
            return ForbiddenProtocol()
        protocol = RelayProtocol(manager_protocol)

        @future_add_callback(protocol.get_auth_waiter())
        def on_auth_success(f):
            self.protocols.append(protocol)
            self.pool.put_nowait(protocol)

        @future_add_callback(protocol.get_close_waiter())
        def on_close(f):
            self.protocols.remove(protocol)
            self.pool.remove(protocol)
        return protocol

    async def start(self) -> NoReturn:
        loop = asyncio.get_event_loop()
        self.server = await loop.create_server(
            self.build_protocol,
            host='0.0.0.0',
            port=Settings.relay_port,
        )
        logger.info(f'RelayServer serving on {"%s:%s" % self.server.sockets[0].getsockname()}')