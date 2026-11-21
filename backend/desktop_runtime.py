"""Private in-process transport for the desktop window."""

import hmac
import socket
from threading import Thread
from time import monotonic, sleep

from starlette.responses import PlainTextResponse
import uvicorn

TOKEN_HEADER = b"x-market-desktop-token"


class DesktopAccess:
    def __init__(self, app, token):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            supplied = dict(scope["headers"]).get(TOKEN_HEADER, b"")
            if not hmac.compare_digest(supplied, self.token):
                await PlainTextResponse("Acceso reservado a la aplicación", 403)(scope, receive, send)
                return
        await self.app(scope, receive, send)


class DesktopRuntime:
    def __init__(self, app, token):
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.port = self.listener.getsockname()[1]
        self.server = uvicorn.Server(uvicorn.Config(
            DesktopAccess(app, token), loop="asyncio", http="h11", ws="none",
            lifespan="on", log_config=None, access_log=False, timeout_graceful_shutdown=3,
        ))
        self.thread = Thread(target=self.server.run, kwargs={"sockets": [self.listener]}, daemon=True)

    def __enter__(self):
        self.thread.start()
        deadline = monotonic() + 10
        while self.thread.is_alive() and monotonic() < deadline:
            if self.server.started:
                return self
            sleep(.02)
        self.__exit__(None, None, None)
        raise RuntimeError("No se pudo iniciar el motor de análisis")

    def __exit__(self, *_):
        self.server.should_exit = True
        self.thread.join(timeout=5)
        self.listener.close()
