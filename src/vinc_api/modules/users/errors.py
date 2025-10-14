from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus


@dataclass(slots=True)
class UserServiceError(Exception):
    detail: str
    status_code: HTTPStatus = HTTPStatus.BAD_REQUEST

    def __str__(self) -> str:  # pragma: no cover
        return self.detail
