import os
import sys
import click
import requests

from pydantic import BaseModel, ValidationError
from pathlib import Path

sys.path.insert(0, str(Path.cwd().parent))
from settings import Settings


BASE_URL = f'http://{Settings.http_command_host}:{Settings.http_command_port}'


class EndPoint(BaseModel):
    host: str
    port: int


@click.group()
def cli():
    """python nat command line"""
    pass


@click.command('add')
@click.argument('endpoint')
@click.option('--bind-port', default=0, type=int, help="proxy server port bind;default: 0")
@click.option('--same-port/--no-same-port', help="proxy server port mapping endpoint port same;default no-same-port")
def add_nat_mapping(endpoint, bind_port, same_port):
    """add nat mapping with endpoint e.g: add 127.0.0.1:8888 """
    if same_port and bind_port != 0:
        click.echo('you can only use option one of (bind-port/same-port)')
        return
    host, port = endpoint.split(':')
    if same_port:
        bind_port = port
    try:
        endpoint = EndPoint(host=host, port=port)
    except ValidationError:
        click.echo(f'({endpoint}) is error endpoint!!')
        return
    response = requests.post(f'{BASE_URL}/endpoint/manager/add/', json={'bind_port': bind_port, **endpoint.dict()})
    click.echo(response.text)


@click.command('rm')
@click.argument('server_id')
def rm_nat_mapping(server_id):
    """rm nat mapping with log id e.g: rm 1 """
    response = requests.post(f'{BASE_URL}/endpoint/manager/remove/?server_id={server_id}')
    click.echo(response.text)


@click.command('ls')
def list_nat_mapping():
    """list nat mapping"""
    response = requests.get(f'{BASE_URL}/endpoint/manager/list/').json()
    for server in response:
        click.echo(server)


@click.command('watch')
def watch_nat_status():
    import asyncio
    import websockets

    # 客户端主逻辑
    async def main_logic():
        async with websockets.connect(f'ws://{Settings.http_command_host}:{Settings.http_command_port}'
                                      f'/watching') as websocket:
            while True:
                response_str = await websocket.recv()
                # print(response_str)
                print('\r' + response_str, end='', flush=True)

    asyncio.get_event_loop().run_until_complete(main_logic())


cli.add_command(add_nat_mapping)
cli.add_command(rm_nat_mapping)
cli.add_command(list_nat_mapping)
cli.add_command(watch_nat_status)

if __name__ == '__main__':
    cli()
