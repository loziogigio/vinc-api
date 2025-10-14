# BMS Integration - Quick Start Guide

## 🚀 Apply Migrations (3 commands)

```bash
cd /home/jire87/software/www-website/www-data/vendereincloud-app/vinc-api
source venv/bin/activate
alembic upgrade head
```

## ✅ Verify Installation

```bash
# Check current revision (should be 202510100002)
alembic current

# Check database schema
psql $VINC_DATABASE_URL -c "\d customer" | grep -E "(customer_code|public_customer_code|fiscal_code)"
psql $VINC_DATABASE_URL -c "\d customer_address" | grep -E "(address_code|is_billing_address|is_shipping_address)"
```

## 📋 What Was Added

### Customer Table (17 fields)
```
✓ customer_code              (Internal ID)
✓ public_customer_code       (Invoice code)
✓ business_name              (Company name)
✓ first_name, last_name      (Individual names)
✓ fiscal_code                (IT tax code - 16 chars)
✓ vat_number                 (IT VAT - 11 digits)
✓ registration_date          (Registration timestamp)
✓ credit_limit               (Credit amount)
✓ customer_category          (Category)
✓ activity_category          (Industry)
✓ gender                     (M/F/O)
✓ business_start_date        (Start timestamp)
✓ financial_status           (Status code)
✓ cash_payment               (Boolean)
✓ auto_packaging             (Boolean)
✓ customer_group             (Group name)
```

### Address Table (37 fields)
```
✓ address_code               (Internal ID)
✓ public_address_code        (Document code)
✓ is_billing_address         (Boolean) ← English naming!
✓ is_shipping_address        (Boolean) ← English naming!
✓ is_payment_address         (Boolean) ← English naming!
✓ is_delivery_address        (Boolean) ← English naming!
✓ province, municipality     (Location)
✓ phone, mobile_phone, fax   (Contact)
✓ email, website             (Digital)
✓ latitude, longitude        (GPS)
✓ pricelist_type, payment_terms_code
✓ + 24 more fields...
```

## 🎯 Key Features

### ✅ English Naming (Not BMS!)
- `is_billing_address` NOT `busat_xfatt`
- `is_shipping_address` NOT `busat_xinme`
- `customer_code` NOT `canag_sclie`
- `address_code` NOT `cindi_dclie`

### ✅ Boolean Conversion
- BMS "S" → `true`
- BMS "N" → `false`

### ✅ Dual Code System
- **Internal**: `customer_code`, `address_code` (machine ID)
- **Public**: `public_customer_code`, `public_address_code` (invoices/docs)

## 📝 Example Usage

### Create Customer with BMS Fields
```python
from vinc_api.modules.customers.schemas import CustomerCreate
from uuid import UUID
from datetime import datetime
from decimal import Decimal

customer = CustomerCreate(
    supplier_id=UUID("..."),
    erp_customer_id="90001",
    name="AURORA PAINT LAB SRL",

    # BMS fields (English names)
    customer_code="90001",
    public_customer_code="4100",
    business_name="AURORA PAINT LAB SRL",
    first_name="ELENA",
    last_name="ROSI",
    fiscal_code="RSLENE85C65H501X",
    vat_number="12345678901",
    registration_date=datetime(2022, 4, 5),
    credit_limit=Decimal("5000.00"),
    gender="F",
    cash_payment=True
)
```

### Create Address with BMS Fields
```python
from vinc_api.modules.customers.schemas import CustomerAddressCreate

address = CustomerAddressCreate(
    erp_address_id="81000",
    label="AURORA PAINT LAB DEPOT",
    street="VIA LUMINOSA 17",
    city="MILANO",
    zip="20121",
    country="IT",

    # BMS fields (English names)
    address_code="81000",
    public_address_code="15",
    province="MI",
    municipality="MILANO",
    phone="+39 02 12345678",
    mobile_phone="+39 339 1234567",
    email="depot@aurorapaint.example",
    pricelist_code="12",
    pricelist_type="VEND",
    payment_terms_code="B180",
    is_billing_address=False,    # ← English!
    is_shipping_address=True,     # ← English!
    is_payment_address=False      # ← English!
)
```

## 🔧 Testing

### Test Customer Creation
```bash
curl -X POST http://localhost:8000/api/v1/customers \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: <supplier-uuid>" \
  -d '{
    "supplier_id": "uuid",
    "erp_customer_id": "90001",
    "customer_code": "90001",
    "public_customer_code": "4100",
    "business_name": "Aurora Paint Lab SRL",
    "fiscal_code": "RSLENE85C65H501X",
    "vat_number": "12345678901",
    "credit_limit": 5000.00
  }'
```

### Test Address Creation
```bash
curl -X POST http://localhost:8000/api/v1/customers/{customer_id}/addresses \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: <supplier-uuid>" \
  -d '{
    "erp_address_id": "81000",
    "address_code": "81000",
    "public_address_code": "15",
    "label": "Main Office",
    "street": "VIA LUMINOSA 17",
    "city": "MILANO",
    "zip": "20121",
    "province": "MI",
    "phone": "+39 02 12345678",
    "email": "contact@example.it",
    "is_billing_address": true,
    "is_shipping_address": true
  }'
```

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [bms-integration-fields.md](bms-integration-fields.md) | Complete field reference |
| [bms-backend-implementation.md](bms-backend-implementation.md) | Implementation details |
| [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) | Step-by-step migration guide |
| [TEST_RESULTS.md](TEST_RESULTS.md) | Test validation results |

## ⚠️ Important Notes

1. **All fields are nullable** - supports gradual migration
2. **English names only** - no BMS originals in code
3. **Boolean flags** - multiple address types possible per address
4. **Indexes added** - optimized for lookups
5. **Backward compatible** - existing data unaffected

## 🆘 Troubleshooting

### Migration fails
```bash
# Check current state
alembic current

# Check migration history
alembic history

# Manually check database
psql $VINC_DATABASE_URL -c "SELECT * FROM alembic_version;"
```

### Schema not updating
1. Verify migration applied: `alembic current`
2. Check database: `\d customer` in psql
3. Restart API server

### Validation errors
- Check field names are English (not BMS)
- Verify boolean fields use true/false (not "S"/"N")
- Check fiscal_code is 16 chars, vat_number is 11 digits

## 🎉 Success Criteria

After running migrations, you should have:
- ✅ 17 new customer fields
- ✅ 37 new address fields
- ✅ 8 new indexes
- ✅ All schemas accepting BMS data
- ✅ English naming throughout
- ✅ Boolean address type flags working

---

**Ready to go!** 🚀 Run the 3 commands at the top to complete the setup.
