from io import BytesIO
import enum
from typing import Optional, NoReturn, Tuple, Dict, Any
import asyncio
from asyncio.futures import Future
from asyncio import Protocol
from asyncio.selector_events import _SelectorSocketTransport

from loguru import logger

from settings import Settings
from utils.sockets import get_local_addr, get_remote_addr


class CommandEnum(str, enum.Enum):
    Forward = 'Forward'
    NewTunnel = 'NewTunnel'
    CloseTunnel = 'CloseTunnel'
    ClientReady = 'ClientReady'
    NewReplier = 'NewReplier'
    AuthRequire = 'AuthRequire'
    AuthSuccess = 'AuthSuccess'
    ManagerEpochChange = 'ManagerEpochChange'
    ManagerKickOut = 'ManagerKickOut'


class ProtocolAuthState(str, enum.Enum):
    WaitAuth = 'WaitAuth'
    AuthSuccess = 'AuthSuccess'
    AuthFail = 'AuthFail'
    Expired = 'Expired'


class UnAuthError(Exception):
    pass


class ImitateHttpParserError(Exception):
    pass


class ParserCallbackError(Exception):
    pass


class BaseProtocol(Protocol):
    def __init__(self) -> NoReturn:
        self._loop = asyncio.get_event_loop()

        # Per-connection state
        self.transport: Optional[_SelectorSocketTransport] = None
        self.server: Optional[Tuple[str, int]] = None
        self.client: Optional[Tuple[str, int]] = None

    def connection_made(self, transport: _SelectorSocketTransport) -> NoReturn:
        self.transport = transport
        self.server = get_local_addr(transport) or (None, None)
        self.client = get_remote_addr(transport) or (None, None)


class ForbiddenProtocol(Protocol):
    def connection_made(self, transport: _SelectorSocketTransport):
        transport.close()


class ImitateHttpProtocol(BaseProtocol):
    def __init__(self):
        super().__init__()
        self.parser = ImitateHttpParser(self)

    def on_command_complete(self, command: CommandEnum, headers: Dict[str, Any]):
        pass

    def on_body_stream(self, body: bytes):
        pass

    def command_complete(self, command: CommandEnum, headers: Dict[str, Any]):
        self.on_command_complete(command, headers)

    def body_stream(self, body: bytes):
        self.on_body_stream(body)

    def data_received(self, data: bytes):
        try:
            self.parser.feed_data(data)
        except ParserCallbackError:
            raise
        except ImitateHttpParserError as e:
            msg = f"<{get_remote_addr(self.transport)}> Invalid HTTP request received: \n {e}"
            logger.warning(msg)
            self.transport.close()

    def send(self, command: CommandEnum, headers: Optional[Dict[str, Any]] = None, body: bytes = b''):
        header_list = [f'Command: {command}']
        if headers:
            for hk, hv in headers.items():
                header_list.append(f'{hk}: {hv}')
        header_list.append('')

        content_bytes = '\n'.join(header_list).encode()
        if body:
            content_bytes += b'ContentLength: %d\n\n%s' % (len(body), body)
        else:
            content_bytes += b'\n'
        self.transport.write(content_bytes)


class ImitateHttpParser(object):
    class ParseStateEnum(str, enum.Enum):
        header_parse = 'header_parse'
        body_stream = 'body_stream'

    def __init__(self, protocol: ImitateHttpProtocol):
        self.protocol = protocol
        self.reset()
        self.state = self.ParseStateEnum.header_parse
        self.command = ''
        self.headers = {}
        self.unprocessed = b''
        self.expected_body_length = 0

    def reset(self):
        self.state = self.ParseStateEnum.header_parse
        self.command = ''
        self.headers = {}
        self.unprocessed = b''
        self.expected_body_length = 0

    def feed_data(self, data: bytes):
        try:
            if self.state == self.ParseStateEnum.header_parse:
                f = BytesIO(self.unprocessed + data)
                self.unprocessed = b''
                self.parse_header(f)
            elif self.state == self.ParseStateEnum.body_stream:
                self.parse_body(data)
        except ParserCallbackError:
            self.reset()
            raise
        except Exception as e:
            self.reset()
            raise ImitateHttpParserError(e)


    def catch_callback_error(self, func, *args, **kwargs):
        try:
            func(*args, **kwargs)
        except Exception as e:
            raise ParserCallbackError(e)

    def parse_header(self, f: BytesIO):
        while True:
            header = f.readline()
            if header == b'\n':  # header parse done
                if not self.command:
                    raise ImitateHttpParserError('header parse complete without command')
                content_length = self.headers.get('ContentLength')
                if content_length:
                    self.headers['ContentLength'] \
                        = self.expected_body_length = int(content_length)
                    if self.headers['ContentLength'] <= 0:
                        raise ImitateHttpParserError('content length must gt than 0')
                    self.state = self.ParseStateEnum.body_stream

                self.catch_callback_error(
                    self.protocol.command_complete,
                    self.command,
                    self.headers
                )

                if self.state == self.ParseStateEnum.body_stream:
                    body_data = f.read()
                    if body_data:
                        self.parse_body(body_data)
                    return
                else:
                    self.reset()
                    another_command = f.read()
                    if another_command:
                        self.parse_header(BytesIO(another_command))

            elif header.endswith(b'\n'):  # parse a single header line
                header = header.strip().decode()
                header_k, header_v = header.split(':', 1)
                if header_k == 'Command':
                    self.command = header_v.strip()
                else:
                    self.headers[header_k] = header_v.strip()

            elif header == b'':  # data end
                return
            else:
                self.unprocessed = header

    def parse_body(self, data: bytes):
        expected_body_length = self.expected_body_length
        body_length = len(data)
        body = data[:expected_body_length]
        self.catch_callback_error(
            self.protocol.body_stream,
            body
        )

        if body_length < expected_body_length:
            self.expected_body_length -= body_length
        elif body_length == expected_body_length:
            self.reset()
        else:
            self.reset()
            self.parse_header(BytesIO(data[expected_body_length:]))


class AuthProtocol(ImitateHttpProtocol):
    AuthTimeout = Settings.auth_timeout
    AuthToken = Settings.auth_token

    def __init__(self):
        super().__init__()
        self.state = ProtocolAuthState.WaitAuth
        self.auth_timer: Optional[Future] = None
        self.auth_waiter = Future()

    def get_auth_waiter(self):
        return self.auth_waiter

    def check_auth(self):
        if self.state != ProtocolAuthState.AuthSuccess:
            self.transport.close()
            raise UnAuthError(f'state: {self.state}, unAuthed!')

    def connection_made(self, transport):
        super().connection_made(transport)

        # start auth timer
        def _auth_timer():
            if self.state != ProtocolAuthState.AuthSuccess:
                transport.close()
        self.auth_timer = asyncio.get_event_loop().call_later(
            self.AuthTimeout,
            _auth_timer
        )

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if self.state != ProtocolAuthState.AuthSuccess:
            self.auth_timer.cancel()

    def on_auth_token_checked(self, headers):
        return True

    def command_complete(self, command: CommandEnum, headers: Dict[str, Any]):
        if command == CommandEnum.AuthRequire:
            self.auth_timer.cancel()
            if headers.get('AuthToken') == self.AuthToken:
                if self.on_auth_token_checked(headers):
                    self.state = ProtocolAuthState.AuthSuccess
                    self.send(CommandEnum.AuthSuccess)
                    self.auth_waiter.set_result(self)
                    self.on_auth_success(headers)
            else:
                self.state = ProtocolAuthState.AuthFail
                self.transport.close()
                self.on_auth_fail()
        else:
            self.check_auth()
            self.on_command_complete(command, headers)

    def body_stream(self, body: bytes):
        self.check_auth()
        self.on_body_stream(body)

    def on_auth_success(self, headers):
        pass

    def on_auth_fail(self):
        pass
