import asyncio
from asyncio import Event

from fastapi import FastAPI, WebSocket, APIRouter, Request, Depends, Body, WebSocketDisconnect

from server.proxy_server import ProxyServerFactory, ProxyServer, RelayPool
from server.relay_server import RelayServer
from server.manager_server import ManagerServer

endpoint_manager_router = APIRouter(prefix='/endpoint/manager')


app = FastAPI()


def get_proxy_server_factory():
    return getattr(app, 'proxy_server_factory', None)


def get_proxy_pool():
    return getattr(app, 'proxy_pool', None)


def get_relay_server():
    return getattr(app, 'relay_server', None)


def get_manager_server():
    return getattr(app, 'manager_server', None)


@endpoint_manager_router.post('/add/')
async def endpoint_add(host: str = Body(...), port: int = Body(...), bind_port: int = Body(0),
                       proxy_server_factory: ProxyServerFactory = Depends(get_proxy_server_factory)):
    endpoint = (host, port)
    server = proxy_server_factory.servers.get(endpoint, 0)
    if server is None:
        return f"warning: {'%s:%s' % endpoint} is creating"
    elif server == 0:
        try:
            server = await proxy_server_factory.create_server(endpoint, bind_port)
        except Exception as e:
            return f"error: {'%s:%s' % endpoint} create fail: {e}"
        return f"success: {'%s:%s' % endpoint} --> {'%s:%s' % server.bind } created"
    else:
        return f"warning: {'%s:%s' % endpoint} was created"


@endpoint_manager_router.post('/remove/')
async def endpoint_remove(server_id: int,
                          proxy_server_factory: ProxyServerFactory = Depends(get_proxy_server_factory)):
    server = proxy_server_factory.get_server_by_id(server_id)
    if server is None:
        return f"warning: server(id={server_id}) not exist"
    else:
        await proxy_server_factory.close_server(server.endpoint)
        return f"success: server(id={server_id})@{'%s:%s' % server.endpoint} remove done"


@endpoint_manager_router.get('/list/')
async def endpoint_list(proxy_server_factory: ProxyServerFactory = Depends(get_proxy_server_factory)):
    server_list = list(proxy_server_factory.servers.values())
    server_list = list(filter(lambda x:x is not None, server_list))
    server_list.sort(key=lambda x: x.server_id)
    return [
        {
            'id': server.server_id,
            'server':  server.bind,
            'endpoint': '%s:%s' % server.endpoint,
            'create_at': server.create_at,
        }
        for server in server_list
    ]


@endpoint_manager_router.websocket('/watching')
async def endpoint_watching(
        websocket: WebSocket,
        pool: RelayPool = Depends(get_proxy_pool),
        relay_server: RelayServer = Depends(get_relay_server),
        manager_server: ManagerServer = Depends(get_manager_server)
):
    await websocket.accept()

    def pool_watcher(event):
        loop = asyncio.get_event_loop()
        loop.create_task(
            websocket.send_json({'pool_size_change': pool.qsize()})
        )
    pool.add_watcher(pool_watcher)
    while True:
        message = await websocket.receive()
        message_type = message["type"]
        if message_type == "websocket.disconnect":
            break
    pool.remove_watcher(pool_watcher)


app.include_router(endpoint_manager_router)
# def get_app(dependencies=None):
#     app = FastAPI(dependencies=dependencies)
#     app.include_router(endpoint_manager_router)
#     return app
