from typing import Optional

from py_types import TypeEndpoint


class Tunnel(object):
    def __init__(self, server: 'TunnelPoint', client: 'TunnelPoint', endpoint: Optional[TypeEndpoint] = None):
        self.server = server
        self.client = client
        self.pair = {
            self.server: self.client,
            self.client: self.server
        }
        self.connected = True
        self.endpoint = endpoint

    def build(self):
        self.server.on_tunnel_build(self)
        self.client.on_tunnel_build(self)

    def write(self, sender, data: bytes):
        if not self.connected:
            return
        receiver = self.pair[sender]
        receiver.on_tunnel_write(data)

    def close(self, sender, exc: Optional[Exception] = None):
        if not self.connected:
            return
        self.connected = False
        receiver = self.pair[sender]
        receiver.on_tunnel_close(exc)
        self.pair = {}


class FakeCloseTunnel(Tunnel):

    def __init__(self):
        self.connected = False

    def build(self):
        raise RuntimeError('fake close tunnel just support close')

    def write(self, sender, data: bytes):
        raise RuntimeError('fake close tunnel just support close')

    def close(self, sender, exc: Optional[Exception] = None):
        pass


class TunnelPoint(object):
    tunnel: 'Tunnel' = FakeCloseTunnel()

    def on_tunnel_build(self, tunnel: 'Tunnel'):
        self.tunnel = tunnel

    def on_tunnel_close(self, exc: Optional[Exception]):
        pass

    def on_tunnel_write(self, data: bytes):
        pass
