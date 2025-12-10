-- Migration: Enable Vault and create secure key retrieval RPC
-- secure_api_keys.sql

-- 1. Enable Supabase Vault extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA vault;

-- 2. Create RPC to retrieve OpenRouter API Key
-- This allows the Edge Function (which runs as 'anon' but signed with a Service Key typically,
-- but we want to be explicit. Actually, for `chat-proxy` we use the Service Key to call this RPC
-- OR we can allow the function to call it if it's SECURITY DEFINER.
-- However, standard practice: modifying chat-proxy to use Service Role key for this call is safest,
-- but let's make a SECURITY DEFINER function that only allows specific roles if needed.
-- For simplicity and following the "Smart Vault" pattern:
CREATE OR REPLACE FUNCTION get_openrouter_key()
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER -- Runs as database owner
SET search_path = public, vault -- Set search path for safety
AS $$
DECLARE
    secret_value TEXT;
BEGIN
    -- Check if we are running in a verified context if needed.
    -- For now, we rely on the fact that only the Edge Function (using Service Role) 
    -- or authenticated users (via RLS if we opened it, but we won't) can access this if we restrict it.
    -- Actually, by default SECURITY DEFINER functions are executable by public.
    -- WE MUST REVOKE EXECUTE FROM PUBLIC to be safe, only allowing Service Role.
    
    SELECT decrypted_secret INTO secret_value
    FROM vault.decrypted_secrets
    WHERE name = 'openrouter_api_key'
    LIMIT 1;

    RETURN secret_value;
END;
$$;

-- 3. Secure the Function: Only allow Service Role to execute it
REVOKE EXECUTE ON FUNCTION get_openrouter_key() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION get_openrouter_key() FROM anon;
REVOKE EXECUTE ON FUNCTION get_openrouter_key() FROM authenticated;
-- Grant execute to service_role (postgres role 'service_role' in Supabase)
GRANT EXECUTE ON FUNCTION get_openrouter_key() TO service_role;

-- 4. Comment/Instruction
COMMENT ON FUNCTION get_openrouter_key IS 'Retrieves the OpenRouter API key from Supabase Vault. Accessible only by service_role.';
