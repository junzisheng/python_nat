import itertools
from typing import NoReturn, Optional, Set, Tuple, Dict, List, Union
import datetime
import asyncio
from asyncio.base_events import Server
from asyncio.futures import Future
from asyncio.tasks import Task

from loguru import logger

from py_types import TypeEndpoint
from protocols import ForbiddenProtocol, BaseProtocol
from tunnel import Tunnel, TunnelPoint, FakeCloseTunnel
from server.relay_pool import RelayPool
from server.manager_server import ManagerServer
from broadcaster import BroadCaster, Event


class ProxyProtocol(BaseProtocol, TunnelPoint):
    def __init__(self, endpoint: TypeEndpoint, close_waiter: Future, pool: RelayPool):
        super().__init__()
        self.endpoint = endpoint
        self.close_waiter = close_waiter
        self.pool = pool
        self.task: Optional[Task] = None
        self.body_buffer = []

    def connection_made(self, transport) -> NoReturn:
        super(ProxyProtocol, self).connection_made(transport)
        loop = asyncio.get_event_loop()
        self.task = loop.create_task(self.create_tunnel())

    async def create_tunnel(self):
        repeater = await self.pool.get()  # todo in case new repeater connect done, but not in use, idle more than max
        tunnel = Tunnel(self, repeater, self.endpoint)
        tunnel.build()
        while self.body_buffer:
            tunnel.write(self, self.body_buffer.pop(0))

    def connection_lost(self, exc: Optional[Exception]):
        if self.task and not self.task.done():
            self.task.cancel()

        self.body_buffer = []
        self.tunnel.close(self, exc)
        self.close_waiter.set_result(self)

    def data_received(self, data: bytes):
        if not isinstance(self.tunnel, FakeCloseTunnel):
            self.tunnel.write(self, data)
        else:
            self.body_buffer.append(data)

    def on_tunnel_close(self, exc: Optional[Exception]):
        self.transport.close()

    def on_tunnel_write(self, data: bytes):
        self.transport.write(data)


class ProxyServer(object):
    def __init__(self, server_id: int, endpoint: TypeEndpoint):
        self.sock_server: Optional[Server] = None
        self.endpoint = endpoint
        self.create_at = datetime.datetime.now()
        self.server_id = server_id
        self.protocols: List[ProxyProtocol] = []
        self.bind: Optional[TypeEndpoint] = None

    def set_sock_server(self, sock_server: Server):
        self.sock_server = sock_server
        self.bind = self.sock_server.sockets[0].getsockname()

    def build_protocol(self, pool: RelayPool) -> ProxyProtocol:
        close_waiter = Future()
        close_waiter.add_done_callback(self.remove_protocol)
        proxy_protocol = ProxyProtocol(self.endpoint, close_waiter, pool)
        self.protocols.append(proxy_protocol)
        return proxy_protocol

    def remove_protocol(self, f: Future):
        self.protocols.remove(f.result())


class ProxyServerFactory(object):
    increment_id = 0

    def __init__(self, pool: RelayPool, manager_server: ManagerServer, broadcaster: BroadCaster):
        self.servers: Dict[TypeEndpoint, Optional[ProxyServer]] = {}
        self.pool = pool
        self.manager = manager_server
        self.broadcaster = broadcaster
        self.broadcaster.add_watcher(Event.ManagerProtocolClose, self.broadcaster_handle)

    def broadcaster_handle(self, event: Event, payload):
        if event == Event.ManagerProtocolClose:
            for server in self.servers.values():
                for p in server.protocols:
                    if p.task and not p.task.done():
                        p.task.cancel()
                    p.transport.close()

    def get_server_by_id(self, server_id: int) -> Optional[ProxyServer]:
        for server in self.servers.values():
            if server.server_id == server_id:
                return server
        return None

    async def create_server(self, endpoint: TypeEndpoint, bind_port: int = 0) -> Optional[ProxyServer]:
        loop = asyncio.get_event_loop()
        if endpoint in self.servers:
            return
        # simple lock
        self.servers.setdefault(endpoint, None)
        self.increment_id += 1
        server = ProxyServer(self.increment_id, endpoint)

        def _build_protocol() -> Union[ProxyProtocol, ForbiddenProtocol]:
            if self.broadcaster.manager_protocol is None:
                return ForbiddenProtocol()
            self.broadcaster.manager_protocol.apply_new_replier(1)  # apply new relay
            protocol = server.build_protocol(self.pool)
            return protocol
        try:
            sock_server = await loop.create_server(
                _build_protocol,
                host='0.0.0.0',
                port=bind_port,
            )
        except Exception as e:
            del self.servers[endpoint]
            raise e
        server.set_sock_server(sock_server)
        logger.success(f'New ProxyServer Serving On '
                       f'{"%s:%s" % server.bind}->{"%s:%s" % endpoint}')
        self.servers[endpoint] = server
        return server

    async def close_server(self, endpoint):
        server = self.servers.get(endpoint)
        if not server:
            return
        self.servers[endpoint] = None
        sock_server = server.sock_server
        sock_server.close()
        await sock_server.wait_closed()
        for p in server.protocols:
            p.transport.close()
        del self.servers[endpoint]
        logger.success(f'ProxyServer Close Done '
                       f'{"%s:%s" % server.bind}->{"%s:%s" % endpoint}')



