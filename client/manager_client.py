import sys
from typing import Dict, Any, Optional
import asyncio
from asyncio.selector_events import _SelectorSocketTransport
from functools import partial

from loguru import logger

from settings import Settings
from protocols import ImitateHttpProtocol, CommandEnum
from utils.sockets import create_connection, set_socket_keepalive
from client.relay_client import RelayClient


class ManagerProtocol(ImitateHttpProtocol):
    def __init__(self, close_event: asyncio.Event):
        super().__init__()
        self.close_event = close_event
        self.tasks = set()

    def connection_made(self, transport: _SelectorSocketTransport):
        super().connection_made(transport)
        self.send(CommandEnum.AuthRequire, headers={'AuthToken': Settings.auth_token})
        sock = transport.get_extra_info('socket')
        set_socket_keepalive(sock)

    def on_command_complete(self, command: CommandEnum, headers: Dict[str, Any]):
        if command == CommandEnum.NewReplier:
            replier_num = int(headers['ReplierNum'])
            for i in range(replier_num):
                loop = asyncio.get_event_loop()
                loop.create_task(
                    create_connection(
                        partial(RelayClient, headers['ManagerSessionId']),
                        Settings.relay_host,
                        Settings.relay_port
                    )
                )
        elif command == CommandEnum.AuthSuccess:
            logger.success('Manager Connect Success')
        elif command == CommandEnum.ManagerKickOut:
            sys.exit(0)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        self.close_event.set()


class ManagerClient(object):
    async def start(self):
        while True:
            close_event = asyncio.Event()
            try:
                _, client = await create_connection(
                    partial(ManagerProtocol, close_event),
                    Settings.manager_host,
                    Settings.manager_port
                )
            except Exception as e:
                logger.warning(f'ManagerClient<{Settings.manager_host}:{Settings.manager_port}> connect fail')
                close_event.set()
                await asyncio.sleep(1)
                continue
            # logger.info(f'ManagerClient<{Settings.manager_host}:{Settings.manager_port}> connect success')
            await close_event.wait()
            logger.warning(f'ManagerClient<{Settings.manager_host}:{Settings.manager_port}> disconnect')


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    manager = ManagerClient()
    loop.run_until_complete(manager.start())
    loop.run_forever()
