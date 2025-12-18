-- Migration: Grant postgres role access to LiteLLM tables
-- 
-- PROBLEM: The LiteLLM proxy connects to PostgreSQL using DATABASE_URL which
-- authenticates as the 'postgres' role. When RLS was enabled on LiteLLM tables
-- in migration 20241217120000, policies were only created for 'service_role'.
-- This caused the LiteLLM proxy to get 500 errors when trying to generate keys.
--
-- SOLUTION: Add RLS policies granting the 'postgres' role full access to all
-- LiteLLM-managed tables. The postgres role is a superuser, but explicit policies
-- ensure consistent behavior regardless of RLS force settings.

-- ============================================================================
-- Grant postgres role access to all LiteLLM tables
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
        'LiteLLM_UserTable'
    ];
BEGIN
    FOREACH t IN ARRAY tables
    LOOP
        IF EXISTS (
            SELECT FROM pg_tables 
            WHERE schemaname = 'public' 
            AND tablename = t
        ) THEN
            -- Drop existing postgres policy if it exists (idempotent)
            EXECUTE format('DROP POLICY IF EXISTS "Postgres role full access" ON public.%I', t);
            
            -- Create policy granting postgres role full access
            EXECUTE format('CREATE POLICY "Postgres role full access"
                ON public.%I
                FOR ALL
                TO postgres
                USING (true)
                WITH CHECK (true)', t);
                
            RAISE NOTICE 'Granted postgres access to: %', t;
        ELSE
            RAISE NOTICE 'Table not found (skipping): %', t;
        END IF;
    END LOOP;
END
$$;

-- ============================================================================
-- Also ensure the authenticator role has access (used by Supabase connection pooler)
-- This covers cases where connections come through Supavisor
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
        'LiteLLM_UserTable'
    ];
BEGIN
    FOREACH t IN ARRAY tables
    LOOP
        IF EXISTS (
            SELECT FROM pg_tables 
            WHERE schemaname = 'public' 
            AND tablename = t
        ) THEN
            -- Drop existing authenticator policy if it exists (idempotent)
            EXECUTE format('DROP POLICY IF EXISTS "Authenticator role full access" ON public.%I', t);
            
            -- Create policy granting authenticator role full access
            -- The authenticator role is used by Supabase's connection pooler
            EXECUTE format('CREATE POLICY "Authenticator role full access"
                ON public.%I
                FOR ALL
                TO authenticator
                USING (true)
                WITH CHECK (true)', t);
                
            RAISE NOTICE 'Granted authenticator access to: %', t;
        ELSE
            RAISE NOTICE 'Table not found (skipping): %', t;
        END IF;
    END LOOP;
END
$$;

-- ============================================================================
-- Summary of changes:
-- 1. Added "Postgres role full access" policy to all LiteLLM tables
-- 2. Added "Authenticator role full access" policy for connection pooler support
-- 
-- After this migration, LiteLLM tables will have these policies:
-- - "Service role full access" (from 20241217120000)
-- - "Postgres role full access" (this migration)
-- - "Authenticator role full access" (this migration)
-- ============================================================================
