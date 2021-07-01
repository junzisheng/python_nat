from pydantic import BaseConfig


class Settings(BaseConfig):
    remote_host = '127.0.0.1'
    # command http web settings
    http_command_host = '127.0.0.1'
    http_command_port = 9001

    # relay settings
    relay_host = remote_host
    relay_port = 81

    # manager server settings
    manager_host = remote_host
    manager_port = 82
    idle_replier_num = 5

    # internal setting
    internal_endpoints = [
    ]
    auth_timeout = 2
    auth_token = 'AuthToken'
