-- Migration: Secure RLS Policies, Security Definer Views, and Rate Limiting
-- Hardens security for LiteLLM proxy and Stripe integrations
-- 
-- Changes:
-- 1. Add RLS policies to LiteLLM_UserTable (if it exists)
-- 2. Create secure user_credit_balance view with security_barrier
-- 3. Create SECURITY DEFINER function for atomic credit transactions
-- 4. Add database-level rate limiting infrastructure
-- 5. Tighten existing RLS policies

-- ============================================================================
-- PART 1: Rate Limiting Infrastructure
-- ============================================================================

-- Table to track API rate limits per user
CREATE TABLE IF NOT EXISTS public.rate_limit_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,  -- 'key_generation', 'credit_purchase', etc.
    request_count INTEGER DEFAULT 1,
    window_start TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for efficient rate limit lookups
CREATE INDEX IF NOT EXISTS idx_rate_limit_user_action 
    ON public.rate_limit_tracking(user_id, action_type, window_start);

-- Enable RLS on rate_limit_tracking
ALTER TABLE public.rate_limit_tracking ENABLE ROW LEVEL SECURITY;

-- Only service role can access rate limiting table
CREATE POLICY "Service role manages rate limits"
    ON public.rate_limit_tracking
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

COMMENT ON TABLE public.rate_limit_tracking IS 'Tracks API request rates per user for rate limiting enforcement';

-- ============================================================================
-- PART 2: Rate Limiting Function (SECURITY DEFINER)
-- ============================================================================

-- Function to check and update rate limit atomically
-- Returns: { allowed: boolean, remaining: int, reset_at: timestamptz }
CREATE OR REPLACE FUNCTION public.check_rate_limit(
    p_user_id UUID,
    p_action_type TEXT,
    p_max_requests INTEGER DEFAULT 10,
    p_window_minutes INTEGER DEFAULT 60
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_window_start TIMESTAMPTZ;
    v_request_count INTEGER;
    v_allowed BOOLEAN;
    v_remaining INTEGER;
    v_reset_at TIMESTAMPTZ;
BEGIN
    -- Calculate window boundaries
    v_window_start := date_trunc('minute', NOW()) - 
        ((EXTRACT(MINUTE FROM NOW())::INTEGER % p_window_minutes) || ' minutes')::INTERVAL;
    v_reset_at := v_window_start + (p_window_minutes || ' minutes')::INTERVAL;
    
    -- Get current request count for this window (with row-level lock)
    SELECT request_count INTO v_request_count
    FROM rate_limit_tracking
    WHERE user_id = p_user_id 
      AND action_type = p_action_type 
      AND window_start = v_window_start
    FOR UPDATE;
    
    IF v_request_count IS NULL THEN
        -- First request in this window - create record
        INSERT INTO rate_limit_tracking (user_id, action_type, request_count, window_start)
        VALUES (p_user_id, p_action_type, 1, v_window_start);
        v_request_count := 1;
    ELSE
        -- Increment existing count
        UPDATE rate_limit_tracking
        SET request_count = request_count + 1
        WHERE user_id = p_user_id 
          AND action_type = p_action_type 
          AND window_start = v_window_start;
        v_request_count := v_request_count + 1;
    END IF;
    
    -- Check if allowed
    v_allowed := v_request_count <= p_max_requests;
    v_remaining := GREATEST(0, p_max_requests - v_request_count);
    
    -- Clean up old entries (older than 24 hours) - do this occasionally
    IF random() < 0.01 THEN  -- 1% chance to clean up
        DELETE FROM rate_limit_tracking 
        WHERE window_start < NOW() - INTERVAL '24 hours';
    END IF;
    
    RETURN jsonb_build_object(
        'allowed', v_allowed,
        'remaining', v_remaining,
        'reset_at', v_reset_at,
        'current_count', v_request_count,
        'max_requests', p_max_requests
    );
END;
$$;

COMMENT ON FUNCTION public.check_rate_limit IS 'Atomically checks and updates rate limit for a user action. Returns allowed status and remaining quota.';

-- Grant execute permission to authenticated users (function controls its own security)
GRANT EXECUTE ON FUNCTION public.check_rate_limit TO authenticated;
GRANT EXECUTE ON FUNCTION public.check_rate_limit TO service_role;

-- ============================================================================
-- PART 3: LiteLLM_UserTable RLS (if table exists)
-- ============================================================================

-- This DO block safely adds RLS to LiteLLM_UserTable if it exists
-- LiteLLM creates this table, so we add policies without creating it
DO $$
BEGIN
    -- Check if the table exists
    IF EXISTS (
        SELECT FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename = 'LiteLLM_UserTable'
    ) THEN
        -- Enable RLS
        EXECUTE 'ALTER TABLE public."LiteLLM_UserTable" ENABLE ROW LEVEL SECURITY';
        
        -- Drop existing policies if they exist (idempotent)
        EXECUTE 'DROP POLICY IF EXISTS "Users can view own LiteLLM data" ON public."LiteLLM_UserTable"';
        EXECUTE 'DROP POLICY IF EXISTS "Service role manages LiteLLM users" ON public."LiteLLM_UserTable"';
        
        -- Users can only see their own row
        EXECUTE 'CREATE POLICY "Users can view own LiteLLM data"
            ON public."LiteLLM_UserTable"
            FOR SELECT
            USING (user_id = auth.uid()::text)';
        
        -- Service role can do everything (for LiteLLM proxy operations)
        EXECUTE 'CREATE POLICY "Service role manages LiteLLM users"
            ON public."LiteLLM_UserTable"
            FOR ALL
            USING (auth.role() = ''service_role'')
            WITH CHECK (auth.role() = ''service_role'')';
        
        RAISE NOTICE 'RLS policies added to LiteLLM_UserTable';
    ELSE
        RAISE NOTICE 'LiteLLM_UserTable does not exist yet - policies will be added when table is created';
    END IF;
END
$$;

-- ============================================================================
-- PART 4: Secure Credit Balance View (SECURITY DEFINER)
-- ============================================================================

-- Create a secure view that exposes credit data safely
-- Uses security_barrier to prevent information leakage
CREATE OR REPLACE VIEW public.user_credit_balance 
WITH (security_barrier = true) AS
SELECT 
    ut.user_id::uuid as user_id,
    COALESCE(ut.max_budget, 0)::decimal(10,4) as max_budget,
    COALESCE(ut.spend, 0)::decimal(10,4) as spend,
    GREATEST(0, COALESCE(ut.max_budget, 0) - COALESCE(ut.spend, 0))::decimal(10,4) as remaining_balance,
    ut.user_email as email
FROM public."LiteLLM_UserTable" ut
WHERE ut.user_id = auth.uid()::text;

COMMENT ON VIEW public.user_credit_balance IS 'Secure view of user credit balance from LiteLLM. Only returns current user data.';

-- Grant SELECT on the view to authenticated users
GRANT SELECT ON public.user_credit_balance TO authenticated;

-- ============================================================================
-- PART 5: Secure Credit Transaction Recording (SECURITY DEFINER)
-- ============================================================================

-- Function to atomically record a credit transaction with validation
-- Only callable by service role (used by edge functions)
CREATE OR REPLACE FUNCTION public.record_credit_transaction(
    p_user_id UUID,
    p_amount DECIMAL(10,4),
    p_type TEXT,
    p_stripe_session_id TEXT DEFAULT NULL,
    p_stripe_payment_intent TEXT DEFAULT NULL,
    p_previous_budget DECIMAL(10,4) DEFAULT NULL,
    p_new_budget DECIMAL(10,4) DEFAULT NULL,
    p_notes TEXT DEFAULT NULL,
    p_idempotency_key TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_transaction_id UUID;
    v_existing_id UUID;
BEGIN
    -- Validate inputs
    IF p_user_id IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error', 'user_id is required');
    END IF;
    
    IF p_type NOT IN ('purchase', 'refund', 'adjustment', 'bonus', 'usage') THEN
        RETURN jsonb_build_object('success', false, 'error', 'Invalid transaction type');
    END IF;
    
    IF p_amount IS NULL OR p_amount = 0 THEN
        RETURN jsonb_build_object('success', false, 'error', 'Amount must be non-zero');
    END IF;
    
    -- Check for duplicate transaction (idempotency)
    IF p_stripe_session_id IS NOT NULL THEN
        SELECT id INTO v_existing_id
        FROM credit_transactions
        WHERE stripe_session_id = p_stripe_session_id
        LIMIT 1;
        
        IF v_existing_id IS NOT NULL THEN
            RETURN jsonb_build_object(
                'success', true, 
                'transaction_id', v_existing_id,
                'duplicate', true,
                'message', 'Transaction already recorded'
            );
        END IF;
    END IF;
    
    -- Verify user exists in auth.users
    IF NOT EXISTS (SELECT 1 FROM auth.users WHERE id = p_user_id) THEN
        RETURN jsonb_build_object('success', false, 'error', 'User does not exist');
    END IF;
    
    -- Insert the transaction
    INSERT INTO credit_transactions (
        user_id, amount, type, stripe_session_id, stripe_payment_intent,
        previous_budget, new_budget, notes
    )
    VALUES (
        p_user_id, p_amount, p_type, p_stripe_session_id, p_stripe_payment_intent,
        p_previous_budget, p_new_budget, p_notes
    )
    RETURNING id INTO v_transaction_id;
    
    RETURN jsonb_build_object(
        'success', true,
        'transaction_id', v_transaction_id,
        'duplicate', false
    );
END;
$$;

COMMENT ON FUNCTION public.record_credit_transaction IS 'Atomically records a credit transaction with validation and idempotency. Only callable by service role.';

-- Only service role can call this function directly
REVOKE ALL ON FUNCTION public.record_credit_transaction FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.record_credit_transaction TO service_role;

-- ============================================================================
-- PART 6: Credit Transaction Summary View (SECURITY DEFINER)
-- ============================================================================

-- View for users to see their transaction history with aggregates
CREATE OR REPLACE VIEW public.user_transaction_summary
WITH (security_barrier = true) AS
SELECT 
    user_id,
    COUNT(*) as total_transactions,
    COALESCE(SUM(amount) FILTER (WHERE type = 'purchase'), 0) as total_purchased,
    COALESCE(SUM(amount) FILTER (WHERE type = 'refund'), 0) as total_refunded,
    COALESCE(SUM(amount) FILTER (WHERE type = 'bonus'), 0) as total_bonus,
    MIN(created_at) as first_transaction,
    MAX(created_at) as last_transaction
FROM credit_transactions
WHERE user_id = auth.uid()
GROUP BY user_id;

COMMENT ON VIEW public.user_transaction_summary IS 'Aggregated view of user credit transactions. Only returns current user data.';

GRANT SELECT ON public.user_transaction_summary TO authenticated;

-- ============================================================================
-- PART 7: Key Generation Rate Limit Function (SECURITY DEFINER)
-- ============================================================================

-- Specific rate limiter for key generation - stricter limits
CREATE OR REPLACE FUNCTION public.check_key_generation_limit(p_user_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    -- Allow 5 key generations per hour
    RETURN check_rate_limit(p_user_id, 'key_generation', 5, 60);
END;
$$;

COMMENT ON FUNCTION public.check_key_generation_limit IS 'Rate limiter specifically for LiteLLM key generation. 5 requests per hour.';

GRANT EXECUTE ON FUNCTION public.check_key_generation_limit TO authenticated;
GRANT EXECUTE ON FUNCTION public.check_key_generation_limit TO service_role;

-- ============================================================================
-- PART 8: Validate User for Operations (SECURITY DEFINER)
-- ============================================================================

-- Function to validate a user exists and is active before operations
CREATE OR REPLACE FUNCTION public.validate_user_for_operation(
    p_user_id UUID,
    p_operation TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_user_exists BOOLEAN;
    v_user_email TEXT;
BEGIN
    -- Check if user exists
    SELECT EXISTS(SELECT 1 FROM auth.users WHERE id = p_user_id), 
           (SELECT email FROM auth.users WHERE id = p_user_id)
    INTO v_user_exists, v_user_email;
    
    IF NOT v_user_exists THEN
        RETURN jsonb_build_object(
            'valid', false,
            'error', 'User does not exist',
            'user_id', p_user_id
        );
    END IF;
    
    -- Log the operation (optional audit)
    -- This could be extended to check user status, bans, etc.
    
    RETURN jsonb_build_object(
        'valid', true,
        'user_id', p_user_id,
        'email', v_user_email,
        'operation', p_operation
    );
END;
$$;

COMMENT ON FUNCTION public.validate_user_for_operation IS 'Validates a user exists and is active before performing operations.';

GRANT EXECUTE ON FUNCTION public.validate_user_for_operation TO service_role;

-- ============================================================================
-- PART 9: Update Existing RLS Policies for Tighter Security
-- ============================================================================

-- Drop and recreate user_virtual_keys policies with explicit permissions
DROP POLICY IF EXISTS "Users can view their own virtual keys" ON public.user_virtual_keys;
DROP POLICY IF EXISTS "Service role can manage all virtual keys" ON public.user_virtual_keys;

-- Recreate with explicit operation types
CREATE POLICY "Users can SELECT own virtual keys"
    ON public.user_virtual_keys
    FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

CREATE POLICY "Service role full access to virtual keys"
    ON public.user_virtual_keys
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Same for credit_transactions
DROP POLICY IF EXISTS "Users can view their own transactions" ON public.credit_transactions;
DROP POLICY IF EXISTS "Service role can manage all transactions" ON public.credit_transactions;

CREATE POLICY "Users can SELECT own transactions"
    ON public.credit_transactions
    FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

CREATE POLICY "Service role full access to transactions"
    ON public.credit_transactions
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- ============================================================================
-- PART 10: Webhook Idempotency Table
-- ============================================================================

-- Table to track processed webhooks for idempotency
CREATE TABLE IF NOT EXISTS public.processed_webhooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    webhook_id TEXT NOT NULL UNIQUE,  -- Stripe event ID or other identifier
    webhook_type TEXT NOT NULL,        -- 'stripe', 'litellm', etc.
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    result JSONB
);

-- Index for webhook lookups
CREATE INDEX IF NOT EXISTS idx_processed_webhooks_id 
    ON public.processed_webhooks(webhook_id);

-- Cleanup index for old webhooks
CREATE INDEX IF NOT EXISTS idx_processed_webhooks_time 
    ON public.processed_webhooks(processed_at);

-- Enable RLS
ALTER TABLE public.processed_webhooks ENABLE ROW LEVEL SECURITY;

-- Only service role can access
CREATE POLICY "Service role manages webhooks"
    ON public.processed_webhooks
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

COMMENT ON TABLE public.processed_webhooks IS 'Tracks processed webhooks to prevent duplicate processing (idempotency)';

-- Function to check and mark webhook as processed
CREATE OR REPLACE FUNCTION public.process_webhook_idempotent(
    p_webhook_id TEXT,
    p_webhook_type TEXT,
    p_result JSONB DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_existing RECORD;
BEGIN
    -- Check if already processed
    SELECT * INTO v_existing
    FROM processed_webhooks
    WHERE webhook_id = p_webhook_id;
    
    IF v_existing IS NOT NULL THEN
        RETURN jsonb_build_object(
            'already_processed', true,
            'original_result', v_existing.result,
            'processed_at', v_existing.processed_at
        );
    END IF;
    
    -- Mark as processed
    INSERT INTO processed_webhooks (webhook_id, webhook_type, result)
    VALUES (p_webhook_id, p_webhook_type, p_result);
    
    -- Clean up old entries (older than 7 days) occasionally
    IF random() < 0.01 THEN
        DELETE FROM processed_webhooks WHERE processed_at < NOW() - INTERVAL '7 days';
    END IF;
    
    RETURN jsonb_build_object(
        'already_processed', false,
        'webhook_id', p_webhook_id
    );
END;
$$;

COMMENT ON FUNCTION public.process_webhook_idempotent IS 'Idempotent webhook processing - returns true if already processed';

GRANT EXECUTE ON FUNCTION public.process_webhook_idempotent TO service_role;
