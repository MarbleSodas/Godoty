-- Migration: Enable Realtime for credit-related tables
-- 
-- This migration sets up Supabase Realtime for tables related to the credits display:
-- 1. LiteLLM_UserTable - stores user budgets and spend (source of truth for credits)
-- 2. credit_transactions - audit log of credit purchases/refunds
--
-- Prerequisites for Realtime to work:
-- - Tables must be added to the supabase_realtime publication
-- - REPLICA IDENTITY must be set to FULL to receive old records on UPDATE
-- - RLS policies must allow SELECT for authenticated users

-- ============================================================================
-- Step 1: Create or update the supabase_realtime publication
-- ============================================================================

-- Drop and recreate publication if it exists (idempotent)
DO $$
BEGIN
    -- Check if publication exists
    IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
        -- Publication exists, we'll add tables to it
        RAISE NOTICE 'supabase_realtime publication exists, will add tables';
    ELSE
        -- Create the publication
        CREATE PUBLICATION supabase_realtime;
        RAISE NOTICE 'Created supabase_realtime publication';
    END IF;
END
$$;

-- ============================================================================
-- Step 2: Add LiteLLM_UserTable to publication (for budget/spend updates)
-- ============================================================================

DO $$
BEGIN
    -- Check if table exists before adding to publication
    IF EXISTS (
        SELECT FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename = 'LiteLLM_UserTable'
    ) THEN
        -- Set REPLICA IDENTITY to FULL so we receive old records on UPDATE
        -- This is needed to compare old vs new values in realtime subscriptions
        ALTER TABLE public."LiteLLM_UserTable" REPLICA IDENTITY FULL;
        
        -- Add table to supabase_realtime publication
        -- Use IF NOT EXISTS equivalent by catching exception
        BEGIN
            ALTER PUBLICATION supabase_realtime ADD TABLE public."LiteLLM_UserTable";
            RAISE NOTICE 'Added LiteLLM_UserTable to supabase_realtime publication';
        EXCEPTION WHEN duplicate_object THEN
            RAISE NOTICE 'LiteLLM_UserTable already in supabase_realtime publication';
        END;
    ELSE
        RAISE NOTICE 'LiteLLM_UserTable not found, skipping';
    END IF;
END
$$;

-- ============================================================================
-- Step 3: Add credit_transactions to publication (for new purchase notifications)
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename = 'credit_transactions'
    ) THEN
        -- Set REPLICA IDENTITY to FULL for credit_transactions
        ALTER TABLE public.credit_transactions REPLICA IDENTITY FULL;
        
        -- Add to publication
        BEGIN
            ALTER PUBLICATION supabase_realtime ADD TABLE public.credit_transactions;
            RAISE NOTICE 'Added credit_transactions to supabase_realtime publication';
        EXCEPTION WHEN duplicate_object THEN
            RAISE NOTICE 'credit_transactions already in supabase_realtime publication';
        END;
    ELSE
        RAISE NOTICE 'credit_transactions not found, skipping';
    END IF;
END
$$;

-- ============================================================================
-- Step 4: Ensure RLS policy allows authenticated users to SELECT their own data
-- (Required for Realtime to filter changes per-user)
-- ============================================================================

-- For LiteLLM_UserTable: Create/update policy for authenticated users
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename = 'LiteLLM_UserTable'
    ) THEN
        -- Drop existing authenticated policy if it exists
        DROP POLICY IF EXISTS "Authenticated users can view own budget" ON public."LiteLLM_UserTable";
        
        -- Create policy allowing users to see their own record
        -- This is needed for Realtime to authorize sending updates to the user
        CREATE POLICY "Authenticated users can view own budget"
            ON public."LiteLLM_UserTable"
            FOR SELECT
            TO authenticated
            USING (user_id = auth.uid()::text);
            
        RAISE NOTICE 'Created RLS policy for LiteLLM_UserTable realtime access';
    END IF;
END
$$;

-- credit_transactions already has RLS policy from original migration:
-- "Users can view their own transactions" allows SELECT where auth.uid() = user_id

-- ============================================================================
-- Step 5: Add logic to automatically update user budget when transaction occurs
-- ============================================================================

CREATE OR REPLACE FUNCTION public.sync_user_budget_from_transaction()
RETURNS TRIGGER AS $$
DECLARE
    current_budget DECIMAL(10, 4);
    target_user_id TEXT;
BEGIN
    target_user_id := NEW.user_id::TEXT;
    
    -- Get current max_budget from LiteLLM_UserTable
    -- If user doesn't exist, we assume 0 or handle error
    SELECT COALESCE(max_budget, 0) INTO current_budget
    FROM public."LiteLLM_UserTable"
    WHERE user_id = target_user_id;

    IF current_budget IS NULL THEN 
       current_budget := 0;
    END IF;

    -- Update the transaction record with budget snapshots if not provided
    -- This ensures the transaction log has the state "before" and "after"
    IF NEW.previous_budget IS NULL THEN
        NEW.previous_budget := current_budget;
    END IF;
    
    -- Calculate new budget based on transaction amount
    -- amount is positive for purchase, negative for refund
    IF NEW.new_budget IS NULL THEN
        NEW.new_budget := current_budget + NEW.amount;
    END IF;

    -- Update the LiteLLM_UserTable or insert if it doesn't exist
    -- This update/insert allows the realtime subscription on LiteLLM_UserTable to fire!
    INSERT INTO public."LiteLLM_UserTable" (user_id, max_budget, spend)
    VALUES (target_user_id, NEW.new_budget, 0)
    ON CONFLICT (user_id) 
    DO UPDATE SET max_budget = EXCLUDED.max_budget;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create the trigger
DROP TRIGGER IF EXISTS trigger_sync_user_budget ON public.credit_transactions;

CREATE TRIGGER trigger_sync_user_budget
BEFORE INSERT ON public.credit_transactions
FOR EACH ROW
EXECUTE FUNCTION public.sync_user_budget_from_transaction();

-- ============================================================================
-- Summary:
-- 
-- After this migration, the frontend can subscribe to realtime changes:
--
-- 1. LiteLLM_UserTable updates (budget/spend changes):
--    supabase.channel('balance-updates')
--      .on('postgres_changes', {
--        event: 'UPDATE',
--        schema: 'public',
--        table: 'LiteLLM_UserTable',
--        filter: `user_id=eq.${userId}`
--      }, callback)
--      .subscribe()
--
-- 2. credit_transactions inserts (new purchases):
--    supabase.channel('credit-transactions')
--      .on('postgres_changes', {
--        event: 'INSERT',
--        schema: 'public', 
--        table: 'credit_transactions',
--        filter: `user_id=eq.${userId}`
--      }, callback)
--      .subscribe()
-- ============================================================================
