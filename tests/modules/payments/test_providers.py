"""Tests for payment providers."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.vinc_api.modules.payments.providers.banca_sella import BancaSellaProvider
from src.vinc_api.modules.payments.providers.bank_transfer import BankTransferProvider
from src.vinc_api.modules.payments.providers.base import PaymentIntentResult
from src.vinc_api.modules.payments.providers.nexi import NexiProvider
from src.vinc_api.modules.payments.providers.paypal import PayPalProvider
from src.vinc_api.modules.payments.providers.scalapay import ScalapayProvider
from src.vinc_api.modules.payments.providers.stripe import StripeProvider


class TestStripeProvider:
    """Test suite for Stripe provider."""

    @pytest.fixture
    def stripe_credentials(self):
        """Provide test Stripe credentials."""
        return {
            "secret_key": "sk_test_123456789",
            "publishable_key": "pk_test_123456789",
            "webhook_secret": "whsec_test_123456789",
        }

    @pytest.fixture
    def stripe_provider(self, stripe_credentials):
        """Provide a Stripe provider instance."""
        return StripeProvider(
            credentials=stripe_credentials,
            mode="test",
            config={"payment_method_types": ["card"]},
        )

    def test_provider_name(self, stripe_provider):
        """Test provider name."""
        assert stripe_provider.provider_name == "stripe"

    def test_is_test_mode(self, stripe_provider):
        """Test mode check."""
        assert stripe_provider.is_test_mode() is True

    def test_get_credential(self, stripe_provider):
        """Test getting credentials."""
        assert stripe_provider.get_credential("secret_key") == "sk_test_123456789"
        assert stripe_provider.get_credential("missing", "default") == "default"

    def test_get_config(self, stripe_provider):
        """Test getting config values."""
        assert stripe_provider.get_config("payment_method_types") == ["card"]
        assert stripe_provider.get_config("missing", "default") == "default"

    @pytest.mark.asyncio
    @patch("src.vinc_api.modules.payments.providers.stripe.stripe")
    async def test_create_payment_intent(self, mock_stripe, stripe_provider):
        """Test creating a payment intent."""
        # Mock Stripe PaymentIntent
        mock_intent = MagicMock()
        mock_intent.id = "pi_test_123"
        mock_intent.client_secret = "pi_test_123_secret"
        mock_intent.status = "requires_payment_method"
        mock_intent.amount = 1000
        mock_intent.currency = "eur"
        mock_intent.to_dict.return_value = {"id": "pi_test_123"}

        mock_stripe.PaymentIntent.create.return_value = mock_intent

        # Create payment intent
        result = await stripe_provider.create_payment_intent(
            amount=10.00,
            currency="EUR",
            order_id=str(uuid4()),
            customer_email="test@example.com",
        )

        # Assertions
        assert isinstance(result, PaymentIntentResult)
        assert result.payment_intent_id == "pi_test_123"
        assert result.client_secret == "pi_test_123_secret"
        assert result.status == "pending"
        assert result.amount == 10.00

        # Verify Stripe was called correctly
        mock_stripe.PaymentIntent.create.assert_called_once()
        call_kwargs = mock_stripe.PaymentIntent.create.call_args[1]
        assert call_kwargs["amount"] == 1000  # cents
        assert call_kwargs["currency"] == "eur"

    @pytest.mark.asyncio
    @patch("src.vinc_api.modules.payments.providers.stripe.stripe")
    async def test_get_payment_status(self, mock_stripe, stripe_provider):
        """Test getting payment status."""
        # Mock Stripe PaymentIntent
        mock_intent = MagicMock()
        mock_intent.id = "pi_test_123"
        mock_intent.client_secret = "pi_test_123_secret"
        mock_intent.status = "succeeded"
        mock_intent.amount = 1000
        mock_intent.currency = "eur"
        mock_intent.next_action = None
        mock_intent.to_dict.return_value = {"id": "pi_test_123"}

        mock_stripe.PaymentIntent.retrieve.return_value = mock_intent

        # Get status
        result = await stripe_provider.get_payment_status("pi_test_123")

        # Assertions
        assert result.payment_intent_id == "pi_test_123"
        assert result.status == "succeeded"
        assert result.amount == 10.00
        assert result.currency == "EUR"

    @pytest.mark.asyncio
    @patch("src.vinc_api.modules.payments.providers.stripe.stripe")
    async def test_refund_payment(self, mock_stripe, stripe_provider):
        """Test refunding a payment."""
        # Mock Stripe Refund
        mock_refund = MagicMock()
        mock_refund.id = "re_test_123"
        mock_refund.amount = 500
        mock_refund.currency = "eur"
        mock_refund.status = "succeeded"
        mock_refund.to_dict.return_value = {"id": "re_test_123"}

        mock_stripe.Refund.create.return_value = mock_refund

        # Create refund
        result = await stripe_provider.refund_payment(
            transaction_id="pi_test_123",
            amount=5.00,
            reason="Customer request",
        )

        # Assertions
        assert result.refund_id == "re_test_123"
        assert result.amount == 5.00
        assert result.status == "succeeded"

    def test_get_payment_method_info(self, stripe_provider):
        """Test getting payment method info."""
        info = stripe_provider.get_payment_method_info()

        assert info["name"] == "Stripe"
        assert info["type"] == "card"
        assert info["supports_refund"] is True
        assert info["requires_redirect"] is False

    def test_map_stripe_status(self, stripe_provider):
        """Test status mapping."""
        # Test various Stripe statuses
        assert stripe_provider._map_stripe_status("requires_payment_method") == "pending"
        assert stripe_provider._map_stripe_status("processing") == "processing"
        assert stripe_provider._map_stripe_status("succeeded") == "succeeded"
        assert stripe_provider._map_stripe_status("canceled") == "cancelled"
        assert stripe_provider._map_stripe_status("unknown") == "pending"


class TestPayPalProvider:
    """Test suite for PayPal provider."""

    @pytest.fixture
    def paypal_credentials(self):
        """Provide test PayPal credentials."""
        return {
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
        }

    @pytest.fixture
    def paypal_provider(self, paypal_credentials):
        """Provide a PayPal provider instance."""
        return PayPalProvider(
            credentials=paypal_credentials,
            mode="test",
            config={"brand_name": "Test Store"},
        )

    def test_provider_name(self, paypal_provider):
        """Test provider name."""
        assert paypal_provider.provider_name == "paypal"

    def test_is_test_mode(self, paypal_provider):
        """Test mode check."""
        assert paypal_provider.is_test_mode() is True

    @pytest.mark.asyncio
    @patch("src.vinc_api.modules.payments.providers.paypal.httpx.AsyncClient")
    async def test_create_payment_intent(self, mock_client_class, paypal_provider):
        """Test creating a PayPal order."""
        # Mock API responses
        mock_client = MagicMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Mock token response
        token_response = MagicMock()
        token_response.json.return_value = {"access_token": "test_token"}
        token_response.raise_for_status = MagicMock()

        # Mock order creation response
        order_response = MagicMock()
        order_response.json.return_value = {
            "id": "ORDER123",
            "status": "CREATED",
            "links": [
                {"rel": "approve", "href": "https://paypal.com/approve"}
            ],
        }
        order_response.raise_for_status = MagicMock()

        mock_client.post.side_effect = [token_response, order_response]

        result = await paypal_provider.create_payment_intent(
            amount=100.00,
            currency="EUR",
            order_id=str(uuid4()),
            customer_email="test@example.com",
        )

        assert isinstance(result, PaymentIntentResult)
        assert result.payment_intent_id == "ORDER123"
        assert result.redirect_url == "https://paypal.com/approve"
        assert result.requires_action is True

    def test_get_payment_method_info(self, paypal_provider):
        """Test getting payment method info."""
        info = paypal_provider.get_payment_method_info()

        assert info["name"] == "PayPal"
        assert info["type"] == "digital_wallet"
        assert info["supports_refund"] is True
        assert info["requires_redirect"] is True


class TestNexiProvider:
    """Test suite for Nexi provider."""

    @pytest.fixture
    def nexi_credentials(self):
        """Provide test Nexi credentials."""
        return {
            "api_key": "test_api_key",
            "webhook_secret": "test_webhook_secret",
        }

    @pytest.fixture
    def nexi_provider(self, nexi_credentials):
        """Provide a Nexi provider instance."""
        return NexiProvider(
            credentials=nexi_credentials,
            mode="test",
            config={"language": "ITA"},
        )

    def test_provider_name(self, nexi_provider):
        """Test provider name."""
        assert nexi_provider.provider_name == "nexi"

    def test_is_test_mode(self, nexi_provider):
        """Test mode check."""
        assert nexi_provider.is_test_mode() is True

    @pytest.mark.asyncio
    @patch("src.vinc_api.modules.payments.providers.nexi.httpx.AsyncClient")
    async def test_create_payment_intent(self, mock_client_class, nexi_provider):
        """Test creating a Nexi payment."""
        mock_client = MagicMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "paymentId": "NEXI123",
            "redirectUrl": "https://nexi.it/pay",
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        result = await nexi_provider.create_payment_intent(
            amount=50.00,
            currency="EUR",
            order_id=str(uuid4()),
            customer_email="test@example.com",
        )

        assert isinstance(result, PaymentIntentResult)
        assert result.payment_intent_id == "NEXI123"
        assert result.redirect_url == "https://nexi.it/pay"
        assert result.requires_action is True

    def test_get_payment_method_info(self, nexi_provider):
        """Test getting payment method info."""
        info = nexi_provider.get_payment_method_info()

        assert info["name"] == "Nexi"
        assert info["type"] == "card"
        assert info["supports_refund"] is True
        assert info["requires_redirect"] is True

    def test_map_nexi_status(self, nexi_provider):
        """Test status mapping."""
        assert nexi_provider._map_nexi_status("pending") == "pending"
        assert nexi_provider._map_nexi_status("captured") == "succeeded"
        assert nexi_provider._map_nexi_status("declined") == "failed"
        assert nexi_provider._map_nexi_status("cancelled") == "cancelled"


class TestBancaSellaProvider:
    """Test suite for Banca Sella provider."""

    @pytest.fixture
    def banca_sella_credentials(self):
        """Provide test Banca Sella credentials."""
        return {
            "shop_login": "test_shop",
            "api_key": "test_api_key",
        }

    @pytest.fixture
    def banca_sella_provider(self, banca_sella_credentials):
        """Provide a Banca Sella provider instance."""
        return BancaSellaProvider(
            credentials=banca_sella_credentials,
            mode="test",
            config={"language": "2"},  # Italian
        )

    def test_provider_name(self, banca_sella_provider):
        """Test provider name."""
        assert banca_sella_provider.provider_name == "banca_sella"

    def test_is_test_mode(self, banca_sella_provider):
        """Test mode check."""
        assert banca_sella_provider.is_test_mode() is True

    @pytest.mark.asyncio
    @patch("src.vinc_api.modules.payments.providers.banca_sella.httpx.AsyncClient")
    async def test_create_payment_intent(self, mock_client_class, banca_sella_provider):
        """Test creating a Banca Sella payment."""
        mock_client = MagicMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "paymentID": "SELLA123",
            "paymentToken": "token123",
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        result = await banca_sella_provider.create_payment_intent(
            amount=75.00,
            currency="EUR",
            order_id=str(uuid4()),
            customer_email="test@example.com",
        )

        assert isinstance(result, PaymentIntentResult)
        assert result.payment_intent_id == "SELLA123"
        assert result.client_secret == "token123"
        assert result.requires_action is True

    def test_get_payment_method_info(self, banca_sella_provider):
        """Test getting payment method info."""
        info = banca_sella_provider.get_payment_method_info()

        assert info["name"] == "Banca Sella"
        assert info["type"] == "card"
        assert info["supports_refund"] is True
        assert info["requires_redirect"] is True

    def test_map_banca_sella_status(self, banca_sella_provider):
        """Test status mapping."""
        assert banca_sella_provider._map_banca_sella_status("OK") == "succeeded"
        assert banca_sella_provider._map_banca_sella_status("KO") == "failed"
        assert banca_sella_provider._map_banca_sella_status("PENDING") == "pending"
        assert banca_sella_provider._map_banca_sella_status("XX") == "cancelled"


class TestScalapayProvider:
    """Test suite for Scalapay provider."""

    @pytest.fixture
    def scalapay_credentials(self):
        """Provide test Scalapay credentials."""
        return {
            "api_key": "test_api_key",
        }

    @pytest.fixture
    def scalapay_provider(self, scalapay_credentials):
        """Provide a Scalapay provider instance."""
        return ScalapayProvider(
            credentials=scalapay_credentials,
            mode="test",
            config={},
        )

    def test_provider_name(self, scalapay_provider):
        """Test provider name."""
        assert scalapay_provider.provider_name == "scalapay"

    def test_is_test_mode(self, scalapay_provider):
        """Test mode check."""
        assert scalapay_provider.is_test_mode() is True

    @pytest.mark.asyncio
    @patch("src.vinc_api.modules.payments.providers.scalapay.httpx.AsyncClient")
    async def test_create_payment_intent(self, mock_client_class, scalapay_provider):
        """Test creating a Scalapay order."""
        mock_client = MagicMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "token": "SCALAPAY123",
            "checkoutUrl": "https://scalapay.com/checkout",
            "status": "pending",
            "totalAmount": {"amount": "100.00", "currency": "EUR"},
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        result = await scalapay_provider.create_payment_intent(
            amount=100.00,
            currency="EUR",
            order_id=str(uuid4()),
            customer_email="test@example.com",
            metadata={
                "customer_first_name": "John",
                "customer_last_name": "Doe",
                "billing_address": "Via Test 1",
                "billing_city": "Milano",
                "billing_postcode": "20100",
            },
        )

        assert isinstance(result, PaymentIntentResult)
        assert result.payment_intent_id == "SCALAPAY123"
        assert result.redirect_url == "https://scalapay.com/checkout"
        assert result.requires_action is True

    def test_get_payment_method_info(self, scalapay_provider):
        """Test getting payment method info."""
        info = scalapay_provider.get_payment_method_info()

        assert info["name"] == "Scalapay"
        assert info["type"] == "bnpl"
        assert info["supports_refund"] is True
        assert info["requires_redirect"] is True
        assert info["max_amount"] == 2000.00  # Scalapay limit

    def test_map_scalapay_status(self, scalapay_provider):
        """Test status mapping."""
        assert scalapay_provider._map_scalapay_status("pending") == "pending"
        assert scalapay_provider._map_scalapay_status("approved") == "processing"
        assert scalapay_provider._map_scalapay_status("captured") == "succeeded"
        assert scalapay_provider._map_scalapay_status("declined") == "failed"


class TestBankTransferProvider:
    """Test suite for Bank Transfer provider."""

    @pytest.fixture
    def bank_transfer_credentials(self):
        """Provide test Bank Transfer credentials."""
        return {
            "iban": "IT60X0542811101000000123456",
            "bic": "BPMOIT22",
        }

    @pytest.fixture
    def bank_transfer_provider(self, bank_transfer_credentials):
        """Provide a Bank Transfer provider instance."""
        return BankTransferProvider(
            credentials=bank_transfer_credentials,
            mode="test",
            config={
                "bank_name": "Test Bank",
                "account_holder": "Test Company",
            },
        )

    def test_provider_name(self, bank_transfer_provider):
        """Test provider name."""
        assert bank_transfer_provider.provider_name == "bank_transfer"

    @pytest.mark.asyncio
    async def test_create_payment_intent(self, bank_transfer_provider):
        """Test creating bank transfer instructions."""
        result = await bank_transfer_provider.create_payment_intent(
            amount=200.00,
            currency="EUR",
            order_id="ORDER123",
            customer_email="test@example.com",
        )

        assert isinstance(result, PaymentIntentResult)
        assert result.payment_intent_id.startswith("BT-ORDER123")
        assert result.requires_action is True
        assert result.status == "pending"
        assert result.amount == 200.00

        # Check instructions included in metadata
        assert "bank_transfer" in result.metadata
        assert "reference" in result.metadata["bank_transfer"]
        assert "bank_details" in result.metadata["bank_transfer"]

    @pytest.mark.asyncio
    async def test_confirm_payment(self, bank_transfer_provider):
        """Test confirming bank transfer."""
        result = await bank_transfer_provider.confirm_payment(
            payment_intent_id="BT-TEST-123456",
            payment_data={
                "amount": 200.00,
                "currency": "EUR",
                "confirmed_at": "2024-01-01T10:00:00",
                "confirmed_by": "admin_user",
            },
        )

        assert isinstance(result, PaymentIntentResult)
        assert result.payment_intent_id == "BT-TEST-123456"
        assert result.status == "succeeded"
        assert result.requires_action is False

    @pytest.mark.asyncio
    async def test_refund_payment(self, bank_transfer_provider):
        """Test creating refund."""
        from src.vinc_api.modules.payments.providers.base import RefundResult

        result = await bank_transfer_provider.refund_payment(
            transaction_id="BT-TEST-123456",
            amount=50.00,
            reason="Customer request",
        )

        assert isinstance(result, RefundResult)
        assert result.refund_id.startswith("REFUND-BT-TEST")
        assert result.amount == 50.00
        assert result.status == "pending"  # Manual refunds

    def test_get_payment_method_info(self, bank_transfer_provider):
        """Test getting payment method info."""
        info = bank_transfer_provider.get_payment_method_info()

        assert info["name"] == "Bank Transfer"
        assert info["type"] == "bank_transfer"
        assert info["supports_refund"] is True
        assert info["requires_redirect"] is False

    @pytest.mark.asyncio
    async def test_webhook_not_supported(self, bank_transfer_provider):
        """Test that webhooks are not supported."""
        with pytest.raises(NotImplementedError):
            await bank_transfer_provider.verify_webhook(
                payload={},
                signature=None,
                headers=None,
            )
