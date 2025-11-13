# Payment Provider Support Matrix

## Supported Payment Providers

### Overview

| Provider | Checkout | MOTO | Recurring | Card on File | BNPL |
|----------|----------|------|-----------|--------------|------|
| **Stripe** | ✅ | ✅ | ✅ | ✅ | ❌ |
| **PayPal** | ✅ | ❌ | ✅ | ✅ | ✅ (Pay in 3) |
| **Nexi** | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Banca Sella** | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Scalapay** | ✅ | ❌ | ❌ | ❌ | ✅ |
| **Bank Transfer** | ✅ | ✅ | ❌ | ❌ | ❌ |

### Implementation Status

| Provider | Implementation | Webhook | Tests | Production Ready |
|----------|---------------|---------|-------|------------------|
| **Stripe** | ✅ Complete | ✅ Complete | ✅ Complete | ✅ Yes |
| **PayPal** | ✅ Complete | ✅ Complete | ✅ Complete | ✅ Yes |
| **Nexi** | ✅ Complete | ✅ Complete | ⚠️ Basic | ⚠️ Needs testing |
| **Banca Sella** | ✅ Complete | ⚠️ Partial | ⚠️ Basic | ⚠️ Needs testing |
| **Scalapay** | ✅ Complete | ⚠️ Partial | ⚠️ Basic | ⚠️ Needs testing |
| **Bank Transfer** | ✅ Complete | N/A | ⚠️ Basic | ✅ Yes |

## Payment Types Explained

### Standard Checkout
- **Description**: Regular one-time payment initiated by customer
- **Use Case**: E-commerce checkout
- **User Experience**: Customer enters payment details and confirms
- **All providers** support this

### MOTO (Mail Order/Telephone Order)
- **Description**: Payments processed without customer present
- **Use Case**: Phone orders, admin-initiated payments
- **User Experience**: Merchant enters customer payment details
- **Security**: Requires PCI compliance
- **Supported by**: Stripe, Nexi, Banca Sella, Bank Transfer

### Recurring/Subscription
- **Description**: Automatic recurring charges for subscriptions
- **Use Case**: Monthly subscriptions, installments
- **User Experience**: Customer authorizes future charges
- **Implementation**: Requires customer consent and stored payment method
- **Supported by**: Stripe, PayPal, Nexi, Banca Sella

### Card on File / One-Click
- **Description**: Saved payment method for future use
- **Use Case**: Returning customers, express checkout
- **User Experience**: Customer pays with one click using saved card
- **Security**: Card details stored securely by provider (not by us)
- **Supported by**: Stripe, PayPal, Nexi, Banca Sella

### BNPL (Buy Now Pay Later)
- **Description**: Split payment into interest-free installments
- **Use Case**: Higher-value purchases
- **User Experience**: Customer chooses installment plan
- **Benefits**: Increases conversion for higher ticket items
- **Supported by**: Scalapay (3-4 installments), PayPal (Pay in 3)

## Provider Details

### Stripe
- **Region**: Global
- **Currencies**: 135+ currencies
- **Payment Methods**: Cards, wallets (Apple Pay, Google Pay), SEPA
- **Fees**: 2.9% + €0.30 per transaction (Europe)
- **Settlement**: 2-7 business days
- **Documentation**: https://stripe.com/docs

**Best For**: International businesses, developer-friendly API, comprehensive features

### PayPal
- **Region**: Global
- **Currencies**: 25+ currencies
- **Payment Methods**: PayPal wallet, cards, Pay in 3
- **Fees**: 3.4% + €0.35 per transaction (Europe)
- **Settlement**: Instant to PayPal balance
- **Documentation**: https://developer.paypal.com

**Best For**: Consumer trust, PayPal account holders, BNPL option

### Nexi
- **Region**: Italy
- **Currencies**: EUR
- **Payment Methods**: All major Italian and European cards
- **Fees**: Variable (negotiate with Nexi)
- **Settlement**: 1-2 business days
- **Documentation**: https://developer.nexi.it

**Best For**: Italian market, local cards, compliance with Italian regulations

### Banca Sella (GestPay)
- **Region**: Italy, Europe
- **Currencies**: EUR, USD, GBP, CHF
- **Payment Methods**: Cards, MyBank, bank transfers
- **Fees**: Variable (negotiate with Banca Sella)
- **Settlement**: 1-2 business days
- **Documentation**: https://docs.gestpay.it

**Best For**: Italian businesses, established banking relationship, MyBank support

### Scalapay
- **Region**: Italy, France, Belgium
- **Currencies**: EUR
- **Payment Methods**: BNPL (3 or 4 installments)
- **Fees**: % per transaction (paid by merchant)
- **Settlement**: After installments complete
- **Limits**: €1 - €2,000 per order
- **Documentation**: https://developers.scalapay.com

**Best For**: Fashion, electronics, higher-value items, increasing conversion

### Bank Transfer
- **Region**: Any
- **Currencies**: Any
- **Payment Methods**: Manual bank transfer (SEPA, wire)
- **Fees**: Bank transfer fees only
- **Settlement**: Manual (1-3 business days)
- **Documentation**: N/A (internal tracking)

**Best For**: B2B transactions, large amounts, customers preferring traditional banking

## Configuration Guide

### Required Credentials

#### Stripe
```json
{
  "secret_key": "sk_live_...",
  "publishable_key": "pk_live_...",
  "webhook_secret": "whsec_..."
}
```

#### PayPal
```json
{
  "client_id": "your_client_id",
  "client_secret": "your_client_secret"
}
```

#### Nexi
```json
{
  "api_key": "your_api_key",
  "webhook_secret": "your_webhook_secret"
}
```

#### Banca Sella
```json
{
  "shop_login": "your_shop_login",
  "api_key": "your_api_key"
}
```

#### Scalapay
```json
{
  "api_key": "your_api_key"
}
```

#### Bank Transfer
```json
{
  "bank_name": "Banca Example",
  "account_holder": "Your Company S.r.l.",
  "iban": "IT60X0542811101000000123456",
  "bic": "BPMOIT22"
}
```

## Payment Type Implementation

### Creating Standard Payment
```python
{
  "provider": "stripe",
  "payment_type": "standard",
  "amount": 100.00,
  "currency": "EUR",
  ...
}
```

### Creating MOTO Payment
```python
{
  "provider": "nexi",
  "payment_type": "moto",
  "amount": 50.00,
  "currency": "EUR",
  "metadata": {
    "operator_id": "admin_user_id",
    "customer_phone": "+39 02 1234567"
  }
}
```

### Creating One-Click Payment
```python
{
  "provider": "stripe",
  "payment_type": "one_click",
  "saved_card_id": "card_abc123",
  "amount": 25.00,
  "currency": "EUR"
}
```

### Creating Recurring Payment
```python
{
  "provider": "stripe",
  "payment_type": "recurrent",
  "amount": 9.99,
  "currency": "EUR",
  "metadata": {
    "subscription_id": "sub_123",
    "billing_period": "monthly"
  }
}
```

## Best Practices

### Provider Selection
- **International**: Use Stripe or PayPal
- **Italy-focused**: Add Nexi and/or Banca Sella
- **Fashion/Electronics**: Add Scalapay for BNPL
- **B2B**: Always offer Bank Transfer

### Fee Optimization
- Compare provider fees for your transaction size
- Consider who bears fees (merchant vs customer)
- Negotiate rates for high volume

### Conversion Optimization
- Offer multiple payment options
- Show familiar logos to build trust
- Add BNPL for higher-value items
- Enable one-click for returning customers

### Security
- Always use test mode for development
- Rotate API keys regularly
- Monitor webhook logs for anomalies
- Implement rate limiting
- Never log sensitive card data

### Compliance
- PCI DSS compliance for card payments
- GDPR compliance for customer data
- Italian regulations for local providers
- 3D Secure (SCA) for EU cards

## Roadmap

### Planned Features
- [ ] Apple Pay direct integration
- [ ] Google Pay direct integration
- [ ] Klarna BNPL integration
- [ ] Satispay integration (Italy)
- [ ] Multibanco integration (Portugal)
- [ ] iDEAL integration (Netherlands)
- [ ] Subscription management UI
- [ ] Payment analytics dashboard
- [ ] Fraud detection
- [ ] Split payments

### Provider Enhancements
- [ ] Complete Banca Sella webhook implementation
- [ ] Complete Scalapay webhook implementation
- [ ] Nexi production testing and certification
- [ ] PayPal recurring payment setup
- [ ] Stripe subscription management

## Support

### Provider Documentation
- [Stripe Docs](https://stripe.com/docs)
- [PayPal Developer](https://developer.paypal.com)
- [Nexi Developer](https://developer.nexi.it)
- [Banca Sella GestPay](https://docs.gestpay.it)
- [Scalapay Developers](https://developers.scalapay.com)

### Getting Help
- Check provider dashboard for payment status
- Review webhook logs for event history
- Consult transaction logs in database
- Contact provider support for API issues
- Refer to main [Payment System Guide](payment-system.md)

---

**Last Updated**: November 2025
**Status**: In Production (Stripe, PayPal, Bank Transfer), Testing (Others)
