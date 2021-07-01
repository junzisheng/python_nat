import asyncio

import uvicorn
from fastapi import FastAPI, Request, Depends

from settings import Settings
from server.proxy_server import ProxyServerFactory
from server.relay_server import RelayServer
from command.http_web import app
from server.manager_server import ManagerServer
from server.relay_pool import RelayPool
from broadcaster import BroadCaster


def register_app(
        app: FastAPI,
):

    @app.on_event('startup')
    async def start_relay_server():
        broadcaster = BroadCaster()
        relay_pool = RelayPool(broadcaster)
        relay_server = RelayServer(relay_pool, broadcaster)
        manager_server = ManagerServer(broadcaster)
        proxy_server_factory = ProxyServerFactory(relay_pool, manager_server, broadcaster)
        setattr(app, 'proxy_pool', relay_pool)
        setattr(app, 'proxy_server_factory', proxy_server_factory)
        setattr(app, 'relay_server', relay_server)
        setattr(app, 'manager_server', manager_server)
        await relay_server.start()
        await manager_server.start()
        for inner_endpoint, bind_port in Settings.internal_endpoints:
            await proxy_server_factory.create_server(inner_endpoint, bind_port)


def run():
    register_app(app)
    uvicorn.run(app, host=Settings.http_command_host, port=Settings.http_command_port, log_level=10)


if __name__ == '__main__':
    run()
    # loop.run_forever()
