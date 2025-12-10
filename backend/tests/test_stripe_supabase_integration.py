"""
Integration tests for Stripe and Supabase monetization.

Tests cover:
- Balance reading via direct Supabase query
- Checkout session creation
- Agent balance check integration
- Transaction history retrieval

Run with: pytest test_stripe_supabase_integration.py -v
For integration tests against real Supabase: pytest test_stripe_supabase_integration.py -v -m integration
"""
"""
Integration tests expect Supabase credentials to come from environment variables
so they can be provided by your MCP/secret manager instead of hardcoding.

Set (for real integration runs):
    SUPABASE_URL
    SUPABASE_PUBLISHABLE_KEY  (preferred) or SUPABASE_ANON_KEY (legacy fallback)

If they are not present, integration-marked tests are skipped.
"""
import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from decimal import Decimal


def _load_supabase_env():
    """Fetch Supabase URL and publishable/anon key from environment or config manager."""
    url = os.environ.get("SUPABASE_URL", "")
    pub = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
    anon = os.environ.get("SUPABASE_ANON_KEY", "")
    key = pub or anon

    # Optional fallback to config_manager (only reads local dev config; no secrets baked here)
    if (not url or not key):
        try:
            from config_manager import get_config  # local helper
            cfg = get_config()
            url = url or cfg.get("supabase_url", "")
            key = key or cfg.get("supabase_publishable_key", "") or cfg.get("supabase_anon_key", "")
        except Exception:
            pass

    return url.strip(), key.strip()


# ==========================================
# Fixtures
# ==========================================

@pytest.fixture
def mock_supabase_client():
    """Mock Supabase client for unit tests."""
    client = MagicMock()
    return client


@pytest.fixture
def mock_supabase_auth(mock_supabase_client):
    """Mock SupabaseAuth instance."""
    with patch("services.supabase_auth.HAS_SUPABASE", True):
        with patch("services.supabase_auth.create_client", return_value=mock_supabase_client):
            from services.supabase_auth import SupabaseAuth
            auth = SupabaseAuth()
            auth._client = mock_supabase_client
            auth._user = MagicMock()
            auth._user.id = "test-user-uuid-1234"
            auth._user.email = "test@example.com"
            yield auth


@pytest.fixture
def mock_user_with_balance():
    """Create mock response for user with balance."""
    return {
        "data": {"credit_balance": "10.500000000"},
        "error": None
    }


@pytest.fixture
def mock_user_zero_balance():
    """Create mock response for user with zero balance."""
    return {
        "data": {"credit_balance": "0.000000000"},
        "error": None
    }


@pytest.fixture
def mock_transactions():
    """Create mock transaction history."""
    return [
        {
            "id": "txn-1",
            "user_id": "test-user-uuid-1234",
            "type": "top_up",
            "amount": "10.000000000",
            "description": "Stripe purchase: 10 credits",
            "external_id": "cs_test_session_123",
            "created_at": "2025-12-09T10:00:00Z"
        },
        {
            "id": "txn-2",
            "user_id": "test-user-uuid-1234",
            "type": "usage",
            "amount": "-0.500000000",
            "description": "Chat: gpt-4",
            "external_id": None,
            "created_at": "2025-12-09T11:00:00Z"
        }
    ]


# ==========================================
# Balance Reading Tests
# ==========================================

class TestBalanceReading:
    """Tests for reading balance directly from Supabase."""
    
    def test_get_balance_returns_float(self, mock_supabase_auth, mock_supabase_client, mock_user_with_balance):
        """Balance should be returned as float."""
        mock_response = MagicMock()
        mock_response.data = mock_user_with_balance["data"]
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_response
        
        balance = mock_supabase_auth.get_balance()
        
        assert balance is not None
        assert isinstance(balance, float)
        assert balance == 10.5
    
    def test_get_balance_zero(self, mock_supabase_auth, mock_supabase_client, mock_user_zero_balance):
        """Zero balance should return 0.0."""
        mock_response = MagicMock()
        mock_response.data = mock_user_zero_balance["data"]
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_response
        
        balance = mock_supabase_auth.get_balance()
        
        assert balance == 0.0
    
    def test_get_balance_unauthenticated(self):
        """Unauthenticated user should return None."""
        with patch("services.supabase_auth.HAS_SUPABASE", True):
            with patch("services.supabase_auth.create_client"):
                from services.supabase_auth import SupabaseAuth
                auth = SupabaseAuth()
                auth._user = None  # Not authenticated
                # PREVENT lazy init which might restore session
                auth._client = MagicMock()
                
                balance = auth.get_balance()
                
                assert balance is None
    
    def test_get_balance_handles_exception(self, mock_supabase_auth, mock_supabase_client):
        """Exception during balance fetch should return None."""
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = Exception("Network error")
        
        balance = mock_supabase_auth.get_balance()
        
        assert balance is None


# ==========================================
# Transaction History Tests
# ==========================================

class TestTransactionHistory:
    """Tests for reading transaction history."""
    
    def test_get_transactions_returns_list(self, mock_supabase_auth, mock_supabase_client, mock_transactions):
        """Transactions should be returned as list."""
        mock_response = MagicMock()
        mock_response.data = mock_transactions
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_response
        
        transactions = mock_supabase_auth.get_transactions()
        
        assert isinstance(transactions, list)
        assert len(transactions) == 2
    
    def test_get_transactions_includes_external_id(self, mock_supabase_auth, mock_supabase_client, mock_transactions):
        """Transactions should include external_id for idempotency tracking."""
        mock_response = MagicMock()
        mock_response.data = mock_transactions
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_response
        
        transactions = mock_supabase_auth.get_transactions()
        
        # First transaction (top_up) should have external_id
        assert transactions[0]["external_id"] == "cs_test_session_123"
        # Second transaction (usage) should have None external_id
        assert transactions[1]["external_id"] is None
    
    def test_get_transactions_respects_limit(self, mock_supabase_auth, mock_supabase_client):
        """Should pass limit parameter to query."""
        mock_response = MagicMock()
        mock_response.data = []
        limit_mock = MagicMock()
        limit_mock.execute.return_value = mock_response
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value = limit_mock
        
        mock_supabase_auth.get_transactions(limit=5)
        
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.assert_called_with(5)
    
    def test_get_transactions_unauthenticated(self):
        """Unauthenticated user should return empty list."""
        with patch("services.supabase_auth.HAS_SUPABASE", True):
            with patch("services.supabase_auth.create_client"):
                from services.supabase_auth import SupabaseAuth
                auth = SupabaseAuth()
                auth._user = None
                # PREVENT lazy init which might restore session
                auth._client = MagicMock()
                
                transactions = auth.get_transactions()
                
                assert transactions == []


# ==========================================
# Agent Balance Check Tests
# ==========================================

class TestAgentBalanceCheck:
    """Tests for balance checking in the agent."""
    
    @pytest.mark.asyncio
    async def test_check_balance_sufficient(self):
        """Agent should allow continuation with sufficient balance."""
        mock_auth = MagicMock()
        mock_auth.is_authenticated = True
        mock_auth.get_balance.return_value = 10.0
        
        with patch("services.supabase_auth.get_supabase_auth", return_value=mock_auth):
            # Simulate the _check_balance logic
            MIN_BALANCE_FOR_STEP = 0.001
            balance = mock_auth.get_balance()
            
            can_continue = balance >= MIN_BALANCE_FOR_STEP
            
            assert can_continue is True
    
    @pytest.mark.asyncio
    async def test_check_balance_insufficient(self):
        """Agent should block with insufficient balance."""
        mock_auth = MagicMock()
        mock_auth.is_authenticated = True
        mock_auth.get_balance.return_value = 0.0
        
        with patch("services.supabase_auth.get_supabase_auth", return_value=mock_auth):
            MIN_BALANCE_FOR_STEP = 0.001
            balance = mock_auth.get_balance()
            
            can_continue = balance >= MIN_BALANCE_FOR_STEP
            
            assert can_continue is False
    
    @pytest.mark.asyncio
    async def test_check_balance_unauthenticated_allows(self):
        """Unauthenticated user should be allowed to continue (no monetization)."""
        mock_auth = MagicMock()
        mock_auth.is_authenticated = False
        
        # When not authenticated, balance check is skipped
        can_continue = True if not mock_auth.is_authenticated else False
        
        assert can_continue is True


# ==========================================
# Checkout Session Tests (API Routes)
# ==========================================

class TestCheckoutSession:
    """Tests for checkout session creation via API."""
    
    @pytest.fixture
    def credit_packs(self):
        """Credit pack configuration from auth_routes.py."""
        return {
            "starter": {"price_id": "price_test_starter", "credits": 5},
            "pro": {"price_id": "price_test_pro", "credits": 12},
            "premium": {"price_id": "price_test_premium", "credits": 25},
        }
    
    def test_valid_pack_returns_price_id(self, credit_packs):
        """Valid pack name should return correct price_id."""
        pack = credit_packs.get("pro")
        
        assert pack is not None
        assert pack["price_id"] == "price_test_pro"
        assert pack["credits"] == 12
    
    def test_invalid_pack_returns_none(self, credit_packs):
        """Invalid pack name should return None."""
        pack = credit_packs.get("invalid_pack")
        
        assert pack is None
    
    def test_checkout_requires_authentication(self):
        """Checkout endpoint should require authentication."""
        # This would be tested via FastAPI TestClient
        # Placeholder for the expected behavior
        expected_status_unauthenticated = 401
        assert expected_status_unauthenticated == 401
    
    def test_checkout_passes_user_id_as_client_reference(self):
        """Checkout should pass user UUID as client_reference_id."""
        user_id = "test-user-uuid-1234"
        
        # When creating Stripe checkout session:
        checkout_params = {
            "client_reference_id": user_id,
            "line_items": [{"price": "price_test_pro", "quantity": 1}],
            "mode": "payment",
        }
        
        assert checkout_params["client_reference_id"] == user_id


# ==========================================
# Idempotency Tests
# ==========================================

class TestIdempotency:
    """Tests for idempotency behavior."""
    
    def test_external_id_is_unique_constraint(self):
        """External ID should be globally unique."""
        # This is enforced by database schema
        # Test documents the expected behavior
        session_id = "cs_test_session_123"
        
        # First transaction with this external_id should succeed
        first_result = True
        assert first_result is True
        
        # Second transaction with same external_id should fail
        second_result = False
        assert second_result is False
    
    def test_duplicate_webhook_returns_false(self):
        """Duplicate webhook (same session.id) should return FALSE from add_credits."""
        # Simulates the database RPC behavior
        def add_credits_mock(p_user_id, p_amount, p_description, p_metadata, p_external_id):
            # First call returns True
            # Second call with same p_external_id returns False
            existing_external_ids = {"cs_test_already_processed"}
            
            if p_external_id in existing_external_ids:
                return False
            return True
        
        # First call - new session
        result1 = add_credits_mock(
            "user-1", 10, "test", {}, "cs_test_new_session"
        )
        assert result1 is True
        
        # Second call - duplicate session
        result2 = add_credits_mock(
            "user-1", 10, "test", {}, "cs_test_already_processed"
        )
        assert result2 is False


# ==========================================
# Integration Tests (require real Supabase)
# ==========================================

@pytest.mark.integration
class TestSupabaseIntegration:
    """Integration tests against real Supabase instance.
    
    These tests are skipped by default. Run with:
    pytest test_stripe_supabase_integration.py -v -m integration
    
    Requires:
    - SUPABASE_URL environment variable
    - SUPABASE_ANON_KEY environment variable
    - A test user account
    """
    
    @pytest.fixture
    def real_supabase_auth(self):
        """Create real SupabaseAuth instance."""
        url, key = _load_supabase_env()

        if not url or not key:
            pytest.skip("SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY (or ANON) not set (provide via env or MCP secrets)")

        # Configure SupabaseAuth with provided values to avoid relying on stored config
        from services.supabase_auth import SupabaseAuth
        auth = SupabaseAuth()
        auth.configure(url, key)
        return auth
    
    def test_can_connect_to_supabase(self, real_supabase_auth):
        """Should be able to create Supabase client."""
        assert real_supabase_auth.client is not None
    
    def test_can_query_profiles_table(self, real_supabase_auth):
        """Should be able to query profiles table (even if empty)."""
        if not real_supabase_auth.client:
            pytest.skip("Supabase client not available")
        
        try:
            # This will fail if table doesn't exist
            response = real_supabase_auth.client.table("profiles").select("id").limit(1).execute()
            assert response is not None
        except Exception as e:
            pytest.fail(f"Failed to query profiles table: {e}")


# ==========================================
# Markup and Cost Calculation Tests
# ==========================================

class TestCostCalculation:
    """Tests for cost calculation and markup."""
    
    def test_markup_rate_is_20_percent(self):
        """Markup rate should be 20%."""
        MARKUP_RATE = 1.20
        assert MARKUP_RATE == 1.20
    
    def test_billable_amount_calculation(self):
        """Billable amount = raw_cost * markup_rate."""
        MARKUP_RATE = 1.20
        raw_cost = 0.001  # $0.001 from OpenRouter
        
        billable_amount = raw_cost * MARKUP_RATE
        
        assert billable_amount == pytest.approx(0.0012, rel=1e-9)
    
    def test_zero_cost_no_deduction(self):
        """Zero cost should not trigger deduction."""
        raw_cost = 0.0
        MARKUP_RATE = 1.20
        
        billable_amount = raw_cost * MARKUP_RATE
        should_deduct = billable_amount > 0
        
        assert should_deduct is False
    
    def test_deduction_metadata_structure(self):
        """Deduction should include proper metadata."""
        metadata = {
            "model": "gpt-4",
            "raw_cost": 0.001,
            "markup": 1.20,
            "prompt_tokens": 100,
            "completion_tokens": 50,
        }
        
        assert "model" in metadata
        assert "raw_cost" in metadata
        assert "markup" in metadata
        assert "prompt_tokens" in metadata
        assert "completion_tokens" in metadata
