"""Tests for payment providers."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.vinc_api.modules.payments.providers.base import PaymentIntentResult
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
