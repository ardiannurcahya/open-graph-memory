
from __future__ import annotations

from typing import Any

import httpx


class OGMError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, detail: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class TransportError(OGMError): ...
class ValidationError(OGMError): ...
class AuthenticationError(OGMError): ...
class NotFoundError(OGMError): ...
class ConflictError(OGMError): ...
class PayloadTooLargeError(OGMError): ...
class UnsupportedMediaTypeError(OGMError): ...
class BadGatewayError(OGMError): ...
class ServiceUnavailableError(OGMError): ...
class ServerError(OGMError): ...

_STATUS_ERRORS: dict[int, type[OGMError]] = {
    400: ValidationError,
    401: AuthenticationError,
    404: NotFoundError,
    409: ConflictError,
    413: PayloadTooLargeError,
    415: UnsupportedMediaTypeError,
    502: BadGatewayError,
    503: ServiceUnavailableError,
}


def raise_for_response(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    try:
        body = response.json()
    except ValueError:
        body = {"detail": response.text}
    detail = body.get("detail") if isinstance(body, dict) else body
    fallback = ServerError if response.status_code >= 500 else OGMError
    cls = _STATUS_ERRORS.get(response.status_code, fallback)
    raise cls(str(detail), status_code=response.status_code, detail=detail)
