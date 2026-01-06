-- Migration: Consolidated Security Measures
-- 
-- This migration consolidates all security measures into a single, well-organized file.
-- It ensures proper RLS policies, removes redundancies, and applies security best practices.
--
-- Components Used:
-- 1. user_virtual_keys - Key caching for LiteLLM (edge function: generate-litellm-key)
-- 2. credit_transactions - Audit log of credit purchases (edge function: stripe-webhook)
-- 3. processed_webhooks - Idempotency for webhooks (edge function: stripe-webhook)
-- 4. rate_limit_tracking - Rate limiting (edge function: generate-litellm-key)
-- 5. LiteLLM_* tables - Managed by LiteLLM proxy (realtime: desktop app)
--
-- Security Principles Applied:
-- - Principle of least privilege for all tables
-- - Service role for all write operations from edge functions
-- - Authenticated users can only SELECT their own data
-- - SECURITY DEFINER functions for atomic operations
-- - Rate limiting to prevent abuse
-- - Webhook idempotency to prevent replay attacks

-- ============================================================================
-- PART 1: Clean up any duplicate or conflicting policies
-- ============================================================================

-- Drop potentially conflicting policies from previous migrations
-- user_virtual_keys
DROP POLICY IF EXISTS "Users can view their own virtual keys" ON public.user_virtual_keys;
DROP POLICY IF EXISTS "Service role can manage all virtual keys" ON public.user_virtual_keys;
DROP POLICY IF EXISTS "Users can SELECT own virtual keys" ON public.user_virtual_keys;
DROP POLICY IF EXISTS "Service role full access to virtual keys" ON public.user_virtual_keys;

-- credit_transactions
DROP POLICY IF EXISTS "Users can view their own transactions" ON public.credit_transactions;
DROP POLICY IF EXISTS "Service role can manage all transactions" ON public.credit_transactions;
DROP POLICY IF EXISTS "Users can SELECT own transactions" ON public.credit_transactions;
DROP POLICY IF EXISTS "Service role full access to transactions" ON public.credit_transactions;

-- rate_limit_tracking
DROP POLICY IF EXISTS "Service role manages rate limits" ON public.rate_limit_tracking;

-- processed_webhooks
DROP POLICY IF EXISTS "Service role manages webhooks" ON public.processed_webhooks;

-- ============================================================================
-- PART 2: Ensure RLS is enabled on all application tables
-- ============================================================================

ALTER TABLE IF EXISTS public.user_virtual_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.credit_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.rate_limit_tracking ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.processed_webhooks ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- PART 3: Create proper RLS policies for application tables
-- ============================================================================

-- user_virtual_keys: Users can only view their own keys, service role manages all
CREATE POLICY "user_virtual_keys_select_own"
    ON public.user_virtual_keys
    FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

CREATE POLICY "user_virtual_keys_service_role"
    ON public.user_virtual_keys
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- credit_transactions: Users can only view their own, service role manages all
CREATE POLICY "credit_transactions_select_own"
    ON public.credit_transactions
    FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

CREATE POLICY "credit_transactions_service_role"
    ON public.credit_transactions
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- rate_limit_tracking: Only service role can access
CREATE POLICY "rate_limit_tracking_service_role"
    ON public.rate_limit_tracking
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- processed_webhooks: Only service role can access
CREATE POLICY "processed_webhooks_service_role"
    ON public.processed_webhooks
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- ============================================================================
-- PART 4: Secure LiteLLM-managed tables (created by LiteLLM proxy)
-- ============================================================================
-- 
-- LiteLLM proxy connects to PostgreSQL using DATABASE_URL which authenticates
-- as the 'postgres' role. Supabase's connection pooler (Supavisor) uses the
-- 'authenticator' role. Both need full access to LiteLLM tables.
--
-- Tables managed by LiteLLM:
-- - LiteLLM_UserTable: User budgets and spend tracking
-- - LiteLLM_VerificationTokenTable: API key storage
-- - LiteLLM_SpendLogs: Request logging and cost tracking
-- - LiteLLM_Config: Proxy configuration
-- - LiteLLM_TeamTable: Team management (if using teams)
-- - LiteLLM_OrganizationTable: Organization management (if using orgs)
-- - LiteLLM_BudgetTable: Budget configurations
-- - LiteLLM_ProxyModelTable: Model configurations
-- - LiteLLM_InvitationLink: Team invitation links
-- - LiteLLM_AuditLog: Audit logging

DO $$
DECLARE
    litellm_table TEXT;
    litellm_tables TEXT[] := ARRAY[
        'LiteLLM_UserTable',
        'LiteLLM_VerificationTokenTable',
        'LiteLLM_SpendLogs',
        'LiteLLM_Config',
        'LiteLLM_TeamTable',
        'LiteLLM_OrganizationTable',
        'LiteLLM_BudgetTable',
        'LiteLLM_ProxyModelTable',
        'LiteLLM_InvitationLink',
        'LiteLLM_AuditLog'
    ];
BEGIN
    FOREACH litellm_table IN ARRAY litellm_tables
    LOOP
        IF EXISTS (
            SELECT FROM pg_tables 
            WHERE schemaname = 'public' 
            AND tablename = litellm_table
        ) THEN
            -- Enable RLS
            EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', litellm_table);
            
            -- Drop existing policies (clean slate)
            EXECUTE format('DROP POLICY IF EXISTS "Users can view own LiteLLM data" ON public.%I', litellm_table);
            EXECUTE format('DROP POLICY IF EXISTS "Users can SELECT own LiteLLM data" ON public.%I', litellm_table);
            EXECUTE format('DROP POLICY IF EXISTS "Service role manages LiteLLM users" ON public.%I', litellm_table);
            EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON public.%I', litellm_table);
            EXECUTE format('DROP POLICY IF EXISTS "Postgres role full access" ON public.%I', litellm_table);
            EXECUTE format('DROP POLICY IF EXISTS "Authenticator role full access" ON public.%I', litellm_table);
            EXECUTE format('DROP POLICY IF EXISTS "Authenticated users can view own budget" ON public.%I', litellm_table);
            EXECUTE format('DROP POLICY IF EXISTS "litellm_service_role" ON public.%I', litellm_table);
            EXECUTE format('DROP POLICY IF EXISTS "litellm_postgres_role" ON public.%I', litellm_table);
            EXECUTE format('DROP POLICY IF EXISTS "litellm_authenticator_role" ON public.%I', litellm_table);
            EXECUTE format('DROP POLICY IF EXISTS "litellm_user_select" ON public.%I', litellm_table);
            
            -- Service role full access (for Supabase edge functions)
            EXECUTE format('CREATE POLICY "litellm_service_role"
                ON public.%I
                FOR ALL
                TO service_role
                USING (true)
                WITH CHECK (true)', litellm_table);
            
            -- Postgres role full access (for LiteLLM proxy using DATABASE_URL directly)
            EXECUTE format('CREATE POLICY "litellm_postgres_role"
                ON public.%I
                FOR ALL
                TO postgres
                USING (true)
                WITH CHECK (true)', litellm_table);
            
            -- Authenticator role full access (for LiteLLM proxy via Supavisor connection pooler)
            EXECUTE format('CREATE POLICY "litellm_authenticator_role"
                ON public.%I
                FOR ALL
                TO authenticator
                USING (true)
                WITH CHECK (true)', litellm_table);
            
            RAISE NOTICE 'Secured LiteLLM table: %', litellm_table;
        ELSE
            RAISE NOTICE 'LiteLLM table not found (will be created by proxy): %', litellm_table;
        END IF;
    END LOOP;
END
$$;

-- Special handling for LiteLLM_UserTable: authenticated users can SELECT their own row
-- This is needed for Realtime subscriptions in the desktop app
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename = 'LiteLLM_UserTable'
    ) THEN
        -- Users can view their own budget data (for Realtime)
        EXECUTE 'CREATE POLICY "litellm_user_select"
            ON public."LiteLLM_UserTable"
            FOR SELECT
            TO authenticated
            USING (user_id = auth.uid()::text)';
        
        RAISE NOTICE 'Added authenticated SELECT policy to LiteLLM_UserTable';
    END IF;
END
$$;

-- ============================================================================
-- PART 5: Ensure secure views exist with security_barrier
-- ============================================================================

-- Drop and recreate user_credit_balance view
DROP VIEW IF EXISTS public.user_credit_balance;

DO $$
BEGIN
    IF EXISTS (
        SELECT FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename = 'LiteLLM_UserTable'
    ) THEN
        EXECUTE '
        CREATE VIEW public.user_credit_balance 
        WITH (security_barrier = true) AS
        SELECT 
            ut.user_id::uuid as user_id,
            COALESCE(ut.max_budget, 0)::numeric(10,4) as total_credits,
            COALESCE(ut.spend, 0)::numeric(10,4) as used_credits,
            GREATEST(0, COALESCE(ut.max_budget, 0) - COALESCE(ut.spend, 0))::numeric(10,4) as remaining_credits,
            ut.budget_reset_at as next_reset
        FROM public."LiteLLM_UserTable" ut
        WHERE ut.user_id = auth.uid()::text';
        
        GRANT SELECT ON public.user_credit_balance TO authenticated;
        
        RAISE NOTICE 'Created user_credit_balance view';
    END IF;
END
$$;

-- Drop and recreate user_transaction_summary view
DROP VIEW IF EXISTS public.user_transaction_summary;

CREATE VIEW public.user_transaction_summary
WITH (security_barrier = true) AS
SELECT 
    user_id,
    COUNT(*) as total_transactions,
    COALESCE(SUM(amount) FILTER (WHERE type = 'purchase'), 0) as total_purchased,
    COALESCE(SUM(amount) FILTER (WHERE type = 'refund'), 0) as total_refunded,
    COALESCE(SUM(amount) FILTER (WHERE type = 'bonus'), 0) as total_bonus,
    MIN(created_at) as first_transaction,
    MAX(created_at) as last_transaction
FROM public.credit_transactions
WHERE user_id = auth.uid()
GROUP BY user_id;

GRANT SELECT ON public.user_transaction_summary TO authenticated;

-- ============================================================================
-- PART 6: Ensure SECURITY DEFINER functions are properly secured
-- ============================================================================

-- Revoke public access to sensitive functions (ensure only service_role can call)
DO $$
BEGIN
    -- These functions should only be callable by service_role
    IF EXISTS (SELECT FROM pg_proc WHERE proname = 'record_credit_transaction') THEN
        REVOKE ALL ON FUNCTION public.record_credit_transaction FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.record_credit_transaction FROM authenticated;
        GRANT EXECUTE ON FUNCTION public.record_credit_transaction TO service_role;
    END IF;
    
    IF EXISTS (SELECT FROM pg_proc WHERE proname = 'process_webhook_idempotent') THEN
        REVOKE ALL ON FUNCTION public.process_webhook_idempotent FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.process_webhook_idempotent FROM authenticated;
        GRANT EXECUTE ON FUNCTION public.process_webhook_idempotent TO service_role;
    END IF;
    
    IF EXISTS (SELECT FROM pg_proc WHERE proname = 'validate_user_for_operation') THEN
        REVOKE ALL ON FUNCTION public.validate_user_for_operation FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.validate_user_for_operation FROM authenticated;
        GRANT EXECUTE ON FUNCTION public.validate_user_for_operation TO service_role;
    END IF;
    
    -- These functions can be called by authenticated users (rate limiting checks)
    IF EXISTS (SELECT FROM pg_proc WHERE proname = 'check_rate_limit') THEN
        REVOKE ALL ON FUNCTION public.check_rate_limit FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION public.check_rate_limit TO authenticated;
        GRANT EXECUTE ON FUNCTION public.check_rate_limit TO service_role;
    END IF;
    
    IF EXISTS (SELECT FROM pg_proc WHERE proname = 'check_key_generation_limit') THEN
        REVOKE ALL ON FUNCTION public.check_key_generation_limit FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION public.check_key_generation_limit TO authenticated;
        GRANT EXECUTE ON FUNCTION public.check_key_generation_limit TO service_role;
    END IF;
END
$$;

-- ============================================================================
-- PART 7: Ensure Realtime publication includes needed tables
-- ============================================================================

DO $$
BEGIN
    -- Ensure supabase_realtime publication exists
    IF NOT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
        CREATE PUBLICATION supabase_realtime;
    END IF;
END
$$;

-- Add LiteLLM_UserTable to realtime publication (for balance updates)
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename = 'LiteLLM_UserTable'
    ) THEN
        -- Set REPLICA IDENTITY to FULL for proper old/new row data
        ALTER TABLE public."LiteLLM_UserTable" REPLICA IDENTITY FULL;
        
        BEGIN
            ALTER PUBLICATION supabase_realtime ADD TABLE public."LiteLLM_UserTable";
        EXCEPTION WHEN duplicate_object THEN
            RAISE NOTICE 'LiteLLM_UserTable already in publication';
        END;
    END IF;
END
$$;

-- Add credit_transactions to realtime publication (for purchase notifications)
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename = 'credit_transactions'
    ) THEN
        ALTER TABLE public.credit_transactions REPLICA IDENTITY FULL;
        
        BEGIN
            ALTER PUBLICATION supabase_realtime ADD TABLE public.credit_transactions;
        EXCEPTION WHEN duplicate_object THEN
            RAISE NOTICE 'credit_transactions already in publication';
        END;
    END IF;
END
$$;

-- ============================================================================
-- PART 8: Cleanup - Remove any stale/orphaned policies
-- ============================================================================

-- This section ensures no orphaned policies exist from previous migrations
-- by re-checking all expected policies are in place

DO $$
DECLARE
    policy_count INTEGER;
BEGIN
    -- Verify user_virtual_keys has exactly 2 policies
    SELECT COUNT(*) INTO policy_count
    FROM pg_policies 
    WHERE schemaname = 'public' AND tablename = 'user_virtual_keys';
    
    IF policy_count != 2 THEN
        RAISE NOTICE 'user_virtual_keys has % policies (expected 2)', policy_count;
    END IF;
    
    -- Verify credit_transactions has exactly 2 policies
    SELECT COUNT(*) INTO policy_count
    FROM pg_policies 
    WHERE schemaname = 'public' AND tablename = 'credit_transactions';
    
    IF policy_count != 2 THEN
        RAISE NOTICE 'credit_transactions has % policies (expected 2)', policy_count;
    END IF;
    
    -- Verify rate_limit_tracking has exactly 1 policy
    SELECT COUNT(*) INTO policy_count
    FROM pg_policies 
    WHERE schemaname = 'public' AND tablename = 'rate_limit_tracking';
    
    IF policy_count != 1 THEN
        RAISE NOTICE 'rate_limit_tracking has % policies (expected 1)', policy_count;
    END IF;
    
    -- Verify processed_webhooks has exactly 1 policy
    SELECT COUNT(*) INTO policy_count
    FROM pg_policies 
    WHERE schemaname = 'public' AND tablename = 'processed_webhooks';
    
    IF policy_count != 1 THEN
        RAISE NOTICE 'processed_webhooks has % policies (expected 1)', policy_count;
    END IF;
END
$$;

-- ============================================================================
-- SUMMARY OF SECURITY MEASURES
-- ============================================================================
-- 
-- Tables with RLS:
-- ┌─────────────────────────────┬─────────────────────────────────────────────┐
-- │ Table                       │ Policies                                    │
-- ├─────────────────────────────┼─────────────────────────────────────────────┤
-- │ user_virtual_keys           │ authenticated: SELECT own                   │
-- │                             │ service_role: ALL                           │
-- ├─────────────────────────────┼─────────────────────────────────────────────┤
-- │ credit_transactions         │ authenticated: SELECT own                   │
-- │                             │ service_role: ALL                           │
-- ├─────────────────────────────┼─────────────────────────────────────────────┤
-- │ rate_limit_tracking         │ service_role: ALL                           │
-- ├─────────────────────────────┼─────────────────────────────────────────────┤
-- │ processed_webhooks          │ service_role: ALL                           │
-- ├─────────────────────────────┼─────────────────────────────────────────────┤
-- │ LiteLLM_UserTable           │ authenticated: SELECT own (for Realtime)    │
-- │                             │ service_role: ALL                           │
-- │                             │ postgres: ALL (direct DATABASE_URL)         │
-- │                             │ authenticator: ALL (Supavisor pooler)       │
-- ├─────────────────────────────┼─────────────────────────────────────────────┤
-- │ LiteLLM_VerificationTokenTable │ service_role: ALL                        │
-- │                             │ postgres: ALL                               │
-- │                             │ authenticator: ALL                          │
-- ├─────────────────────────────┼─────────────────────────────────────────────┤
-- │ LiteLLM_SpendLogs           │ service_role: ALL                           │
-- │                             │ postgres: ALL                               │
-- │                             │ authenticator: ALL                          │
-- ├─────────────────────────────┼─────────────────────────────────────────────┤
-- │ LiteLLM_Config              │ service_role: ALL                           │
-- │                             │ postgres: ALL                               │
-- │                             │ authenticator: ALL                          │
-- ├─────────────────────────────┼─────────────────────────────────────────────┤
-- │ LiteLLM_TeamTable           │ service_role: ALL                           │
-- │                             │ postgres: ALL                               │
-- │                             │ authenticator: ALL                          │
-- ├─────────────────────────────┼─────────────────────────────────────────────┤
-- │ LiteLLM_OrganizationTable   │ service_role: ALL                           │
-- │                             │ postgres: ALL                               │
-- │                             │ authenticator: ALL                          │
-- ├─────────────────────────────┼─────────────────────────────────────────────┤
-- │ LiteLLM_BudgetTable         │ service_role: ALL                           │
-- │                             │ postgres: ALL                               │
-- │                             │ authenticator: ALL                          │
-- ├─────────────────────────────┼─────────────────────────────────────────────┤
-- │ LiteLLM_ProxyModelTable     │ service_role: ALL                           │
-- │                             │ postgres: ALL                               │
-- │                             │ authenticator: ALL                          │
-- ├─────────────────────────────┼─────────────────────────────────────────────┤
-- │ LiteLLM_InvitationLink      │ service_role: ALL                           │
-- │                             │ postgres: ALL                               │
-- │                             │ authenticator: ALL                          │
-- ├─────────────────────────────┼─────────────────────────────────────────────┤
-- │ LiteLLM_AuditLog            │ service_role: ALL                           │
-- │                             │ postgres: ALL                               │
-- │                             │ authenticator: ALL                          │
-- └─────────────────────────────┴─────────────────────────────────────────────┘
--
-- LiteLLM Proxy Access:
-- The LiteLLM proxy needs full access to its tables. Access is granted via:
-- 1. postgres role - Direct DATABASE_URL connection
-- 2. authenticator role - Supavisor connection pooler (pooled connections)
-- 3. service_role - Supabase edge functions using service key
--
-- Secure Views:
-- - user_credit_balance: WITH (security_barrier = true), filtered by auth.uid()
-- - user_transaction_summary: WITH (security_barrier = true), filtered by auth.uid()
--
-- SECURITY DEFINER Functions:
-- - record_credit_transaction: service_role only
-- - process_webhook_idempotent: service_role only  
-- - validate_user_for_operation: service_role only
-- - check_rate_limit: authenticated + service_role
-- - check_key_generation_limit: authenticated + service_role
--
-- Realtime:
-- - LiteLLM_UserTable: For balance updates in desktop app
-- - credit_transactions: For purchase notifications in desktop app
-- ============================================================================
