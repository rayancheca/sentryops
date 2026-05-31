"""Shared API primitives: the response envelope, pagination, and error shape."""

from __future__ import annotations

from typing import Annotated, Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

T = TypeVar("T")


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: Any | None = None


class Meta(BaseModel):
    request_id: str | None = None
    total: int | None = None
    limit: int | None = None
    offset: int | None = None


class Envelope(BaseModel, Generic[T]):
    """Consistent envelope for every API response (mirrors the error shape)."""

    success: bool = True
    data: T | None = None
    error: ErrorInfo | None = None
    meta: Meta | None = None

    @classmethod
    def ok(cls, data: T, *, meta: Meta | None = None) -> Envelope[T]:
        return cls(success=True, data=data, meta=meta)


class Page(BaseModel, Generic[T]):
    """A page of results returned inside ``Envelope[Page[X]]`` for list endpoints."""

    items: list[T]
    total: int
    limit: int
    offset: int


class PaginationParams:
    """Reusable ``limit``/``offset`` query dependency."""

    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset
