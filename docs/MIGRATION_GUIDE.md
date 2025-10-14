# BMS Integration Migration Guide

## Quick Start

### Step 1: Run Database Migrations

```bash
cd /home/jire87/software/www-website/www-data/vendereincloud-app/vinc-api
source venv/bin/activate
alembic upgrade head
```

This will add:
- **17 new columns** to `customer` table (HIGH + MEDIUM priority)
- **37 new columns** to `customer_address` table (HIGH + MEDIUM priority)
- **8 new indexes** for performance

### Step 2: Verify Schema

```bash
# Check customer table
alembic current
psql $VINC_DATABASE_URL -c "\d customer"

# Check address table
psql $VINC_DATABASE_URL -c "\d customer_address"
```

### Step 3: Test API

The Pydantic schemas are already updated. Test with:

```bash
# Example: Create customer with BMS fields
curl -X POST http://localhost:8000/api/v1/customers \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: your-supplier-id" \
  -d '{
    "supplier_id": "uuid",
    "erp_customer_id": "90001",
    "customer_code": "90001",
    "public_customer_code": "4100",
    "business_name": "Aurora Paint Lab SRL",
    "fiscal_code": "RSLENE85C65H501X",
    "vat_number": "12345678901",
    "registration_date": "2022-04-05T00:00:00Z",
    "credit_limit": 5000.00
  }'
```

## What Changed

### Database Schema

#### Customer Table - New Columns
```sql
-- HIGH Priority
customer_code VARCHAR            -- Internal code (BMS: canag_sclie)
public_customer_code VARCHAR     -- Public code (BMS: ncocg)
business_name VARCHAR             -- Business name (BMS: traso)
first_name VARCHAR                -- First name (BMS: rnome)
last_name VARCHAR                 -- Last name (BMS: rcogn)
fiscal_code VARCHAR(16)           -- IT tax code (BMS: cfisc)
vat_number VARCHAR(11)            -- IT VAT (BMS: cpiva)
registration_date TIMESTAMPTZ     -- Registration (BMS: ianag_sclie)
credit_limit NUMERIC(12,2)        -- Credit limit (BMS: asogl_xivas)

-- MEDIUM Priority
customer_category VARCHAR         -- Category (BMS: ccate_sclie)
activity_category VARCHAR         -- Activity (BMS: ccate_satti)
gender VARCHAR(1)                 -- M/F/O (BMS: csess)
business_start_date TIMESTAMPTZ   -- Business start (BMS: dinse_ianag)
financial_status VARCHAR          -- Financial status (BMS: cstat_dfiac)
cash_payment BOOLEAN              -- Cash payment (BMS: bcafl S/N)
auto_packaging BOOLEAN            -- Auto package (BMS: bragg_ximba S/N)
customer_group VARCHAR            -- Group (BMS: tclie_ngrup)
```

#### Customer Address Table - New Columns
```sql
-- HIGH Priority (10 fields)
address_code VARCHAR              -- Internal (BMS: cindi_dclie)
public_address_code VARCHAR       -- Public (BMS: ncocg_dcntr)
province VARCHAR(2)               -- Province (BMS: cprov)
municipality VARCHAR              -- Municipality (BMS: rcomu)
phone VARCHAR                     -- Phone (BMS: cntel)
email VARCHAR                     -- Email (BMS: tinte_semai)
pricelist_type VARCHAR            -- Pricelist type (BMS: ctipo_dlist)
payment_terms_code VARCHAR        -- Payment terms (BMS: cmpag)
is_billing_address BOOLEAN        -- Billing (BMS: busat_xfatt S/N)
is_shipping_address BOOLEAN       -- Shipping (BMS: busat_xinme S/N)

-- MEDIUM Priority (27 fields)
-- See full list in bms-integration-fields.md
```

#### New Indexes
```sql
-- Customer indexes
CREATE INDEX idx_customer_customer_code ON customer(customer_code);
CREATE INDEX idx_customer_public_code ON customer(public_customer_code);
CREATE INDEX idx_customer_fiscal_code ON customer(fiscal_code);
CREATE INDEX idx_customer_vat_number ON customer(vat_number);

-- Address indexes
CREATE INDEX idx_address_address_code ON customer_address(address_code);
CREATE INDEX idx_address_public_code ON customer_address(public_address_code);
CREATE INDEX idx_address_email ON customer_address(email);
CREATE INDEX idx_address_phone ON customer_address(phone);
```

### API Schemas

All Pydantic schemas updated in `src/vinc_api/modules/customers/schemas.py`:

- ✅ `CustomerCreate` - accepts all new BMS fields
- ✅ `CustomerUpdate` - accepts all new BMS fields
- ✅ `CustomerResponse` - returns all new BMS fields
- ✅ `CustomerAddressCreate` - accepts all new BMS fields
- ✅ `CustomerAddressUpdate` - accepts all new BMS fields
- ✅ `CustomerAddressResponse` - returns all new BMS fields

### Key Design Decisions

1. **English Field Names** ✅
   - Use `is_billing_address`, NOT `busat_xfatt`
   - Use `customer_code`, NOT `canag_sclie`
   - BMS names only in comments

2. **All Fields Nullable** ✅
   - Supports gradual migration
   - Existing data unaffected

3. **Boolean Conversion** ✅
   - BMS "S" → `true`
   - BMS "N" → `false`

4. **Dual Code System** ✅
   - Internal: `customer_code`, `address_code`
   - Public: `public_customer_code`, `public_address_code`

## Rollback

If needed, rollback migrations:

```bash
# Rollback address fields
alembic downgrade -1

# Rollback customer fields
alembic downgrade -1

# Or rollback to specific revision
alembic downgrade 202410150004
```

## Next Development Steps

### 1. Add Validation (Recommended)

Create `src/vinc_api/common/validators/italian.py`:

```python
import re

def validate_fiscal_code(code: str) -> bool:
    """Validate Italian fiscal code (codice fiscale)"""
    if not code:
        return True  # Allow null
    pattern = r'^[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z]$'
    return bool(re.match(pattern, code.upper()))

def validate_vat_number(vat: str) -> bool:
    """Validate Italian VAT (partita IVA)"""
    if not vat:
        return True  # Allow null
    if not re.match(r'^[0-9]{11}$', vat):
        return False
    # Add checksum validation
    return validate_vat_checksum(vat)

def validate_vat_checksum(vat: str) -> bool:
    """Validate VAT checksum"""
    total = 0
    for i in range(10):
        digit = int(vat[i])
        if i % 2 == 0:
            total += digit
        else:
            total += (digit * 2) % 10 + (digit * 2) // 10
    check = (10 - (total % 10)) % 10
    return check == int(vat[10])
```

### 2. Add BMS Import Endpoint (Recommended)

Create `src/vinc_api/modules/customers/bms_router.py`:

```python
from fastapi import APIRouter, Depends
from typing import List, Dict
from .schemas import CustomerCreate, CustomerAddressCreate
from .bms_transformer import transform_bms_customer, transform_bms_address

router = APIRouter(prefix="/customers/bms", tags=["BMS Import"])

@router.post("/import")
async def import_bms_customers(
    bms_data: Dict,
    supplier_id: str = Depends(get_active_supplier)
):
    """Import customers from BMS format"""
    customers = []
    for bms_customer in bms_data.get("myclient", []):
        customer = transform_bms_customer(bms_customer, supplier_id)
        # Save to database
        customers.append(customer)
    return {"imported": len(customers)}

@router.post("/{customer_id}/addresses/import")
async def import_bms_addresses(
    customer_id: str,
    bms_data: Dict
):
    """Import addresses from BMS format"""
    addresses = []
    for bms_address in bms_data.get("myindcli", []):
        address = transform_bms_address(bms_address)
        # Save to database
        addresses.append(address)
    return {"imported": len(addresses)}
```

### 3. Add Transformer Service (Required for Import)

Create `src/vinc_api/modules/customers/bms_transformer.py`:

```python
from datetime import datetime
from typing import Dict, Optional
from .schemas import CustomerCreate, CustomerAddressCreate

def bms_bool(value: Optional[str]) -> Optional[bool]:
    """Convert BMS S/N to boolean"""
    if not value:
        return None
    return value.strip().upper() == "S"

def bms_date(value: Optional[str]) -> Optional[datetime]:
    """Convert BMS date to datetime"""
    if not value:
        return None
    return datetime.fromisoformat(value.replace(" ", "T"))

def transform_bms_customer(bms_data: Dict, supplier_id: str) -> CustomerCreate:
    """Transform BMS customer to VINC format"""
    return CustomerCreate(
        supplier_id=supplier_id,
        erp_customer_id=bms_data["canag_sclie"],
        name=bms_data.get("traso") or f"{bms_data.get('rnome', '')} {bms_data.get('rcogn', '')}".strip(),

        # HIGH priority
        customer_code=bms_data.get("canag_sclie"),
        public_customer_code=bms_data.get("ncocg"),
        business_name=bms_data.get("traso"),
        first_name=bms_data.get("rnome"),
        last_name=bms_data.get("rcogn"),
        fiscal_code=bms_data.get("cfisc"),
        vat_number=bms_data.get("cpiva"),
        registration_date=bms_date(bms_data.get("ianag_sclie")),
        credit_limit=bms_data.get("asogl_xivas"),

        # MEDIUM priority
        customer_category=bms_data.get("ccate_sclie"),
        activity_category=bms_data.get("ccate_satti"),
        gender=bms_data.get("csess"),
        business_start_date=bms_date(bms_data.get("dinse_ianag")),
        financial_status=bms_data.get("cstat_dfiac"),
        cash_payment=bms_bool(bms_data.get("bcafl")),
        auto_packaging=bms_bool(bms_data.get("bragg_ximba")),
        customer_group=bms_data.get("tclie_ngrup"),
    )

def transform_bms_address(bms_data: Dict) -> CustomerAddressCreate:
    """Transform BMS address to VINC format"""
    return CustomerAddressCreate(
        erp_address_id=bms_data["cindi_dclie"],
        label=bms_data.get("tindi"),
        street=bms_data.get("rindi"),
        city=bms_data.get("rcitt"),
        zip=bms_data.get("ccapp"),
        country=bms_data.get("cnazi"),

        # HIGH priority
        address_code=bms_data.get("cindi_dclie"),
        public_address_code=bms_data.get("ncocg_dcntr"),
        province=bms_data.get("cprov"),
        municipality=bms_data.get("rcomu"),
        phone=bms_data.get("cntel"),
        email=bms_data.get("tinte_semai"),
        pricelist_code=bms_data.get("clist"),
        pricelist_type=bms_data.get("ctipo_dlist"),
        payment_terms_code=bms_data.get("cmpag"),
        is_billing_address=bms_bool(bms_data.get("busat_xfatt")),
        is_shipping_address=bms_bool(bms_data.get("busat_xinme")),

        # MEDIUM priority
        # ... add remaining fields
    )
```

## Troubleshooting

### Migration Fails

```bash
# Check current revision
alembic current

# Check migration history
alembic history

# Manually inspect database
psql $VINC_DATABASE_URL -c "SELECT * FROM alembic_version;"
```

### Schema Mismatch

If Pydantic schema doesn't match database:

1. Check migration was applied: `alembic current`
2. Restart API server
3. Check column exists: `\d customer` in psql

### Import Errors

Common issues:
- BMS boolean "S"/"N" not converted
- Dates in wrong format
- Missing required fields
- Duplicate customer/address codes

## Documentation

- **Field Mapping**: `docs/bms-integration-fields.md`
- **Implementation**: `docs/bms-backend-implementation.md`
- **Frontend Docs**: `vinc-office/docs/integrations/bms/`

## Support

For issues or questions:
1. Check migration logs
2. Verify schema with `\d table_name`
3. Test API endpoints manually
4. Review BMS data format
