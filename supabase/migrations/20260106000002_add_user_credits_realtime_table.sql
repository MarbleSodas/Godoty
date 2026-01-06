-- Migration: Add user_credits table for robust Realtime synchronization
-- 
-- This migration creates a dedicated table for user credits that syncs with 
-- LiteLLM_UserTable via triggers. This provides a more reliable source for 
-- Supabase Realtime than views or proxy-managed tables.

-- ============================================================================
-- Step 1: Create user_credits table
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.user_credits (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    balance NUMERIC(15, 4) DEFAULT 0 NOT NULL,
    max_budget NUMERIC(15, 4) DEFAULT 0 NOT NULL,
    total_spent NUMERIC(15, 4) DEFAULT 0 NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
);

-- Enable RLS
ALTER TABLE public.user_credits ENABLE ROW LEVEL SECURITY;

-- Add comment
COMMENT ON TABLE public.user_credits IS 'Synchronized credit balances for frontend Realtime updates.';

-- ============================================================================
-- Step 2: Create RLS policies
-- ============================================================================

-- Users can select their own credits
CREATE POLICY "user_credits_select_own" 
    ON public.user_credits 
    FOR SELECT 
    TO authenticated 
    USING (auth.uid() = user_id);

-- Service role can manage all (used by triggers and edge functions)
CREATE POLICY "user_credits_service_role" 
    ON public.user_credits 
    FOR ALL 
    TO service_role 
    USING (true)
    WITH CHECK (true);

-- ============================================================================
-- Step 3: Create Sync Trigger
-- ============================================================================

CREATE OR REPLACE FUNCTION public.sync_user_credits_from_litellm()
RETURNS TRIGGER AS $$
BEGIN
    -- Only proceed if user_id is a valid UUID
    -- LiteLLM_UserTable might have non-UUID IDs in some setups, but here we expect Supabase UIDs
    IF (NEW.user_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') THEN
        INSERT INTO public.user_credits (
            user_id, 
            balance, 
            max_budget, 
            total_spent, 
            updated_at
        )
        VALUES (
            NEW.user_id::UUID,
            GREATEST(0, COALESCE(NEW.max_budget, 0) - COALESCE(NEW.spend, 0)),
            COALESCE(NEW.max_budget, 0),
            COALESCE(NEW.spend, 0),
            now()
        )
        ON CONFLICT (user_id) DO UPDATE SET
            balance = EXCLUDED.balance,
            max_budget = EXCLUDED.max_budget,
            total_spent = EXCLUDED.total_spent,
            updated_at = EXCLUDED.updated_at;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create the trigger
DROP TRIGGER IF EXISTS trigger_sync_user_credits ON public."LiteLLM_UserTable";
CREATE TRIGGER trigger_sync_user_credits
AFTER INSERT OR UPDATE ON public."LiteLLM_UserTable"
FOR EACH ROW
EXECUTE FUNCTION public.sync_user_credits_from_litellm();

-- ============================================================================
-- Step 4: Initial Sync of existing data
-- ============================================================================

INSERT INTO public.user_credits (user_id, balance, max_budget, total_spent)
SELECT 
    user_id::UUID,
    GREATEST(0, COALESCE(max_budget, 0) - COALESCE(spend, 0)),
    COALESCE(max_budget, 0),
    COALESCE(spend, 0)
FROM public."LiteLLM_UserTable"
WHERE user_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
ON CONFLICT (user_id) DO UPDATE SET
    balance = EXCLUDED.balance,
    max_budget = EXCLUDED.max_budget,
    total_spent = EXCLUDED.total_spent,
    updated_at = now();

-- ============================================================================
-- Step 5: Enable Realtime
-- ============================================================================

-- Set REPLICA IDENTITY to FULL
ALTER TABLE public.user_credits REPLICA IDENTITY FULL;

-- Add to publication
BEGIN;
    -- Try to add, catch if already exists
    DO $$
    BEGIN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.user_credits;
    EXCEPTION WHEN duplicate_object THEN
        RAISE NOTICE 'user_credits already in publication';
    END;
    $$;
COMMIT;
