-- Migration: Secure remaining LiteLLM Proxy tables
-- Enables RLS on internal LiteLLM tables to prevent unauthorized access
-- 
-- Tables secured:
-- 1. LiteLLM_VerificationTokenTable (Stores API keys)
-- 2. LiteLLM_SpendLogs (Stores request logs)
-- 3. LiteLLM_Config (Stores proxy config)
-- 4. LiteLLM_TeamTable (Stores team data)
-- 5. LiteLLM_OrganizationTable (Stores org data)

DO $$
DECLARE
    t text;
    tables text[] := ARRAY[
        'LiteLLM_VerificationTokenTable',
        'LiteLLM_SpendLogs',
        'LiteLLM_Config',
        'LiteLLM_TeamTable',
        'LiteLLM_OrganizationTable'
    ];
BEGIN
    FOREACH t IN ARRAY tables
    LOOP
        -- Check if table exists
        IF EXISTS (
            SELECT FROM pg_tables 
            WHERE schemaname = 'public' 
            AND tablename = t
        ) THEN
            -- Enable RLS
            EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
            
            -- Drop existing policies to ensure clean slate
            EXECUTE format('DROP POLICY IF EXISTS "Service role full access" ON public.%I', t);
            EXECUTE format('DROP POLICY IF EXISTS "Allow service role" ON public.%I', t);
            
            -- Create Service Role policy (Full Access)
            EXECUTE format('CREATE POLICY "Service role full access"
                ON public.%I
                FOR ALL
                TO service_role
                USING (true)
                WITH CHECK (true)', t);
                
            RAISE NOTICE 'Secured table: %', t;
        ELSE
            RAISE NOTICE 'Table not found (skipping): %', t;
        END IF;
    END LOOP;
END
$$;
