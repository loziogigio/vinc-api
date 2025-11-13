# VINC API Documentation

Complete documentation for the VINC API enterprise SaaS backend.

## 📚 Documentation Index

### Getting Started
- **[Quick Start Guide](QUICK_START.md)** - Get up and running quickly
- **[Migration Guide](MIGRATION_GUIDE.md)** - Database migration and upgrade instructions
- **[Test Results](TEST_RESULTS.md)** - Testing documentation and results

### Feature Documentation

#### Payment System
- **[Payment System Guide](payment-system.md)** - Complete payment processing documentation
  - Multi-tenant payment configuration
  - Stripe & PayPal integration
  - Webhook handling
  - Security & encryption
  - API reference
  - Setup instructions

#### BMS/ERP Integration
- **[BMS Integration Fields](bms-integration-fields.md)** - BMS/ERP field mapping
- **[BMS Backend Implementation](bms-backend-implementation.md)** - Backend integration guide

## 🏗️ Architecture Overview

### Core Modules

```
vinc-api/
├── src/vinc_api/
│   ├── api/                    # API layer (routing, dependencies)
│   ├── common/                 # Shared middleware & auth
│   ├── core/                   # Core configuration & services
│   └── modules/                # Feature modules
│       ├── customers/          # Customer management
│       ├── suppliers/          # Supplier management
│       ├── users/              # User management
│       ├── tenants/            # Multi-tenancy
│       ├── payments/           # Payment processing
│       └── public_registration/# Public API endpoints
```

### Key Features

- **Multi-Tenancy** - Complete tenant isolation with X-Tenant-ID header
- **Authentication** - Keycloak integration with JWT
- **Database** - PostgreSQL with SQLAlchemy ORM
- **Caching** - Redis for session management
- **Document Store** - MongoDB for flexible data
- **Observability** - OpenTelemetry tracing with Jaeger/Tempo
- **Payment Processing** - Multi-provider payment system

## 🚀 Quick Links

### Development
- [Quick Start Guide](QUICK_START.md) - Setup and run locally
- [Migration Guide](MIGRATION_GUIDE.md) - Database migrations
- [Test Results](TEST_RESULTS.md) - Running tests

### Integration
- [Payment System](payment-system.md) - Payment provider setup
- [BMS Integration](bms-integration-fields.md) - ERP field mapping

## 📖 API Documentation

### Interactive API Docs

Once the API is running, access interactive documentation at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### API Endpoints

#### Authentication & Users
- `POST /api/v1/users` - Create user
- `GET /api/v1/users` - List users
- `GET /api/v1/users/me` - Get current user
- `GET /api/v1/users/{user_id}` - Get user details

#### Customers & Suppliers
- `GET /api/v1/customers` - List customers
- `GET /api/v1/suppliers` - List suppliers
- `POST /api/v1/customers` - Create customer
- `POST /api/v1/suppliers` - Create supplier

#### Payments
- `GET /api/v1/payments/storefronts/{storefront_id}/methods` - Get payment methods
- `POST /api/v1/payments/intent` - Create payment intent
- `GET /api/v1/payments/{transaction_id}/status` - Get payment status
- `POST /api/v1/payments/transactions/{transaction_id}/refund` - Refund payment

See [Payment System Guide](payment-system.md) for complete payment API reference.

## 🔧 Configuration

### Environment Variables

All configuration via environment variables with `VINC_` prefix:

```bash
# Application
VINC_ENV=dev
VINC_DEBUG=true
VINC_API_V1_PREFIX=/api/v1

# Database
VINC_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/vinc
VINC_DB_POOL_SIZE=10

# Redis
VINC_REDIS_URL=redis://localhost:6379/0

# MongoDB
VINC_MONGO_URL=mongodb://localhost:27017/
VINC_MONGO_DB=vinc

# Keycloak
VINC_KEYCLOAK_SERVER_URL=http://localhost:8080
VINC_KEYCLOAK_REALM=vinc
VINC_KEYCLOAK_ADMIN_USERNAME=admin
VINC_KEYCLOAK_ADMIN_PASSWORD=admin

# Observability
VINC_OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces
VINC_OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
VINC_OTEL_SERVICE_NAME=vinc-api

# Payment System
VINC_PAYMENT_ENCRYPTION_KEY=your-secure-key-here
```

See `.env.example` for complete configuration reference.

## 🧪 Testing

### Run All Tests
```bash
pytest
```

### Run Specific Module Tests
```bash
# Payment system tests
pytest tests/modules/payments/

# User management tests
pytest tests/modules/users/

# Customer tests
pytest tests/modules/customers/
```

### Test Coverage
```bash
pytest --cov=src/vinc_api --cov-report=html
```

## 🛠️ Development Workflow

### Local Setup
1. Clone repository
2. Create virtual environment: `python -m venv .venv`
3. Install dependencies: `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and configure
5. Run migrations: `alembic upgrade head`
6. Start API: `uvicorn vinc_api.main:app --reload`

### Making Changes
1. Create feature branch
2. Make changes with tests
3. Run tests: `pytest`
4. Commit with descriptive message
5. Push and create pull request

### Database Migrations
```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Review generated migration
# Edit if needed

# Apply migration
alembic upgrade head

# Rollback if needed
alembic downgrade -1
```

## 📊 Monitoring & Observability

### Tracing
- OpenTelemetry integration
- Jaeger or Tempo backend
- Automatic instrumentation for FastAPI, SQLAlchemy, Redis, MongoDB
- Tenant-aware tracing with `tenant.id` attribute

### Logging
- Structured JSON logging
- Request ID tracking
- Tenant ID in all logs
- Configurable log levels

### Metrics
- Built-in FastAPI metrics
- Database connection pool metrics
- Custom business metrics

## 🔒 Security

### Authentication
- Keycloak JWT tokens
- Role-based access control (RBAC)
- Capability-based permissions

### Multi-Tenancy
- Header-based tenant isolation (`X-Tenant-ID`)
- Tenant data segregation
- Cross-tenant access prevention

### Payment Security
- Encrypted credential storage (Fernet)
- Webhook signature verification
- PCI compliance considerations
- No sensitive data in logs

## 🤝 Contributing

### Code Style
- Follow PEP 8
- Use type hints
- Write docstrings
- Add tests for new features

### Pull Request Process
1. Update documentation
2. Add/update tests
3. Ensure tests pass
4. Update CHANGELOG if applicable
5. Get code review approval

## 📝 Additional Resources

### External Documentation
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Keycloak Documentation](https://www.keycloak.org/documentation)
- [Stripe API Documentation](https://stripe.com/docs/api)
- [PayPal API Documentation](https://developer.paypal.com/api/rest/)

### Support
- For bugs, create an issue in the repository
- For questions, consult this documentation
- For urgent issues, contact the development team

## 📅 Changelog

See commit history for detailed changes:
```bash
git log --oneline
```

Major features:
- ✅ Multi-tenant architecture
- ✅ Keycloak authentication
- ✅ User management with roles
- ✅ Customer and supplier management
- ✅ BMS/ERP integration
- ✅ Payment processing system
- ✅ OpenTelemetry observability

---

**Last Updated**: November 2025
**Version**: 1.0.0
**License**: Proprietary
