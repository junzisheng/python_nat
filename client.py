import asyncio

from client.manager_client import ManagerClient

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    manager = ManagerClient()
    loop.run_until_complete(manager.start())
    loop.run_forever()
