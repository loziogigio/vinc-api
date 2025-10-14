# BMS Integration - Database Fields Implementation

This document lists the HIGH and MEDIUM priority fields from BMS that will be implemented in the vinc-api PostgreSQL database.

**IMPORTANT**: All field names use **English naming conventions** (e.g., `is_billing_address`), NOT the original BMS field names.

## Customer Table - New Fields

### HIGH Priority

| Field Name | Type | Description | BMS Source | Nullable |
|------------|------|-------------|------------|----------|
| `customer_code` | VARCHAR | Internal customer code (machine ID) | canag_sclie | YES |
| `public_customer_code` | VARCHAR | Public code shown on invoices | ncocg | YES |
| `business_name` | VARCHAR | Full business/trade name | traso | YES |
| `first_name` | VARCHAR | First name (individuals) | rnome | YES |
| `last_name` | VARCHAR | Last name (individuals) | rcogn | YES |
| `fiscal_code` | VARCHAR(16) | Italian tax code (codice fiscale) | cfisc | YES |
| `vat_number` | VARCHAR(11) | Italian VAT number (P.IVA) | cpiva | YES |
| `registration_date` | TIMESTAMP | Initial registration date | ianag_sclie | YES |
| `credit_limit` | NUMERIC(12,2) | Credit limit amount | asogl_xivas | YES |

### MEDIUM Priority

| Field Name | Type | Description | BMS Source | Nullable |
|------------|------|-------------|------------|----------|
| `customer_category` | VARCHAR | Customer category/classification | ccate_sclie | YES |
| `activity_category` | VARCHAR | Activity/industry sector | ccate_satti | YES |
| `gender` | VARCHAR(1) | Gender (M/F/O) | csess | YES |
| `business_start_date` | TIMESTAMP | Business activity start date | dinse_ianag | YES |
| `financial_status` | VARCHAR | Financial status code | cstat_dfiac | YES |
| `cash_payment` | BOOLEAN | Cash payment preference | bcafl | YES |
| `auto_packaging` | BOOLEAN | Auto packaging flag | bragg_ximba | YES |
| `customer_group` | VARCHAR | Customer group name | tclie_ngrup | YES |

**Constraints**:
- `fiscal_code` should have CHECK constraint for 16 characters when present
- `vat_number` should have CHECK constraint for 11 digits when present
- `gender` should have CHECK constraint: `gender IN ('M', 'F', 'O')`
- Index on `customer_code` for lookups
- Index on `public_customer_code` for invoices

## Customer Address Table - New Fields

### HIGH Priority

| Field Name | Type | Description | BMS Source | Nullable |
|------------|------|-------------|------------|----------|
| `address_code` | VARCHAR | Internal address code (machine ID) | cindi_dclie | YES |
| `public_address_code` | VARCHAR | Public code shown on documents | ncocg_dcntr | YES |
| `province` | VARCHAR(2) | Province code (2 chars) | cprov | YES |
| `municipality` | VARCHAR | Municipality/comune | rcomu | YES |
| `phone` | VARCHAR | Main phone number | cntel | YES |
| `email` | VARCHAR | Email address | tinte_semai | YES |
| `pricelist_type` | VARCHAR | Price list type | ctipo_dlist | YES |
| `payment_terms_code` | VARCHAR | Payment terms code | cmpag | YES |
| `is_billing_address` | BOOLEAN | Billing address flag | busat_xfatt | YES |
| `is_shipping_address` | BOOLEAN | Shipping address flag | busat_xinme | YES |

### MEDIUM Priority

| Field Name | Type | Description | BMS Source | Nullable |
|------------|------|-------------|------------|----------|
| `street_name` | VARCHAR | Street name (separated) | rviaa_dstra | YES |
| `street_number` | VARCHAR | Street number | cnciv_dstra | YES |
| `internal_number` | VARCHAR | Internal/apartment number | cnint_dstra | YES |
| `region` | VARCHAR | Region code | cregi | YES |
| `zone_code` | VARCHAR | Geographic zone | czona | YES |
| `mobile_phone` | VARCHAR | Mobile/additional phone | cntel_sagg1 | YES |
| `fax` | VARCHAR | Fax number | cntel_sfaxx | YES |
| `website` | VARCHAR | Website URL | tinte_ssito | YES |
| `latitude` | NUMERIC(10,8) | GPS latitude | qcoox | YES |
| `longitude` | NUMERIC(11,8) | GPS longitude | qcooy | YES |
| `promo_pricelist_code` | VARCHAR | Promotional pricelist | clist_sprom | YES |
| `shipping_terms` | VARCHAR | Shipping/port terms | cport | YES |
| `transport_type` | VARCHAR | Transport type | ctras | YES |
| `language_code` | VARCHAR(10) | Language code | cling | YES |
| `currency_code` | VARCHAR(10) | Currency code | cvalu | YES |
| `carrier_code` | VARCHAR | Carrier/shipper code | canag_svett | YES |
| `is_payment_address` | BOOLEAN | Payment address flag | busat_xpaga | YES |
| `is_delivery_address` | BOOLEAN | Delivery address flag | busat_xsdlg | YES |
| `registration_date` | TIMESTAMP | Address registration date | iindi_dclie | YES |
| `iban` | VARCHAR(34) | IBAN code | cabix | YES |
| `bic_swift` | VARCHAR(11) | BIC/SWIFT code | ccabx | YES |
| `discount_1` | NUMERIC(5,3) | Discount percentage 1 | pscon_orica_1 | YES |
| `discount_2` | NUMERIC(5,3) | Discount percentage 2 | pscon_orica_2 | YES |
| `agent_code` | VARCHAR | Sales agent code | canag_sagen | YES |
| `sales_point_code` | VARCHAR | Sales point code | cpven | YES |
| `vat_code` | VARCHAR | VAT exemption code | caiva | YES |
| `credit_limit` | NUMERIC(12,2) | Credit limit for this address | afido_dclie | YES |

**Constraints**:
- `province` should have CHECK constraint for 2 characters when present
- `language_code` and `currency_code` have reasonable length limits
- `iban` max length 34 (international standard)
- `bic_swift` max length 11 (8 or 11 chars)
- Index on `address_code` for lookups
- Index on `public_address_code` for documents
- Index on `email` for customer communication lookups

## Migration Strategy

1. **Migration 1**: Add customer HIGH priority fields
2. **Migration 2**: Add customer MEDIUM priority fields
3. **Migration 3**: Add address HIGH priority fields
4. **Migration 4**: Add address MEDIUM priority fields

Or combine as:
- **Migration 1**: All customer fields (HIGH + MEDIUM)
- **Migration 2**: All address fields (HIGH + MEDIUM)

## Data Types Rationale

- **VARCHAR**: Variable length strings (most BMS text fields)
- **VARCHAR(n)**: Fixed/max length codes (fiscal_code, VAT, province, etc.)
- **BOOLEAN**: True/false flags (replaces BMS S/N strings)
- **NUMERIC(p,s)**: Decimal numbers for money/percentages
- **TIMESTAMP**: Dates with timezone support

## Indexes Recommendation

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

## Validation Rules (Application Level)

### Italian Tax Codes
- **Fiscal Code**: 16 alphanumeric chars, pattern `^[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z]$`
- **VAT Number**: 11 digits, pattern `^[0-9]{11}$`, with checksum validation

### Address Validation
- **Province**: 2 uppercase letters (IT province codes)
- **ZIP Code (Italy)**: 5 digits `^[0-9]{5}$`
- **IBAN (Italy)**: Starts with "IT", 27 chars total
- **BIC/SWIFT**: 8 or 11 chars

## Notes

- All new fields are **nullable** to support gradual migration
- BMS-specific metadata (low priority fields) stored in JSONB `metadata` column (existing)
- English field names used throughout for consistency
- Boolean fields replace BMS "S"/"N" string flags
- Timestamps use PostgreSQL TIMESTAMP WITH TIME ZONE
