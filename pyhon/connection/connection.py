from contextlib import asynccontextmanager

import aiohttp

from pyhon import const
from pyhon.connection.auth import HonAuth, _LOGGER
from pyhon.connection.device import HonDevice


class HonBaseConnectionHandler:
    _HEADERS = {"user-agent": const.USER_AGENT, "Content-Type": "application/json"}

    def __init__(self):
        self._session = None
        self._auth = None

    async def __aenter__(self):
        await self.create()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def create(self):
        self._session = aiohttp.ClientSession(headers=self._HEADERS)

    @asynccontextmanager
    async def get(self, *args, **kwargs):
        raise NotImplemented

    @asynccontextmanager
    async def post(self, *args, **kwargs):
        raise NotImplemented

    async def close(self):
        await self._session.close()


class HonConnectionHandler(HonBaseConnectionHandler):
    def __init__(self, email, password):
        super().__init__()
        self._device = HonDevice()
        self._email = email
        self._password = password
        if not self._email:
            raise PermissionError("Login-Error - An email address must be specified")
        if not self._password:
            raise PermissionError("Login-Error - A password address must be specified")
        self._request_headers = {}

    @property
    def device(self):
        return self._device

    async def create(self):
        await super().create()
        self._auth = HonAuth(self._session, self._email, self._password, self._device)

    async def _check_headers(self, headers):
        if "cognito-token" not in self._request_headers or "id-token" not in self._request_headers:
            if await self._auth.authorize():
                self._request_headers["cognito-token"] = self._auth.cognito_token
                self._request_headers["id-token"] = self._auth.id_token
            else:
                raise PermissionError("Can't Login")
        return {h: v for h, v in self._request_headers.items() if h not in headers}

    @asynccontextmanager
    async def get(self, *args, loop=0, **kwargs):
        kwargs["headers"] = await self._check_headers(kwargs.get("headers", {}))
        async with self._session.get(*args, **kwargs) as response:
            if response.status == 403 and not loop:
                _LOGGER.warning("%s - Error %s - %s", response.request_info.url, response.status, await response.text())
                await self.create()
                yield await self.get(*args, loop=loop + 1, **kwargs)
            elif loop >= 2:
                _LOGGER.error("%s - Error %s - %s", response.request_info.url, response.status, await response.text())
                raise PermissionError()
            else:
                yield response

    @asynccontextmanager
    async def post(self, *args, **kwargs):
        kwargs["headers"] = await self._check_headers(kwargs.get("headers", {}))
        async with self._session.post(*args, **kwargs) as response:
            yield response


class HonAnonymousConnectionHandler(HonBaseConnectionHandler):
    _HEADERS = HonBaseConnectionHandler._HEADERS | {"x-api-key": const.API_KEY}

    @asynccontextmanager
    async def get(self, *args, **kwargs):
        async with self._session.post(*args, **kwargs) as response:
            yield response

    @asynccontextmanager
    async def post(self, *args, **kwargs):
        async with self._session.post(*args, **kwargs) as response:
            yield response
