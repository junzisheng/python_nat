import socket
from typing import Optional, Union
import asyncio

import async_timeout


def get_remote_addr(transport):
    socket_info = transport.get_extra_info("socket")
    if socket_info is not None:
        try:
            info = socket_info.getpeername()
            return (str(info[0]), int(info[1])) if isinstance(info, tuple) else None
        except OSError:
            return None, None

    info = transport.get_extra_info("peername")
    if info is not None and isinstance(info, (list, tuple)) and len(info) == 2:
        return (str(info[0]), int(info[1]))
    return None, None


def get_local_addr(transport):
    socket_info = transport.get_extra_info("socket")
    if socket_info is not None:
        info = socket_info.getsockname()

        return (str(info[0]), int(info[1])) if isinstance(info, tuple) else None
    info = transport.get_extra_info("sockname")
    if info is not None and isinstance(info, (list, tuple)) and len(info) == 2:
        return (str(info[0]), int(info[1]))
    return None


async def create_connection(
        protocol_factory: callable,
        host: str,
        port: int,
        timeout: Optional[Union[float, int]] = None
):
    loop = asyncio.get_event_loop()
    with async_timeout.timeout(timeout):
        return await loop.create_connection(
            protocol_factory=protocol_factory,
            host=host,
            port=port,
        )


def set_socket_keepalive(sock: socket.socket,
                  tcp_keepidle: int = 2,
                  tcp_keepintval: int = 6,
                  tcp_keepcnt:int = 3):
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)  # open keepalive
    sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPIDLE, tcp_keepidle)  # idle 2
    sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPINTVL, tcp_keepintval) # interval
    sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPCNT, tcp_keepcnt)  # max retries


