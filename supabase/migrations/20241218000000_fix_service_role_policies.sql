-- Migration: Fix service_role RLS policies
-- The previous policies used auth.role() = 'service_role' which doesn't work
-- correctly with service_role key in edge functions. The correct pattern is
-- TO service_role USING (true) WITH CHECK (true).

-- ============================================================================
-- Fix rate_limit_tracking policy
-- ============================================================================
DROP POLICY IF EXISTS "Service role manages rate limits" ON public.rate_limit_tracking;

CREATE POLICY "Service role manages rate limits"
    ON public.rate_limit_tracking
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- ============================================================================
-- Fix LiteLLM_UserTable policy
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename = 'LiteLLM_UserTable'
    ) THEN
        -- Drop the old policy with incorrect pattern
        EXECUTE 'DROP POLICY IF EXISTS "Service role manages LiteLLM users" ON public."LiteLLM_UserTable"';
        
        -- Create policy with correct pattern
        EXECUTE 'CREATE POLICY "Service role manages LiteLLM users"
            ON public."LiteLLM_UserTable"
            FOR ALL
            TO service_role
            USING (true)
            WITH CHECK (true)';
        
        -- Also fix the user SELECT policy if it exists with wrong pattern
        EXECUTE 'DROP POLICY IF EXISTS "Users can SELECT own LiteLLM data" ON public."LiteLLM_UserTable"';
        EXECUTE 'CREATE POLICY "Users can SELECT own LiteLLM data"
            ON public."LiteLLM_UserTable"
            FOR SELECT
            TO authenticated
            USING (user_id = auth.uid()::text)';
    END IF;
END
$$;

-- ============================================================================
-- Fix LiteLLM_VerificationTokenTable policy (ensure consistency)
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename = 'LiteLLM_VerificationTokenTable'
    ) THEN
        EXECUTE 'DROP POLICY IF EXISTS "Service role full access" ON public."LiteLLM_VerificationTokenTable"';
        EXECUTE 'CREATE POLICY "Service role full access"
            ON public."LiteLLM_VerificationTokenTable"
            FOR ALL
            TO service_role
            USING (true)
            WITH CHECK (true)';
    END IF;
END
$$;

-- ============================================================================
-- Fix LiteLLM_SpendLogs policy (ensure consistency)
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename = 'LiteLLM_SpendLogs'
    ) THEN
        EXECUTE 'DROP POLICY IF EXISTS "Service role full access" ON public."LiteLLM_SpendLogs"';
        EXECUTE 'CREATE POLICY "Service role full access"
            ON public."LiteLLM_SpendLogs"
            FOR ALL
            TO service_role
            USING (true)
            WITH CHECK (true)';
    END IF;
END
$$;

-- ============================================================================
-- Fix LiteLLM_Config policy (ensure consistency)
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename = 'LiteLLM_Config'
    ) THEN
        EXECUTE 'DROP POLICY IF EXISTS "Service role full access" ON public."LiteLLM_Config"';
        EXECUTE 'CREATE POLICY "Service role full access"
            ON public."LiteLLM_Config"
            FOR ALL
            TO service_role
            USING (true)
            WITH CHECK (true)';
    END IF;
END
$$;

-- ============================================================================
-- Fix LiteLLM_TeamTable policy (ensure consistency)
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename = 'LiteLLM_TeamTable'
    ) THEN
        EXECUTE 'DROP POLICY IF EXISTS "Service role full access" ON public."LiteLLM_TeamTable"';
        EXECUTE 'CREATE POLICY "Service role full access"
            ON public."LiteLLM_TeamTable"
            FOR ALL
            TO service_role
            USING (true)
            WITH CHECK (true)';
    END IF;
END
$$;

-- ============================================================================
-- Fix LiteLLM_OrganizationTable policy (ensure consistency)
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename = 'LiteLLM_OrganizationTable'
    ) THEN
        EXECUTE 'DROP POLICY IF EXISTS "Service role full access" ON public."LiteLLM_OrganizationTable"';
        EXECUTE 'CREATE POLICY "Service role full access"
            ON public."LiteLLM_OrganizationTable"
            FOR ALL
            TO service_role
            USING (true)
            WITH CHECK (true)';
    END IF;
END
$$;

-- ============================================================================
-- Make user_credit_balance view more resilient
-- Recreate view with COALESCE to handle missing data gracefully
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename = 'LiteLLM_UserTable'
    ) THEN
        -- Drop existing view
        DROP VIEW IF EXISTS public.user_credit_balance;
        
        -- Recreate with security_barrier and better null handling
        EXECUTE '
        CREATE VIEW public.user_credit_balance 
        WITH (security_barrier = true) AS
        SELECT 
            ut.user_id::uuid as user_id,
            COALESCE(ut.max_budget, 0)::numeric(10,2) as total_credits,
            COALESCE(ut.spend, 0)::numeric(10,2) as used_credits,
            COALESCE(ut.max_budget - ut.spend, 0)::numeric(10,2) as remaining_credits,
            ut.budget_reset_at as next_reset
        FROM public."LiteLLM_UserTable" ut
        WHERE ut.user_id = auth.uid()::text';
        
        -- Grant access
        GRANT SELECT ON public.user_credit_balance TO authenticated;
    END IF;
END
$$;

-- ============================================================================
-- Ensure processed_webhooks policy is correct
-- ============================================================================
DROP POLICY IF EXISTS "Service role manages webhooks" ON public.processed_webhooks;

CREATE POLICY "Service role manages webhooks"
    ON public.processed_webhooks
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- ============================================================================
-- Summary of changes:
-- 1. Fixed rate_limit_tracking policy to use TO service_role pattern
-- 2. Fixed all LiteLLM_* table policies to use consistent TO service_role pattern
-- 3. Made user_credit_balance view more resilient with COALESCE
-- 4. Ensured processed_webhooks policy uses correct pattern
-- ============================================================================
