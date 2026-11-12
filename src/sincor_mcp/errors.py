"""Shared capability error type. Each surface (MCP tools, HTTP gateway)
translates a CapabilityError into its own error shape."""
from __future__ import annotations


class CapabilityError(Exception):
    """A capability could not serve the request.

    code: machine-readable reason — one of
    ``bad_request`` (400), ``not_found`` (404), ``unavailable`` (503).
    """

    HTTP_STATUS = {"bad_request": 400, "not_found": 404, "unavailable": 503}

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def http_status(self) -> int:
        return self.HTTP_STATUS.get(self.code, 500)
