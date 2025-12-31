-- Migration: Add credit_transactions table and update user_virtual_keys
-- This migration supports user-based wallet/budget system with LiteLLM

-- Create credit_transactions table for audit trail
CREATE TABLE IF NOT EXISTS public.credit_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    amount DECIMAL(10, 4) NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('purchase', 'refund', 'adjustment', 'bonus')),
    stripe_session_id TEXT,
    stripe_payment_intent TEXT,
    previous_budget DECIMAL(10, 4),
    new_budget DECIMAL(10, 4),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes for credit_transactions
CREATE INDEX IF NOT EXISTS idx_credit_transactions_user_id ON public.credit_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_credit_transactions_created_at ON public.credit_transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_credit_transactions_stripe_session ON public.credit_transactions(stripe_session_id) WHERE stripe_session_id IS NOT NULL;

-- Enable RLS on credit_transactions
ALTER TABLE public.credit_transactions ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Users can only read their own transactions
CREATE POLICY "Users can view their own transactions"
    ON public.credit_transactions
    FOR SELECT
    USING (auth.uid() = user_id);

-- RLS Policy: Only service role can insert transactions (from webhooks)
CREATE POLICY "Service role can manage all transactions"
    ON public.credit_transactions
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- Remove max_budget from user_virtual_keys since budget is now at USER level in LiteLLM
-- We keep the table for key caching but budget tracking moves to LiteLLM
ALTER TABLE public.user_virtual_keys 
    DROP COLUMN IF EXISTS max_budget;

-- Comment on tables
COMMENT ON TABLE public.credit_transactions IS 'Audit log of all credit purchases, refunds, and adjustments. LiteLLM is source of truth for budgets.';
COMMENT ON COLUMN public.credit_transactions.amount IS 'Amount in USD (positive for purchases, negative for refunds)';
COMMENT ON COLUMN public.credit_transactions.type IS 'Transaction type: purchase, refund, adjustment, or bonus';
COMMENT ON COLUMN public.credit_transactions.previous_budget IS 'User max_budget in LiteLLM before this transaction';
COMMENT ON COLUMN public.credit_transactions.new_budget IS 'User max_budget in LiteLLM after this transaction';

-- Update comment on user_virtual_keys
COMMENT ON TABLE public.user_virtual_keys IS 'Caches LiteLLM virtual keys for users. Budget is managed at USER level in LiteLLM, not here.';
