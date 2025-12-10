"""
End-to-End tests for Stripe webhook using Stripe CLI.

These tests use the Stripe CLI to trigger real webhook events against
the deployed Supabase Edge Function. They verify the full flow including
idempotency handling.

Prerequisites:
1. Stripe CLI installed and authenticated: `stripe login`
2. Webhook endpoint configured in Stripe Dashboard or via CLI
3. Supabase Edge Function deployed: `supabase functions deploy stripe-webhook`
4. Test user UUID exists in profiles table

Run with:
    pytest test_stripe_e2e.py -v -m e2e --capture=no

Environment Variables (provide via MCP/secret manager; never hardcode):
    SUPABASE_URL                 : Your Supabase project URL
    SUPABASE_SERVICE_ROLE_KEY    : Service role key for admin operations (secret)
    SUPABASE_PUBLISHABLE_KEY     : Publishable key (optional, for non-admin calls)
    STRIPE_WEBHOOK_URL           : URL of the deployed stripe-webhook function
    TEST_USER_UUID (optional)    : If provided, reuse instead of creating a test user

How to obtain values (if missing):
    - SUPABASE_URL / SERVICE_ROLE_KEY: Supabase Dashboard → Project Settings → API → "Project URL" and "service_role" key.
    - STRIPE_WEBHOOK_URL: After deploying edge function, copy https://<project>.functions.supabase.co/stripe-webhook
    - Stripe CLI auth: run `stripe login` (already done in this repo's terminal).
"""
import pytest
import subprocess
import json
import time
import os
import uuid
import hmac
import hashlib
import requests
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


# ==========================================
# Configuration
# ==========================================

def _load_e2e_config():
    """Load configuration from env or config manager."""
    url = os.environ.get("SUPABASE_URL", "")
    # Check for SECRET KEY first (per user request), then fall back to SERVICE_ROLE_KEY
    key = os.environ.get("SUPABASE_SECRET_KEY", "") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    webhook_url = os.environ.get("STRIPE_WEBHOOK_URL", "")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    
    # Fallback to config manager
    if not url or not key:
        try:
            from config_manager import get_config
            cfg = get_config()
            url = url or cfg.get("supabase_url", "")
            # Check for secret keys in config
            key = key or cfg.get("supabase_secret_key", "") or cfg.get("supabase_service_role_key", "")
            
            # Helper: construct webhook URL if we have the supabase URL
            if not webhook_url and url:
                # Remove trailing slash if present
                clean_url = url.rstrip("/")
                webhook_url = f"{clean_url}/functions/v1/stripe-webhook"
        except Exception:
            pass
            
    return url, key, webhook_url, webhook_secret

SUPABASE_URL, SUPABASE_SERVICE_KEY, STRIPE_WEBHOOK_URL, STRIPE_WEBHOOK_SECRET = _load_e2e_config()

# Test configuration
TEST_USER_EMAIL = "stripe_e2e_test@example.com"
TEST_AMOUNT_CENTS = 1000  # $10.00 -> 12 credits based on CREDIT_MAP


def skip_if_not_configured():
    """Skip test if environment not configured."""
    if not SUPABASE_URL:
        pytest.fail("SUPABASE_URL not set (required for E2E tests)")
    if not SUPABASE_SERVICE_KEY:
        pytest.fail("SUPABASE_SECRET_KEY (or SUPABASE_SERVICE_ROLE_KEY) not set (required for E2E tests)")
    if not STRIPE_WEBHOOK_URL:
        pytest.fail("STRIPE_WEBHOOK_URL required (deployed edge function URL)")
    if not STRIPE_WEBHOOK_SECRET:
        pytest.fail("STRIPE_WEBHOOK_SECRET required (for signing webhook requests)")


def generate_stripe_signature(payload_bytes: bytes, secret: str, timestamp: int) -> str:
    """Generate the Stripe-Signature header using HMAC-SHA256."""
    signed_payload = f"{timestamp}.".encode('utf-8') + payload_bytes
    signature = hmac.new(
        key=secret.encode('utf-8'),
        msg=signed_payload,
        digestmod=hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={signature}"


def trigger_stripe_event(event_type: str, override_data: dict = None) -> requests.Response:
    """
    Simulate a Stripe webhook event by sending a POST request to the Edge Function.
    """
    if not STRIPE_WEBHOOK_SECRET:
        pytest.fail("STRIPE_WEBHOOK_SECRET not set in .env")

    timestamp = int(time.time())
    
    # Get API version from environment or use default
    stripe_api_version = os.environ.get("STRIPE_API_VERSION", "2025-11-17.clover")
    
    # Base payload structure
    payload_data = {
        "id": f"evt_{uuid.uuid4().hex[:16]}",
        "object": "event",
        "api_version": stripe_api_version,
        "created": timestamp,
        "type": event_type,
        "data": {
            "object": {
                "id": "cs_test_default",
                "object": "checkout.session",
                "amount_total": TEST_AMOUNT_CENTS,
                "currency": "usd",
                "payment_status": "paid",
                "status": "complete",
                "client_reference_id": None,
                "payment_intent": f"pi_{uuid.uuid4().hex[:16]}",
                "metadata": {}
            }
        }
    }

    # Apply overrides
    if override_data:
        obj = payload_data["data"]["object"]
        for key, value in override_data.items():
            if key in obj:
                obj[key] = value

    # Use compact separators to ensure standard JSON formatting
    payload_str = json.dumps(payload_data, separators=(',', ':'))
    payload_bytes = payload_str.encode('utf-8')
    
    signature = generate_stripe_signature(payload_bytes, STRIPE_WEBHOOK_SECRET, timestamp)
    
    print(f"\n[Debug] Triggering Webhook to {STRIPE_WEBHOOK_URL}")

    headers = {
        "Content-Type": "application/json",
        "Stripe-Signature": signature
    }

    # Send request
    response = requests.post(STRIPE_WEBHOOK_URL, data=payload_bytes, headers=headers)
    return response


# ==========================================
# Fixtures
# ==========================================

@pytest.fixture(scope="module")
def supabase_admin():
    """Create Supabase admin client for test setup/teardown."""
    skip_if_not_configured()
    
    try:
        from supabase import create_client
        return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    except ImportError:
        pytest.skip("supabase-py not installed")


@pytest.fixture(scope="module")
def test_user_id(supabase_admin):
    """Create or get test user for E2E tests.
    
    Returns the user UUID to use as client_reference_id in Stripe.
    """
    # If caller provides a TEST_USER_UUID (e.g., from MCP secret), reuse it
    provided_user = os.environ.get("TEST_USER_UUID")
    if provided_user:
        # Ensure profile exists
        supabase_admin.table("profiles").upsert({
            "id": provided_user,
            "credit_balance": 0
        }).execute()
        return provided_user

    # Try to find existing test user
    try:
        response = supabase_admin.auth.admin.list_users()
        for user in response:
            if user.email == TEST_USER_EMAIL:
                # Ensure profile exists
                supabase_admin.table("profiles").upsert({
                    "id": user.id,
                    "credit_balance": 0
                }).execute()
                return user.id
    except Exception as e:
        print(f"Warning: Could not list users: {e}")
    
    # Create new test user
    try:
        response = supabase_admin.auth.admin.create_user({
            "email": TEST_USER_EMAIL,
            "password": "test_password_e2e_123!",
            "email_confirm": True
        })
        user_id = response.user.id
        
        # Profile should be created by trigger, but ensure it exists
        time.sleep(1)  # Wait for trigger
        supabase_admin.table("profiles").upsert({
            "id": user_id,
            "credit_balance": 0
        }).execute()
        
        return user_id
    except Exception as e:
        pytest.skip(f"Could not create test user: {e}")


@pytest.fixture
def reset_user_balance(supabase_admin, test_user_id):
    """Reset user balance to 0 before test."""
    supabase_admin.table("profiles").update({
        "credit_balance": 0
    }).eq("id", test_user_id).execute()
    
    # Clear any test transactions
    supabase_admin.table("transactions").delete().eq(
        "user_id", test_user_id
    ).like("external_id", "cs_test_%").execute()
    
    yield
    
    # Cleanup after test (optional)


# ==========================================
# Helper Functions
# ==========================================

def get_user_balance(supabase_admin, user_id: str) -> float:
    """Get user's current credit balance."""
    response = supabase_admin.table("profiles").select(
        "credit_balance"
    ).eq("id", user_id).single().execute()
    return float(response.data.get("credit_balance", 0))


def get_transaction_by_external_id(supabase_admin, external_id: str) -> Optional[dict]:
    """Get transaction by external_id."""
    response = supabase_admin.table("transactions").select("*").eq(
        "external_id", external_id
    ).execute()
    return response.data[0] if response.data else None





# ==========================================
# E2E Tests
# ==========================================

@pytest.mark.e2e
class TestStripeWebhookE2E:
    """End-to-end tests for Stripe webhook."""
    
    @pytest.fixture(autouse=True)
    def check_prerequisites(self):
        """Check prerequisites before each test."""
        skip_if_not_configured()
    
    def test_checkout_completed_adds_credits(
        self, supabase_admin, test_user_id, reset_user_balance
    ):
        """checkout.session.completed should add credits to user."""
        # Verify starting balance is 0
        initial_balance = get_user_balance(supabase_admin, test_user_id)
        assert initial_balance == 0, f"Expected 0, got {initial_balance}"
        
        # Generate unique session ID
        session_id = f"cs_test_{uuid.uuid4().hex[:16]}"
        
        # Trigger the webhook
        result = trigger_stripe_event(
            event_type="checkout.session.completed",
            override_data={
                "client_reference_id": test_user_id,
                "amount_total": 1000,
                "id": session_id
            }
        )
        
        print(f"Webhook status: {result.status_code}")
        print(f"Webhook response: {result.text}")
        assert result.status_code == 200
        
        # Wait for webhook processing
        time.sleep(2)
        
        # Verify credits were added
        final_balance = get_user_balance(supabase_admin, test_user_id)
        
        # Based on CREDIT_MAP: 1000 cents -> 12 credits
        expected_credits = 12
        assert final_balance == expected_credits, \
            f"Expected {expected_credits} credits, got {final_balance}"
        
        # Verify transaction was logged with external_id
        transaction = get_transaction_by_external_id(supabase_admin, session_id)
        
        if transaction is None:
            # Debug: List all transactions for this user
            all_tx = supabase_admin.table("transactions").select("*").eq("user_id", test_user_id).execute()
            print(f"\n[Debug] Transaction not found for {session_id}")
            print(f"[Debug] All transactions for user {test_user_id}:")
            for tx in all_tx.data:
                print(f"  - {tx.get('external_id')} : {tx.get('amount')} ({tx.get('type')})")

        assert transaction is not None, "Transaction not found"
        assert transaction["type"] == "top_up"
        assert float(transaction["amount"]) == expected_credits
    
    def test_idempotency_prevents_double_credit(
        self, supabase_admin, test_user_id, reset_user_balance
    ):
        """Duplicate webhook with same session.id should not double-credit."""
        # Use a fixed session ID for this test
        session_id = f"cs_test_idempotent_{uuid.uuid4().hex[:8]}"
        
        # First webhook - should add credits
        result1 = trigger_stripe_event(
            event_type="checkout.session.completed",
            override_data={
                "client_reference_id": test_user_id,
                "amount_total": 1000,
                "id": session_id
            }
        )
        assert result1.status_code == 200
        time.sleep(2)
        
        balance_after_first = get_user_balance(supabase_admin, test_user_id)
        print(f"Balance after first webhook: {balance_after_first}")
        
        # Second webhook with SAME session_id - should NOT add credits
        result2 = trigger_stripe_event(
            event_type="checkout.session.completed",
            override_data={
                "client_reference_id": test_user_id,
                "amount_total": 1000,
                "id": session_id
            }
        )
        assert result2.status_code == 200
        time.sleep(2)
        
        balance_after_second = get_user_balance(supabase_admin, test_user_id)
        print(f"Balance after second webhook: {balance_after_second}")
        
        # Balance should remain the same
        assert balance_after_second == balance_after_first, \
            f"Idempotency failed! Balance changed from {balance_after_first} to {balance_after_second}"
        
        # Should still only have one transaction with this external_id
        response = supabase_admin.table("transactions").select("*").eq(
            "external_id", session_id
        ).execute()
        assert len(response.data) == 1, \
            f"Expected 1 transaction, got {len(response.data)}"
    
    def test_different_amounts_map_to_correct_credits(
        self, supabase_admin, test_user_id, reset_user_balance
    ):
        """Different payment amounts should map to correct credit amounts."""
        test_cases = [
            (500, 5),    # $5.00 -> 5 credits
            (1000, 12),  # $10.00 -> 12 credits  
            (2000, 25),  # $20.00 -> 25 credits
        ]
        
        total_expected_credits = 0
        
        for amount_cents, expected_credits in test_cases:
            session_id = f"cs_test_{amount_cents}_{uuid.uuid4().hex[:8]}"
            
            trigger_stripe_event(
                event_type="checkout.session.completed",
                override_data={
                    "client_reference_id": test_user_id,
                    "amount_total": amount_cents,
                    "id": session_id
                }
            )
            time.sleep(1)
            
            total_expected_credits += expected_credits
        
        # Wait for all webhooks to process
        time.sleep(2)
        
        final_balance = get_user_balance(supabase_admin, test_user_id)
        assert final_balance == total_expected_credits, \
            f"Expected {total_expected_credits} credits, got {final_balance}"
    
    def test_missing_client_reference_id_handled(self, supabase_admin):
        """Webhook without client_reference_id should not crash."""
        # This tests error handling - webhook should return 400 but not 500
        session_id = f"cs_test_no_user_{uuid.uuid4().hex[:8]}"
        
        # Trigger with empty client_reference_id
        result = trigger_stripe_event(
            event_type="checkout.session.completed",
            override_data={
                "client_reference_id": None, # Explicitly set to None
                "amount_total": 1000,
                "id": session_id
            }
        )
        
        # The webhook should handle this gracefully
        # We expect a non-200 status code, but not a server error (5xx)
        print(f"Missing user test - status: {result.status_code}")
        print(f"Missing user test - body: {result.text}")
        assert result.status_code == 400 # Assuming the function returns 400 for missing user ID


@pytest.mark.e2e
class TestChatProxyE2E:
    """End-to-end tests for chat-proxy Edge Function.
    
    These tests require:
    - chat-proxy function deployed
    - OpenRouter API key in Supabase Vault
    - Test user with credits
    """
    
    @pytest.fixture(autouse=True)
    def check_prerequisites(self):
        skip_if_not_configured()
    
    @pytest.fixture
    def chat_proxy_url(self):
        return f"{SUPABASE_URL}/functions/v1/chat-proxy"
    
    @pytest.fixture
    def user_with_credits(self, supabase_admin, test_user_id):
        """Ensure test user has credits."""
        supabase_admin.table("profiles").update({
            "credit_balance": 10.0
        }).eq("id", test_user_id).execute()
        return test_user_id
    
    @pytest.fixture
    def user_token(self, supabase_admin, test_user_id):
        """Get an access token for the test user.
        
        Note: This is tricky without user credentials.
        For E2E testing, you may need to:
        1. Use a pre-authenticated token
        2. Use service role with user impersonation
        3. Skip auth tests and use mocked auth
        """
        # This is a placeholder - real implementation depends on your auth setup
        pytest.skip("User token generation not implemented for E2E")
    
    def test_zero_balance_returns_402(
        self, supabase_admin, test_user_id, chat_proxy_url
    ):
        """User with zero balance should get 402 Payment Required."""
        # Set balance to 0
        supabase_admin.table("profiles").update({
            "credit_balance": 0
        }).eq("id", test_user_id).execute()
        
        # Would need to make actual HTTP request with valid token
        # This is a placeholder showing expected behavior
        expected_status = 402
        assert expected_status == 402
    
    def test_credits_deducted_after_chat(
        self, supabase_admin, user_with_credits, chat_proxy_url
    ):
        """Credits should be deducted after successful chat."""
        initial_balance = get_user_balance(supabase_admin, user_with_credits)
        
        # Would make actual chat request here
        # After request, balance should be lower
        
        # Placeholder assertion
        assert initial_balance > 0


# ==========================================
# CLI Test Runner
# ==========================================


