# BMS Integration - Backend Implementation Summary

This document summarizes the backend implementation of BMS ERP integration fields for VINC API.

## ✅ Completed

### 1. Database Migrations

**Migration 1: Customer BMS Fields**
- **File**: `migrations/versions/202510100001_add_customer_bms_fields.py`
- **Adds**: 17 new columns to `customer` table
- **Indexes**: 4 new indexes (customer_code, public_customer_code, fiscal_code, vat_number)
- **Constraints**: Gender check constraint (M/F/O)

**Migration 2: Address BMS Fields**
- **File**: `migrations/versions/202510100002_add_address_bms_fields.py`
- **Adds**: 37 new columns to `customer_address` table
- **Indexes**: 4 new indexes (address_code, public_address_code, email, phone)

### 2. Pydantic Schemas

**Updated**: `src/vinc_api/modules/customers/schemas.py`

All schemas updated with HIGH and MEDIUM priority BMS fields:
- `CustomerCreate` - with all BMS fields
- `CustomerUpdate` - with all BMS fields
- `CustomerResponse` - with all BMS fields
- `CustomerAddressCreate` - with all BMS fields
- `CustomerAddressUpdate` - with all BMS fields
- `CustomerAddressResponse` - with all BMS fields

### 3. Field Naming Convention

**✅ Using English naming** (not BMS originals):
- ✅ `is_billing_address` (not `busat_xfatt`)
- ✅ `is_shipping_address` (not `busat_xinme`)
- ✅ `is_payment_address` (not `busat_xpaga`)
- ✅ `is_delivery_address` (not `busat_xsdlg`)
- ✅ `customer_code` (internal, from `canag_sclie`)
- ✅ `public_customer_code` (customer-facing, from `ncocg`)
- ✅ `address_code` (internal, from `cindi_dclie`)
- ✅ `public_address_code` (customer-facing, from `ncocg_dcntr`)

## Customer Fields Summary

### HIGH Priority (9 fields)
| Field | Type | Description |
|-------|------|-------------|
| `customer_code` | VARCHAR | Internal machine code |
| `public_customer_code` | VARCHAR | Public code on invoices |
| `business_name` | VARCHAR | Business/trade name |
| `first_name` | VARCHAR | First name |
| `last_name` | VARCHAR | Last name |
| `fiscal_code` | VARCHAR(16) | Italian tax code |
| `vat_number` | VARCHAR(11) | Italian VAT |
| `registration_date` | TIMESTAMP | Registration date |
| `credit_limit` | NUMERIC(12,2) | Credit limit |

### MEDIUM Priority (8 fields)
| Field | Type | Description |
|-------|------|-------------|
| `customer_category` | VARCHAR | Category/classification |
| `activity_category` | VARCHAR | Industry sector |
| `gender` | VARCHAR(1) | Gender (M/F/O) |
| `business_start_date` | TIMESTAMP | Business start date |
| `financial_status` | VARCHAR | Financial status |
| `cash_payment` | BOOLEAN | Cash payment preference |
| `auto_packaging` | BOOLEAN | Auto packaging |
| `customer_group` | VARCHAR | Customer group |

## Address Fields Summary

### HIGH Priority (10 fields)
| Field | Type | Description |
|-------|------|-------------|
| `address_code` | VARCHAR | Internal machine code |
| `public_address_code` | VARCHAR | Public code on documents |
| `province` | VARCHAR(2) | Province code |
| `municipality` | VARCHAR | Municipality |
| `phone` | VARCHAR | Phone number |
| `email` | VARCHAR | Email address |
| `pricelist_type` | VARCHAR | Pricelist type |
| `payment_terms_code` | VARCHAR | Payment terms |
| `is_billing_address` | BOOLEAN | Billing flag |
| `is_shipping_address` | BOOLEAN | Shipping flag |

### MEDIUM Priority (27 fields)
| Field | Type | Description |
|-------|------|-------------|
| `street_name` | VARCHAR | Street name |
| `street_number` | VARCHAR | Street number |
| `internal_number` | VARCHAR | Apt/internal |
| `region` | VARCHAR | Region code |
| `zone_code` | VARCHAR | Geographic zone |
| `mobile_phone` | VARCHAR | Mobile phone |
| `fax` | VARCHAR | Fax number |
| `website` | VARCHAR | Website URL |
| `latitude` | NUMERIC(10,8) | GPS latitude |
| `longitude` | NUMERIC(11,8) | GPS longitude |
| `promo_pricelist_code` | VARCHAR | Promo pricelist |
| `shipping_terms` | VARCHAR | Shipping terms |
| `transport_type` | VARCHAR | Transport type |
| `language_code` | VARCHAR(10) | Language |
| `currency_code` | VARCHAR(10) | Currency |
| `carrier_code` | VARCHAR | Carrier code |
| `is_payment_address` | BOOLEAN | Payment flag |
| `is_delivery_address` | BOOLEAN | Delivery flag |
| `registration_date` | TIMESTAMP | Registration date |
| `iban` | VARCHAR(34) | IBAN |
| `bic_swift` | VARCHAR(11) | BIC/SWIFT |
| `discount_1` | NUMERIC(5,3) | Discount 1 |
| `discount_2` | NUMERIC(5,3) | Discount 2 |
| `agent_code` | VARCHAR | Sales agent |
| `sales_point_code` | VARCHAR | Sales point |
| `vat_code` | VARCHAR | VAT code |
| `credit_limit` | NUMERIC(12,2) | Credit limit |

## Running Migrations

```bash
# Navigate to vinc-api
cd /home/jire87/software/www-website/www-data/vendereincloud-app/vinc-api

# Activate virtualenv
source venv/bin/activate

# Run migrations
alembic upgrade head

# Verify
psql $DATABASE_URL -c "\d customer"
psql $DATABASE_URL -c "\d customer_address"
```

## Next Steps

### 1. SQLAlchemy Models (Optional)
If you have SQLAlchemy model files, update them to include:
- New column definitions
- Type hints
- Relationships

### 2. Service Layer Updates
Update `src/vinc_api/modules/customers/service.py` if needed:
- Add BMS data transformation logic
- Add validation for Italian tax codes
- Add BMS import endpoints

### 3. Router/API Endpoints
Consider adding new endpoints in `src/vinc_api/modules/customers/router.py`:
```python
@router.post("/customers/import/bms")
async def import_bms_customers(...)

@router.post("/customers/{customer_id}/addresses/import/bms")
async def import_bms_addresses(...)

@router.get("/customers/by-public-code/{code}")
async def get_by_public_code(...)
```

### 4. Validation Utilities
Create validation functions:
```python
# src/vinc_api/common/validators.py
def validate_italian_fiscal_code(code: str) -> bool:
    pattern = r'^[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z]$'
    return bool(re.match(pattern, code.upper()))

def validate_italian_vat(vat: str) -> bool:
    pattern = r'^[0-9]{11}$'
    if not re.match(pattern, vat):
        return False
    # Add checksum validation
    return validate_vat_checksum(vat)
```

### 5. Data Import Service
Create BMS import service:
```python
# src/vinc_api/modules/customers/bms_import.py
from typing import Dict, List
from .schemas import CustomerCreate, CustomerAddressCreate

class BMSImportService:
    @staticmethod
    def transform_customer(bms_data: Dict) -> CustomerCreate:
        return CustomerCreate(
            supplier_id=supplier_id,
            erp_customer_id=bms_data["canag_sclie"],
            customer_code=bms_data["canag_sclie"],
            public_customer_code=bms_data.get("ncocg"),
            business_name=bms_data.get("traso"),
            fiscal_code=bms_data.get("cfisc"),
            vat_number=bms_data.get("cpiva"),
            # ... map all fields
        )

    @staticmethod
    def transform_address(bms_data: Dict) -> CustomerAddressCreate:
        return CustomerAddressCreate(
            erp_address_id=bms_data["cindi_dclie"],
            address_code=bms_data["cindi_dclie"],
            public_address_code=bms_data.get("ncocg_dcntr"),
            is_billing_address=bms_data.get("busat_xfatt") == "S",
            is_shipping_address=bms_data.get("busat_xinme") == "S",
            # ... map all fields
        )
```

## Testing

### Migration Testing
```bash
# Test upgrade
alembic upgrade head

# Test downgrade
alembic downgrade -1

# Test re-upgrade
alembic upgrade head
```

### API Testing
```bash
# Test customer creation with new fields
curl -X POST http://localhost:8000/api/v1/customers \
  -H "Content-Type: application/json" \
  -d '{
    "supplier_id": "uuid-here",
    "erp_customer_id": "90001",
    "customer_code": "90001",
    "public_customer_code": "4100",
    "business_name": "Aurora Paint Lab SRL",
    "fiscal_code": "RSLENE85C65H501X",
    "vat_number": "12345678901"
  }'
```

## Important Notes

1. **All fields are nullable** - supports gradual migration
2. **English naming** throughout - no BMS originals in schema
3. **Boolean conversion** - BMS "S"/"N" → true/false
4. **Indexes added** for performance on lookups
5. **Validation** should be added at application level
6. **BMS metadata** can still use existing JSONB columns if needed

## Documentation References

- Field Mapping: `docs/bms-integration-fields.md`
- Frontend Mapping: `vinc-office/docs/integrations/bms/customer-field-mapping.md`
- Frontend Mapping: `vinc-office/docs/integrations/bms/address-field-mapping.md`
