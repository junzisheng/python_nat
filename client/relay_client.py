from typing import Dict, Any, Union, Optional
import asyncio
from asyncio.tasks import Task
from asyncio import CancelledError, Queue
from asyncio.selector_events import _SelectorSocketTransport


from settings import Settings
from py_types import TypeEndpoint
from utils.sockets import create_connection
from protocols import ImitateHttpProtocol, CommandEnum
from client.local_client import LocalProtocol
from tunnel import Tunnel, TunnelPoint


class RelayClient(ImitateHttpProtocol, TunnelPoint):
    def __init__(self, session_id):
        super().__init__()
        self.body_buffers = []
        self.tunnel: Optional[Tunnel] = None
        self.task: Optional[Task] = None
        self.session_id = session_id

    def connection_made(self, transport: _SelectorSocketTransport):
        super().connection_made(transport)
        self.send(CommandEnum.AuthRequire, headers={
            'AuthToken': Settings.auth_token,
            'ManagerSessionId': self.session_id
        })
        self.send(CommandEnum.ClientReady)

    def on_command_complete(self, command: CommandEnum, headers: Dict[str, Any]):
        if command == CommandEnum.NewTunnel:
            assert self.tunnel is None, 'repeat new Tunnel command'
            endpoint: TypeEndpoint = headers['Endpoint'].split(':')
            self.task = asyncio.get_event_loop().create_task(self.create_local_connection(endpoint))

    def on_body_stream(self, body: bytes):
        if self.tunnel:
            self.tunnel.write(self, body)
        else:
            self.body_buffers.append(body)

    def on_tunnel_write(self, data: bytes):
        self.send(CommandEnum.Forward, body=data)

    def on_tunnel_close(self, exc: Optional[Exception]):
        self.transport.close()

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if self.task:
            self.task.cancel()
        self.body_buffers = []
        if self.tunnel:
            self.tunnel.close(self)

    async def create_local_connection(self, endpoint: TypeEndpoint):
        try:
            _, client = await create_connection(LocalProtocol, *endpoint)
            self.tunnel = Tunnel(self, client)
            self.tunnel.build()
            while self.body_buffers:
                self.tunnel.write(self, self.body_buffers.pop(0))
        except CancelledError:  # closed by remote
            pass
        except Exception as e:
            self.transport.close()

