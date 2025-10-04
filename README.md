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

Project structure
- `src/vic_api/app.py` — App factory, middleware, router wiring
- `src/vic_api/main.py` — Entrypoint (`uvicorn vic_api.main:app`)
- `src/vic_api/core/` — Config, logging, database placeholders
- `src/vic_api/common/` — Shared middleware and context
- `src/vic_api/api/v1/` — Versioned API aggregator
- `src/vic_api/modules/` — Domain modules (e.g., health, tenants)
- `tests/` — Minimal example test (`/api/v1/health`)
- `migrations/` — Alembic environment and versioned PostgreSQL migrations

Run locally
1) Create virtualenv and install dependencies
   - `python -m venv .venv && source .venv/bin/activate`
   - `pip install -r requirements.txt`
2) Apply database migrations (PostgreSQL)
   - `alembic upgrade head`
3) Start API
   - `uvicorn vic_api.main:app --reload`
4) Visit docs
   - Swagger UI: `http://127.0.0.1:8000/docs`

Production run
- Set environment with your preferred `.env` or deployment variables
- Install with the same `requirements.txt`
- Start with Uvicorn (multi-worker, no reload):
  - `uvicorn --app-dir src vic_api.main:app --host 0.0.0.0 --port 8000 --workers 4`
- For process supervision, wrap the command with systemd, Supervisor, or a container orchestrator
- Run Alembic migrations as part of your release pipeline (`alembic upgrade head`).

Configuration
- Settings are read from environment variables (prefix `VIC_`). See `.env.example`.
- Important variables: `VIC_ENV`, `VIC_DEBUG`, `VIC_API_V1_PREFIX`, `VIC_TENANT_HEADER`, `VIC_CORS_ORIGINS`.
- Database: `VIC_DATABASE_URL`, `VIC_DB_POOL_SIZE`, `VIC_DB_MAX_OVERFLOW`, `VIC_DB_POOL_TIMEOUT`, `VIC_DB_ECHO`.
- Redis: `VIC_REDIS_URL`, `VIC_REDIS_MAX_CONNECTIONS`, `VIC_REDIS_SOCKET_TIMEOUT`.
- MongoDB: `VIC_MONGO_URL`, `VIC_MONGO_DB`, `VIC_MONGO_MIN_POOL_SIZE`, `VIC_MONGO_MAX_POOL_SIZE`.
- Observability: `VIC_OTEL_EXPORTER_OTLP_ENDPOINT`, `VIC_OTEL_EXPORTER_OTLP_PROTOCOL`, `VIC_OTEL_EXPORTER_OTLP_HEADERS`, `VIC_OTEL_SERVICE_NAME`, `VIC_OTEL_SAMPLE_RATIO`.
- Keycloak: `VIC_KEYCLOAK_SERVER_URL`, `VIC_KEYCLOAK_REALM`, `VIC_KEYCLOAK_ADMIN_USER_REALM`, `VIC_KEYCLOAK_ADMIN_USERNAME`, `VIC_KEYCLOAK_ADMIN_PASSWORD`, `VIC_KEYCLOAK_ADMIN_CLIENT_ID`, `VIC_KEYCLOAK_ADMIN_CLIENT_SECRET`, `VIC_KEYCLOAK_VERIFY_SSL`.

Connections & pools
- PostgreSQL (SQLAlchemy): engine is initialized on app startup using pool settings above.
- Redis (async): created on startup via `redis.asyncio` with a pooled client; closed on shutdown.
- MongoDB (async): created on startup via `motor` with configured pool sizes; closed on shutdown.

Examples
- Postgres: `VIC_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/dbname`
- Redis: `VIC_REDIS_URL=redis://:pass@host:6379/0`
- Mongo: `VIC_MONGO_URL=mongodb://user:pass@host:27017/?authSource=admin`
- OTLP/Jaeger gRPC: `VIC_OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317`
- OTLP/Jaeger HTTP: `VIC_OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces` with `VIC_OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`

Observability
- This scaffold integrates OpenTelemetry tracing; instrumentation activates when `VIC_OTEL_EXPORTER_OTLP_ENDPOINT` is set.
- Jaeger all-in-one: expose 4317/4318 (OTLP) and 16686 (UI). Example `docker run --rm -e COLLECTOR_OTLP_ENABLED=true -p 4317:4317 -p 4318:4318 -p 16686:16686 jaegertracing/jaeger:latest` and browse `http://localhost:16686` for service `vic-api`.
- Grafana Tempo (your current setup): keep OTLP ports 4317/4318 and map 3200 for the Tempo API. Tempo has no built-in UI—use Grafana (add an “Tempo” data source) or `tempo-query`.
- Environment variables (for either backend):
  - `VIC_OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces`
  - `VIC_OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`
  - optional `VIC_OTEL_SERVICE_NAME=vic-api` and `VIC_OTEL_SAMPLE_RATIO=1.0`
- Tenant-aware tracing: every span includes `tenant.id` (defaults to `vic` when header absent) and logs add the same field for correlation.

Multi-tenancy
- The middleware reads tenant id from `X-Tenant-ID` (configurable) and publishes it to `request.state.tenant_id`. Access via dependency `get_tenant_id`.
- Baggage/trace attributes propagate `tenant.id`, enabling Tempo/Jaeger filtering and tenant-level dashboards.

Testing
- `pytest -q`

Bootstrap super admin
- Ensure PostgreSQL and Keycloak are running with the credentials from `.env`
- Activate the virtualenv: `source venv/bin/activate`
- Run `PYTHONPATH=src python -m vic_api.scripts.create_super_admin --email admin@example.com --name "Global Admin" --temp-password changeme`
- Omit `--temp-password` to trigger the Keycloak invite flow instead of setting a password
