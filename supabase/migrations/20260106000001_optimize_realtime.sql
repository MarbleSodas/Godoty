-- Migration: Optimize Realtime Configuration
-- 
-- The client only needs realtime updates for LiteLLM_UserTable (balance changes).
-- While credit_transactions provides audit logs, the balance update on LiteLLM_UserTable
-- is sufficient for the UI and reduces realtime noise/cost.
--
-- Changes:
-- 1. Remove credit_transactions from supabase_realtime publication
-- 2. Ensure LiteLLM_UserTable remains in publication
-- 3. Verify RLS policies are correct for LiteLLM_UserTable

-- ============================================================================
-- Step 1: Remove credit_transactions from publication
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT FROM pg_publication_tables 
        WHERE pubname = 'supabase_realtime' 
        AND schemaname = 'public' 
        AND tablename = 'credit_transactions'
    ) THEN
        ALTER PUBLICATION supabase_realtime DROP TABLE public.credit_transactions;
        RAISE NOTICE 'Removed credit_transactions from supabase_realtime publication';
    END IF;
END
$$;

-- ============================================================================
-- Step 2: Ensure LiteLLM_UserTable is in publication
-- ============================================================================

DO $$
BEGIN
    -- Check if LiteLLM_UserTable exists
    IF EXISTS (
        SELECT FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename = 'LiteLLM_UserTable'
    ) THEN
        -- Make sure it has REPLICA IDENTITY FULL (needed for proper updates)
        ALTER TABLE public."LiteLLM_UserTable" REPLICA IDENTITY FULL;
        
        -- Add to publication if not already present
        IF NOT EXISTS (
            SELECT FROM pg_publication_tables 
            WHERE pubname = 'supabase_realtime' 
            AND schemaname = 'public' 
            AND tablename = 'LiteLLM_UserTable'
        ) THEN
            ALTER PUBLICATION supabase_realtime ADD TABLE public."LiteLLM_UserTable";
            RAISE NOTICE 'Added LiteLLM_UserTable to supabase_realtime publication';
        ELSE
             RAISE NOTICE 'LiteLLM_UserTable is already in supabase_realtime publication';
        END IF;
    END IF;
END
$$;

-- ============================================================================
-- Step 3: Explicitly exclude other LiteLLM tables from realtime
-- (Safety measure in case they were added by default)
-- ============================================================================

DO $$
DECLARE
    t text;
    tables text[] := ARRAY[
        'LiteLLM_VerificationTokenTable',
        'LiteLLM_SpendLogs',
        'LiteLLM_Config',
        'LiteLLM_TeamTable',
        'LiteLLM_OrganizationTable',
        'LiteLLM_BudgetTable',
        'LiteLLM_ProxyModelTable',
        'LiteLLM_InvitationLink',
        'LiteLLM_AuditLog',
        'user_virtual_keys',
        'rate_limit_tracking',
        'processed_webhooks'
    ];
BEGIN
    FOREACH t IN ARRAY tables
    LOOP
        IF EXISTS (
            SELECT FROM pg_publication_tables 
            WHERE pubname = 'supabase_realtime' 
            AND schemaname = 'public' 
            AND tablename = t
        ) THEN
            EXECUTE format('ALTER PUBLICATION supabase_realtime DROP TABLE public.%I', t);
            RAISE NOTICE 'Removed % from supabase_realtime publication', t;
        END IF;
    END LOOP;
END
$$;
