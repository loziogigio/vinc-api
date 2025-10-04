from __future__ import annotations

import uuid
import contextvars
import logging
from typing import Callable

from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

try:
    from opentelemetry import trace
except Exception:  # pragma: no cover
    trace = None  # type: ignore

try:
    from opentelemetry import baggage
    from opentelemetry.context import attach, detach
except Exception:  # pragma: no cover
    baggage = None  # type: ignore
    attach = detach = None  # type: ignore


from ..core.config import Settings, get_settings
from .auth import JWTVerifier


tenant_id_ctx_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("tenant_id", default=None)
request_id_ctx_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

ANONYMOUS_PATH_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi",
)
ANONYMOUS_EXACT_PATHS = {"/api/v1/health"}


class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]) -> Response:  # type: ignore[override]
        req_id = request.headers.get(self.header_name) or str(uuid.uuid4())
        token = request_id_ctx_var.set(req_id)
        try:
            request.state.request_id = req_id
            response = await call_next(request)
        finally:
            request_id_ctx_var.reset(token)
        response.headers.setdefault(self.header_name, req_id)
        return response


class TenantContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, header_name: str = "X-Tenant-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]) -> Response:  # type: ignore[override]
        tenant_id = request.headers.get(self.header_name)
        tenant_value = tenant_id or "vic"
        token = tenant_id_ctx_var.set(tenant_id)
        baggage_token = None
        try:
            request.state.tenant_id = tenant_id
            if trace is not None:
                try:
                    span = trace.get_current_span()
                    if span and span.is_recording():
                        span.set_attribute("tenant.id", tenant_value)
                except Exception:  # pragma: no cover
                    pass
            if baggage is not None and attach is not None:
                try:
                    context = baggage.set_baggage("tenant.id", tenant_value)
                    baggage_token = attach(context)
                except Exception:  # pragma: no cover
                    baggage_token = None
            response = await call_next(request)
        finally:
            tenant_id_ctx_var.reset(token)
            if baggage_token is not None and detach is not None:
                try:
                    detach(baggage_token)
                except Exception:  # pragma: no cover
                    pass
        return response


class RequestIDLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - pure logging
        try:
            record.request_id = request_id_ctx_var.get()
        except Exception:
            record.request_id = "-"

        try:
            tenant_id = tenant_id_ctx_var.get()
            record.tenant_id = tenant_id or "vic"
        except Exception:
            record.tenant_id = "vic"

        if trace is not None:
            try:
                span = trace.get_current_span()
                span_ctx = span.get_span_context() if span else None
                if span_ctx and span_ctx.trace_id:
                    record.trace_id = f"{span_ctx.trace_id:032x}"
                    record.span_id = f"{span_ctx.span_id:016x}"
                else:
                    record.trace_id = record.span_id = "-"
            except Exception:
                record.trace_id = record.span_id = "-"
        else:
            record.trace_id = record.span_id = "-"
        return True


class JWTAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: Settings | None = None) -> None:
        super().__init__(app)
        self.settings = settings or get_settings()
        self.verifier = JWTVerifier(self.settings)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]) -> Response:  # type: ignore[override]
        if not self.settings.JWT_ENABLED or _is_anonymous_path(request.url.path):
            return await call_next(request)

        authorization = request.headers.get("Authorization")
        if not authorization or not authorization.startswith("Bearer "):
            return _unauthorized("Missing bearer token")

        token = authorization[7:].strip()
        try:
            authenticated = await run_in_threadpool(self.verifier.authenticate, token)
        except ValueError as exc:
            return _unauthorized(str(exc))

        request.state.authenticated_user = authenticated
        request.state.claims = authenticated.raw_claims
        request.state.allowed_address_ids = authenticated.allowed_address_ids
        request.state.allowed_customer_ids = authenticated.allowed_customer_ids
        request.state.user_role = authenticated.role
        request.state.user_sub = authenticated.sub
        return await call_next(request)


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=401)


def _is_anonymous_path(path: str) -> bool:
    if path in ANONYMOUS_EXACT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in ANONYMOUS_PATH_PREFIXES)
