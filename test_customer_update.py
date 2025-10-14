#!/usr/bin/env python
"""
Test script to verify customer update endpoint with all BMS fields
"""
import requests
import json
import os
from datetime import datetime

# Configuration
API_BASE_URL = os.getenv("VINC_API_URL", "http://localhost:8000")
API_PREFIX = "/api/v1"

# Test data - Using the reseller ID from the conversation
RESELLER_ID = "b4a8bcad-9bcc-4152-8597-b84737377ea7"

# You'll need to provide a valid access token
# Get it from your browser's developer tools after logging in
ACCESS_TOKEN = os.getenv("VINC_ACCESS_TOKEN", "")

if not ACCESS_TOKEN:
    print("❌ Please set VINC_ACCESS_TOKEN environment variable")
    print("   Get it from browser DevTools -> Application -> Cookies -> next-auth.session-token")
    exit(1)

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json",
    "X-Tenant-ID": "vinc"  # Default tenant
}

print("=" * 80)
print("Testing Customer Update Endpoint")
print("=" * 80)

# Step 1: Get current customer data
print(f"\n1️⃣  Fetching current customer data for ID: {RESELLER_ID}")
response = requests.get(
    f"{API_BASE_URL}{API_PREFIX}/customers/{RESELLER_ID}",
    headers=headers
)

if response.status_code != 200:
    print(f"❌ Failed to fetch customer: {response.status_code}")
    print(f"   Response: {response.text}")
    exit(1)

current_data = response.json()
print(f"✅ Current data retrieved successfully")
print(f"   Name: {current_data.get('name')}")
print(f"   Business Name: {current_data.get('business_name')}")
print(f"   Contact Email: {current_data.get('contact_email')}")
print(f"   Contact Phone: {current_data.get('contact_phone')}")
print(f"   Fiscal Code: {current_data.get('fiscal_code')}")
print(f"   VAT Number: {current_data.get('vat_number')}")

# Step 2: Prepare update payload with test values
print(f"\n2️⃣  Preparing update payload with test values")
update_payload = {
    "contact_email": "test.updated@example.com",
    "contact_phone": "+39 123 456 7890",
    "business_name": "Updated Business Name - Test",
    "first_name": "Mario",
    "last_name": "Rossi",
    "fiscal_code": "RSSMRA80A01H501U",  # Valid Italian fiscal code format
    "vat_number": "12345678901",  # Valid Italian VAT format (11 digits)
    "customer_category": "B2B",
    "activity_category": "Retail",
    "gender": "M",
    "cash_payment": True,
    "auto_packaging": False,
    "credit_limit": 5000.00,
    "customer_group": "Premium"
}

print(f"   Update payload: {json.dumps(update_payload, indent=2)}")

# Step 3: Send PATCH request
print(f"\n3️⃣  Sending PATCH request to update customer")
response = requests.patch(
    f"{API_BASE_URL}{API_PREFIX}/customers/{RESELLER_ID}",
    headers=headers,
    json=update_payload
)

if response.status_code != 200:
    print(f"❌ Failed to update customer: {response.status_code}")
    print(f"   Response: {response.text}")
    exit(1)

updated_data = response.json()
print(f"✅ Customer updated successfully!")

# Step 4: Verify the update
print(f"\n4️⃣  Verifying updated values")
verification_passed = True

for field, expected_value in update_payload.items():
    actual_value = updated_data.get(field)
    if actual_value != expected_value:
        print(f"❌ {field}: Expected '{expected_value}', got '{actual_value}'")
        verification_passed = False
    else:
        print(f"✅ {field}: {actual_value}")

# Step 5: Test address update
print(f"\n5️⃣  Testing address update")
addresses = updated_data.get("addresses", [])
if addresses:
    address_id = addresses[0]["id"]
    print(f"   Updating address ID: {address_id}")

    address_update_payload = {
        "label": "Updated Main Office",
        "street": "Via Test 123",
        "city": "Milano",
        "zip": "20100",
        "province": "MI",
        "phone": "+39 02 1234567",
        "email": "office@example.com",
        "is_billing_address": True,
        "is_shipping_address": True
    }

    response = requests.patch(
        f"{API_BASE_URL}{API_PREFIX}/customers/{RESELLER_ID}/addresses/{address_id}",
        headers=headers,
        json=address_update_payload
    )

    if response.status_code != 200:
        print(f"❌ Failed to update address: {response.status_code}")
        print(f"   Response: {response.text}")
    else:
        updated_address = response.json()
        print(f"✅ Address updated successfully!")
        print(f"   Label: {updated_address.get('label')}")
        print(f"   Street: {updated_address.get('street')}")
        print(f"   City: {updated_address.get('city')}")
        print(f"   Province: {updated_address.get('province')}")
else:
    print("⚠️  No addresses found to test")

# Summary
print("\n" + "=" * 80)
if verification_passed:
    print("✅ ALL TESTS PASSED!")
else:
    print("❌ SOME TESTS FAILED")
print("=" * 80)
