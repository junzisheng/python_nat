from typing import Dict, Any, Union, Optional

from protocols import ImitateHttpProtocol, CommandEnum
from tunnel import Tunnel, TunnelPoint


class LocalProtocol(ImitateHttpProtocol, TunnelPoint):
    def on_tunnel_write(self, data: bytes):
        self.transport.write(data)

    def on_tunnel_close(self, exc: Optional[Exception]):
        self.transport.close()

    def data_received(self, data: bytes):
        self.tunnel.write(self, data)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        self.tunnel.close(self, exc)
