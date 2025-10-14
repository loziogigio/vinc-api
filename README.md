Enterprise-grade FastAPI API Skeleton (SaaS)

This repository contains a modular, enterprise-ready FastAPI application scaffold tailored for SaaS backends. It focuses on clear separation of concerns, versioned APIs, tenant awareness, and extensibility.

Key features

- App factory pattern with environment-based settings
- Versioned API routing (`/api/v1`) and modular routers
- Tenant-aware middleware via `X-Tenant-ID` header
- Request ID middleware for traceability
- CORS and GZip middleware pre-configured
- Structured layout for domain modules (e.g., tenants)
- User provisioning module with Keycloak bootstrap and persisted customer/address links
- Role aliasing: `supplier_admin` ↔ `wholesale_admin`, `supplier_helpdesk` ↔ `wholesaler_helpdesk`
- Optional memberships in MongoDB to support multi-wholesaler scopes and capabilities
- Scoped Keycloak attributes: `allowed_wholesalers` and `multi_tenant` for multi-wholesaler accounts

Project structure

- `src/vinc_api/app.py` — App factory, middleware, router wiring
- `src/vinc_api/main.py` — Entrypoint (`uvicorn vinc_api.main:app`)
- `src/vinc_api/core/` — Config, logging, database placeholders
- `src/vinc_api/common/` — Shared middleware and context
- `src/vinc_api/api/v1/` — Versioned API aggregator
- `src/vinc_api/modules/` — Domain modules (e.g., health, tenants)
- `tests/` — Minimal example test (`/api/v1/health`)
- `migrations/` — Alembic environment and versioned PostgreSQL migrations

Run locally

1) Create virtualenv and install dependencies
   - `python -m venv .venv && source .venv/bin/activate`
   - `pip install -r requirements.txt`
2) Apply database migrations (PostgreSQL)
   - `alembic upgrade head`
3) Start API
   - `uvicorn vinc_api.main:app --reload`
4) Visit docs
   - Swagger UI: `http://127.0.0.1:8000/docs`

Email testing (Mailpit)

- The compose stack exposes Mailpit at `http://localhost:8025`; use the container hostname `saleor-platform-mailpit-1` from other services.
- In Keycloak → Realm Settings → Email set host `saleor-platform-mailpit-1`, port `1025`, disable TLS/auth for local testing.
- Once configured, invites sent by `/api/v1/public/retailer/register` appear instantly in the Mailpit inbox for easy verification.

Production run

- Set environment with your preferred `.env` or deployment variables
- Install with the same `requirements.txt`
- Start with Uvicorn (multi-worker, no reload):
  - `uvicorn --app-dir src vinc_api.main:app --host 0.0.0.0 --port 8000 --workers 4`
- For process supervision, wrap the command with systemd, Supervisor, or a container orchestrator
- Run Alembic migrations as part of your release pipeline (`alembic upgrade head`).

Configuration

- Settings are read from environment variables (prefix `VINC_`). See `.env.example`.
- Important variables: `VINC_ENV`, `VINC_DEBUG`, `VINC_API_V1_PREFIX`, `VINC_TENANT_HEADER`, `VINC_CORS_ORIGINS`.
- Database: `VINC_DATABASE_URL`, `VINC_DB_POOL_SIZE`, `VINC_DB_MAX_OVERFLOW`, `VINC_DB_POOL_TIMEOUT`, `VINC_DB_ECHO`.
- Redis: `VINC_REDIS_URL`, `VINC_REDIS_MAX_CONNECTIONS`, `VINC_REDIS_SOCKET_TIMEOUT`.
- MongoDB: `VINC_MONGO_URL`, `VINC_MONGO_DB`, `VINC_MONGO_MIN_POOL_SIZE`, `VINC_MONGO_MAX_POOL_SIZE`.
- Observability: `VINC_OTEL_EXPORTER_OTLP_ENDPOINT`, `VINC_OTEL_EXPORTER_OTLP_PROTOCOL`, `VINC_OTEL_EXPORTER_OTLP_HEADERS`, `VINC_OTEL_SERVICE_NAME`, `VINC_OTEL_SAMPLE_RATIO`.
- Keycloak: `VINC_KEYCLOAK_SERVER_URL`, `VINC_KEYCLOAK_REALM`, `VINC_KEYCLOAK_ADMIN_USER_REALM`, `VINC_KEYCLOAK_ADMIN_USERNAME`, `VINC_KEYCLOAK_ADMIN_PASSWORD`, `VINC_KEYCLOAK_ADMIN_CLIENT_ID`, `VINC_KEYCLOAK_ADMIN_CLIENT_SECRET`, `VINC_KEYCLOAK_VERIFY_SSL`.

Connections & pools

- PostgreSQL (SQLAlchemy): engine is initialized on app startup using pool settings above.
- Redis (async): created on startup via `redis.asyncio` with a pooled client; closed on shutdown.
- MongoDB (async): created on startup via `motor` with configured pool sizes; closed on shutdown.

Examples

- Postgres: `VINC_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/dbname`
- Redis: `VINC_REDIS_URL=redis://:pass@host:6379/0`
- Mongo: `VINC_MONGO_URL=mongodb://user:pass@host:27017/?authSource=admin`
- OTLP/Jaeger gRPC: `VINC_OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317`
- OTLP/Jaeger HTTP: `VINC_OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces` with `VINC_OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`

Observability

- This scaffold integrates OpenTelemetry tracing; instrumentation activates when `VINC_OTEL_EXPORTER_OTLP_ENDPOINT` is set.
- Jaeger all-in-one: expose 4317/4318 (OTLP) and 16686 (UI). Example `docker run --rm -e COLLECTOR_OTLP_ENABLED=true -p 4317:4317 -p 4318:4318 -p 16686:16686 jaegertracing/jaeger:latest` and browse `http://localhost:16686` for service `vinc-api`.
- Grafana Tempo (your current setup): keep OTLP ports 4317/4318 and map 3200 for the Tempo API. Tempo has no built-in UI—use Grafana (add an “Tempo” data source) or `tempo-query`.
- Environment variables (for either backend):
  - `VINC_OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces`
  - `VINC_OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`
  - optional `VINC_OTEL_SERVICE_NAME=vinc-api` and `VINC_OTEL_SAMPLE_RATIO=1.0`
- Tenant-aware tracing: every span includes `tenant.id` (defaults to `vinc` when header absent) and logs add the same field for correlation.

Multi-tenancy

- The middleware reads tenant id from `X-Tenant-ID` (configurable) and publishes it to `request.state.tenant_id`. Access via dependency `get_tenant_id`.
- Alias `request.state.active_wholesaler_id` mirrors the same value for permissions code.
- Baggage/trace attributes propagate `tenant.id`, enabling Tempo/Jaeger filtering and tenant-level dashboards.

Memberships (optional)

- Stored in MongoDB collection `user_memberships` as:
  - `{ user_key, default_role, memberships: [{ scope_type: 'supplier'|'global'|..., scope_id, role, capabilities, ... }] }`
- Endpoints:
  - `GET /api/v1/users/{user_id}/memberships` (super/supplier admin)
  - `PUT /api/v1/users/{user_id}/memberships` (super/supplier admin)
- `/api/v1/users/me` embeds the membership document when available.
- Single-wholesaler memberships continue to stamp `allowed_customers` / `allowed_addresses` for backwards compatibility.
- Multi-wholesaler memberships omit customer/address stamping and rely on runtime resolution, setting `allowed_wholesalers` plus `multi_tenant=true` claims.

Capabilities

- Use `require_capabilities(*caps)` to guard routes by effective capabilities for the active wholesaler (`X-Tenant-ID`).
- Backward compatibility: `require_roles(*roles)` accepts both legacy and new names.

Testing

- `pytest -q`

Bootstrap super admin

- Ensure PostgreSQL and Keycloak are running with the credentials from `.env`
- Activate the virtualenv: `source venv/bin/activate`
- Run `PYTHONPATH=src python -m vinc_api.scripts.create_super_admin --email admin@example.com --name "Global Admin" --temp-password changeme`
- Omit `--temp-password` to trigger the Keycloak invite flow instead of setting a password
