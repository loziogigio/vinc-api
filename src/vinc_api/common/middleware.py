from __future__ import annotations

import uuid
import time
import json
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
    "/api/v1/public/",
)
ANONYMOUS_EXACT_PATHS = {"/api/v1/health", "/api/v1/public", "/api/v1/public/retailer/register"}


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
        tenant_value = tenant_id or "vinc"
        token = tenant_id_ctx_var.set(tenant_id)
        baggage_token = None
        try:
            request.state.tenant_id = tenant_id
            # Back-compat alias used by permissions code
            request.state.active_wholesaler_id = tenant_id
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
            record.tenant_id = tenant_id or "vinc"
        except Exception:
            record.tenant_id = "vinc"

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
        request.state.allowed_wholesaler_ids = authenticated.allowed_wholesaler_ids
        request.state.multi_tenant = authenticated.multi_tenant
        request.state.user_role = authenticated.role
        request.state.user_sub = authenticated.sub
        return await call_next(request)


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=401)


def _is_anonymous_path(path: str) -> bool:
    if path in ANONYMOUS_EXACT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in ANONYMOUS_PATH_PREFIXES)


class DebugLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for detailed request/response logging in DEBUG mode.
    Logs headers, query params, request/response bodies, and timing.
    """
    def __init__(self, app: ASGIApp, settings: Settings | None = None) -> None:
        super().__init__(app)
        self.settings = settings or get_settings()
        self.logger = logging.getLogger("vinc_api.debug")
        self.enabled = self.settings.DEBUG
        self.log_headers = self.settings.DEBUG_LOG_HEADERS
        self.log_body = self.settings.DEBUG_LOG_BODY
        self.max_body_length = self.settings.DEBUG_MAX_BODY_LENGTH
        self.sensitive_headers = {h.lower() for h in self.settings.debug_sensitive_headers_list}

    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]) -> Response:  # type: ignore[override]
        if not self.enabled:
            return await call_next(request)

        start_time = time.time()

        # Log request
        self._log_request(request)

        # Capture request body if needed
        request_body = None
        if self.log_body and request.method in ("POST", "PUT", "PATCH"):
            try:
                body_bytes = await request.body()
                if body_bytes:
                    request_body = body_bytes.decode("utf-8")
                    # Restore body for next middleware/endpoint
                    async def receive():
                        return {"type": "http.request", "body": body_bytes}
                    request._receive = receive
            except Exception:
                request_body = "(unable to read body)"

        # Call next middleware/endpoint
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Log response
        await self._log_response(response, duration_ms, request_body)

        return response

    def _log_request(self, request: Request) -> None:
        """Log detailed request information"""
        lines = [
            "",
            "━━━━━━━━━━━━ REQUEST ━━━━━━━━━━━━",
            f"Method: {request.method}",
            f"Path: {request.url.path}",
        ]

        # Query parameters
        if request.url.query:
            lines.append(f"Query: {request.url.query}")

        # Headers
        if self.log_headers:
            lines.append("Headers:")
            for name, value in request.headers.items():
                if name.lower() in self.sensitive_headers:
                    # Mask sensitive headers
                    if name.lower() == "authorization" and value.startswith("Bearer "):
                        masked_value = f"Bearer ***"
                    else:
                        masked_value = "***"
                    lines.append(f"  {name}: {masked_value}")
                else:
                    lines.append(f"  {name}: {value}")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        self.logger.debug("\n".join(lines))

    async def _log_response(self, response: Response, duration_ms: float, request_body: str | None) -> None:
        """Log detailed response information"""
        lines = [
            "",
            "━━━━━━━━━━━━ RESPONSE ━━━━━━━━━━━━",
            f"Status: {response.status_code}",
            f"Duration: {duration_ms:.2f}ms",
        ]

        # Headers
        if self.log_headers:
            lines.append("Headers:")
            for name, value in response.headers.items():
                lines.append(f"  {name}: {value}")

        # Body (if logging enabled)
        if self.log_body:
            # Try to read response body
            if hasattr(response, "body"):
                try:
                    body_bytes = response.body
                    if body_bytes:
                        body_text = body_bytes.decode("utf-8")

                        # Try to pretty-print JSON
                        try:
                            body_json = json.loads(body_text)
                            body_display = json.dumps(body_json, indent=2)
                        except (json.JSONDecodeError, ValueError):
                            body_display = body_text

                        # Truncate if too long
                        if len(body_display) > self.max_body_length:
                            body_display = body_display[:self.max_body_length] + f"... (truncated {len(body_display) - self.max_body_length} chars)"

                        lines.append("Body:")
                        lines.append(body_display)
                    else:
                        lines.append("Body: (empty)")
                except Exception as e:
                    lines.append(f"Body: (error reading: {e})")

            # Also log request body if available
            if request_body:
                lines.append("")
                lines.append("--- Request Body ---")
                # Try to pretty-print JSON
                try:
                    body_json = json.loads(request_body)
                    body_display = json.dumps(body_json, indent=2)
                except (json.JSONDecodeError, ValueError):
                    body_display = request_body

                # Truncate if too long
                if len(body_display) > self.max_body_length:
                    body_display = body_display[:self.max_body_length] + f"... (truncated {len(body_display) - self.max_body_length} chars)"

                lines.append(body_display)

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        self.logger.debug("\n".join(lines))
