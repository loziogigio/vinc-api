# Payment System Documentation

## Overview

The VINC API payment system provides a comprehensive, multi-tenant payment processing solution with support for multiple payment providers. The system features two-level configuration (tenant/wholesaler and storefront/retailer), complete transaction logging, webhook handling, and extensive security measures.

## Supported Payment Providers

- **Stripe**: Card payments, digital wallets (Apple Pay, Google Pay), SEPA Direct Debit
- **PayPal**: PayPal wallet, PayPal Credit
- **Extensible**: Easy to add Nexi, Banca Sella, Scalapay, bank transfers, and other providers

## Architecture

### Two-Level Configuration

1. **Tenant Level (Wholesaler)**: Wholesalers configure payment providers with their credentials
2. **Storefront Level (Retailer)**: Retailers enable specific payment methods for their storefronts

This architecture allows:
- Wholesalers to manage payment provider credentials centrally
- Retailers to choose which payment methods to offer customers
- Custom display names and conditions per storefront

### Key Components

```
src/vinc_api/modules/payments/
├── models.py              # SQLAlchemy database models
├── schemas.py             # Pydantic request/response models
├── service.py             # Business logic layer
├── router.py              # FastAPI API endpoints
├── providers/             # Payment provider implementations
│   ├── base.py           # Abstract base class
│   ├── stripe.py         # Stripe implementation
│   └── paypal.py         # PayPal implementation
├── webhooks/              # Webhook handlers
│   ├── stripe.py         # Stripe webhook handler
│   └── paypal.py         # PayPal webhook handler
└── utils/
    └── encryption.py      # Credentials encryption
```

## Database Models

### TenantPaymentProvider
Stores payment provider configurations for wholesalers:
- Provider type (stripe, paypal, etc.)
- Encrypted credentials
- Mode (test/live)
- Fee configuration
- Provider-specific settings

### StorefrontPaymentMethod
Enables payment methods for storefronts:
- Links to tenant provider
- Custom display name/description
- Display order
- Conditions (min/max cart amount)

### PaymentTransaction
Complete audit trail of all payments:
- Transaction status
- Amount and currency
- Provider details
- Webhook events
- Refund information
- Timestamps

### PaymentWebhookLog
Logs all webhook events for debugging:
- Provider and event type
- Complete payload
- Processing status
- Execution time

## API Endpoints

### Public Endpoints (Storefront Checkout)

#### Get Available Payment Methods
```http
GET /api/v1/payments/storefronts/{storefront_id}/methods?amount=100&currency=EUR
```

Returns available payment methods for checkout based on cart amount and storefront configuration.

#### Create Payment Intent
```http
POST /api/v1/payments/intent
Content-Type: application/json

{
  "storefront_id": "uuid",
  "order_id": "uuid",
  "provider": "stripe",
  "amount": 100.00,
  "currency": "EUR",
  "customer_email": "customer@example.com",
  "return_url": "https://storefront.com/success",
  "cancel_url": "https://storefront.com/cancel"
}
```

Creates a payment intent and returns client secret or redirect URL.

#### Get Payment Status
```http
GET /api/v1/payments/{transaction_id}/status
```

Check the current status of a payment transaction.

### Admin Endpoints (Wholesaler)

#### Configure Payment Provider
```http
POST /api/v1/payments/tenants/{tenant_id}/providers
Content-Type: application/json
Authorization: Bearer {token}

{
  "provider": "stripe",
  "credentials": {
    "secret_key": "sk_live_...",
    "publishable_key": "pk_live_...",
    "webhook_secret": "whsec_..."
  },
  "mode": "live",
  "fee_bearer": "wholesaler",
  "fees": {
    "percentage": 2.9,
    "fixed": 0.30
  }
}
```

Credentials are automatically encrypted before storage.

#### List Tenant Providers
```http
GET /api/v1/payments/tenants/{tenant_id}/providers
Authorization: Bearer {token}
```

Returns all configured payment providers (credentials not exposed).

#### Update Provider
```http
PATCH /api/v1/payments/tenants/{tenant_id}/providers/{provider_id}
Content-Type: application/json
Authorization: Bearer {token}

{
  "is_enabled": false
}
```

### Admin Endpoints (Retailer)

#### Enable Storefront Payment Method
```http
POST /api/v1/payments/storefronts/{storefront_id}/methods
Content-Type: application/json
Authorization: Bearer {token}
X-Tenant-ID: {tenant_id}

{
  "provider": "stripe",
  "is_enabled": true,
  "display_name": "Credit or Debit Card",
  "display_description": "Pay securely with your card",
  "display_order": 0,
  "conditions": {
    "min_cart": 5.00,
    "max_cart": 10000.00
  }
}
```

### Transaction Management

#### Get Transaction Logs
```http
GET /api/v1/payments/transactions?tenant_id={uuid}&status=succeeded&limit=100
Authorization: Bearer {token}
```

#### Refund Payment
```http
POST /api/v1/payments/transactions/{transaction_id}/refund
Content-Type: application/json
Authorization: Bearer {token}

{
  "amount": 50.00,
  "reason": "Customer request"
}
```

#### Get Analytics
```http
GET /api/v1/payments/analytics?tenant_id={uuid}&start_date=2024-01-01&end_date=2024-12-31
Authorization: Bearer {token}
```

## Webhook Endpoints

### Stripe Webhooks
```http
POST /api/v1/payments/webhooks/stripe
Stripe-Signature: {signature}
Content-Type: application/json

{webhook payload}
```

### PayPal Webhooks
```http
POST /api/v1/payments/webhooks/paypal
Content-Type: application/json

{webhook payload}
```

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Environment Variables

```bash
# Required for encryption
export VINC_PAYMENT_ENCRYPTION_KEY="your-secure-encryption-key"

# Generate a secure key:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3. Run Database Migrations

```bash
alembic upgrade head
```

This creates the payment tables:
- `tenant_payment_provider`
- `storefront_payment_method`
- `payment_transaction`
- `payment_webhook_log`

### 4. Configure Payment Providers

For Stripe:
```python
# Required credentials
{
    "secret_key": "sk_test_...",  # or sk_live_...
    "publishable_key": "pk_test_...",  # or pk_live_...
    "webhook_secret": "whsec_..."
}
```

For PayPal:
```python
# Required credentials
{
    "client_id": "your_client_id",
    "client_secret": "your_client_secret"
}
```

### 5. Configure Webhooks

#### Stripe Webhooks
1. Go to Stripe Dashboard → Developers → Webhooks
2. Add endpoint: `https://your-domain.com/api/v1/payments/webhooks/stripe`
3. Select events to listen to:
   - `payment_intent.succeeded`
   - `payment_intent.payment_failed`
   - `payment_intent.canceled`
   - `charge.refunded`
4. Copy the webhook secret to your provider configuration

#### PayPal Webhooks
1. Go to PayPal Developer Dashboard → Webhooks
2. Add webhook: `https://your-domain.com/api/v1/payments/webhooks/paypal`
3. Select events:
   - `CHECKOUT.ORDER.COMPLETED`
   - `PAYMENT.CAPTURE.COMPLETED`
   - `PAYMENT.CAPTURE.DENIED`
   - `PAYMENT.CAPTURE.REFUNDED`

## Security Features

### Credentials Encryption
All payment provider credentials are encrypted using Fernet (symmetric encryption) before storage:
- AES 128-bit encryption
- PBKDF2 key derivation (100,000 iterations)
- Unique encryption per installation

### Webhook Verification
- Stripe: Signature verification using webhook secret
- PayPal: Event verification via API call
- Duplicate event detection

### Access Control
- Role-based access (super_admin, supplier_admin, etc.)
- Tenant isolation
- Credentials never exposed in API responses

## Testing

### Run All Tests
```bash
pytest tests/modules/payments/
```

### Run Specific Test Suites
```bash
# Test encryption
pytest tests/modules/payments/test_encryption.py

# Test providers
pytest tests/modules/payments/test_providers.py

# Test API endpoints
pytest tests/modules/payments/test_api.py

# Test webhooks
pytest tests/modules/payments/test_webhooks.py
```

## Adding New Payment Providers

### 1. Create Provider Class

```python
# src/vinc_api/modules/payments/providers/nexi.py

from .base import BasePaymentProvider, PaymentIntentResult, RefundResult

class NexiProvider(BasePaymentProvider):
    @property
    def provider_name(self) -> str:
        return "nexi"

    async def create_payment_intent(self, ...):
        # Implementation
        pass

    # Implement other abstract methods...
```

### 2. Register Provider

```python
# src/vinc_api/modules/payments/service.py

def _get_provider_instance(self, tenant_provider):
    provider_map = {
        "stripe": StripeProvider,
        "paypal": PayPalProvider,
        "nexi": NexiProvider,  # Add new provider
    }
    # ...
```

### 3. Add to Models

Update `PROVIDER_VALUES` in `models.py`:
```python
PROVIDER_VALUES = (
    "stripe",
    "paypal",
    "nexi",  # Add here
    # ...
)
```

### 4. Create Migration

```bash
alembic revision -m "add nexi provider"
```

Update the CheckConstraint to include the new provider.

## Transaction Lifecycle

1. **Create Payment Intent**
   - Transaction record created with status `pending`
   - Provider creates payment intent
   - Client secret/redirect URL returned

2. **Customer Completes Payment**
   - Payment processed by provider
   - Webhook received with status update
   - Transaction updated to `succeeded` or `failed`

3. **Refund (if needed)**
   - Refund request submitted
   - Provider processes refund
   - Transaction updated with refund amount
   - Status changed to `refunded` or `partially_refunded`

## Monitoring & Analytics

### Transaction Logs
All transactions are logged with:
- Complete status history
- Webhook events received
- Processing times
- Error messages

### Analytics Endpoint
Provides aggregated metrics:
- Total transactions and amounts
- Success/failure rates
- Provider breakdown
- Refund statistics

### Debugging Webhooks
All webhooks logged to `payment_webhook_log` table:
- Complete payload
- Signature verification status
- Processing time
- Related transaction

## Best Practices

### For Wholesalers
1. Start with test mode providers
2. Test thoroughly before switching to live mode
3. Monitor webhook logs regularly
4. Set up proper fee configurations
5. Keep webhook secrets secure

### For Retailers
1. Configure appropriate cart amount conditions
2. Use clear, customer-friendly display names
3. Order payment methods by preference
4. Test the complete payment flow
5. Handle failed payments gracefully

### For Developers
1. Always encrypt credentials
2. Validate webhook signatures
3. Handle idempotency (duplicate webhooks)
4. Log all payment operations
5. Use transactions for database operations
6. Test with provider test credentials first

## Troubleshooting

### Payment Intent Creation Fails
- Check provider credentials are correctly configured
- Verify provider is enabled at both tenant and storefront levels
- Check amount meets minimum/maximum requirements
- Review error message in transaction record

### Webhook Not Received
- Verify webhook URL is publicly accessible
- Check webhook is configured in provider dashboard
- Review webhook logs for errors
- Ensure webhook secret is correct

### Refund Fails
- Verify transaction status is `succeeded`
- Check refund amount doesn't exceed available amount
- Confirm provider supports refunds
- Review provider-specific refund rules

## Future Enhancements

Potential features for future development:
- Buy Now Pay Later providers (Scalapay, Klarna)
- Italian payment methods (Nexi, Banca Sella)
- Subscription/recurring payments
- Payment method tokenization
- Fraud detection integration
- Multi-currency support enhancements
- Payment installments
- Digital wallets (beyond Stripe/PayPal)

## Support

For issues or questions:
1. Check transaction logs and webhook logs
2. Review provider dashboard for status
3. Consult provider documentation
4. Contact development team with transaction ID
