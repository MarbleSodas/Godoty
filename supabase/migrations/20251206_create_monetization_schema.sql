-- Migration: Create monetization schema for Godoty
-- Handles user credit balances and transaction ledger
-- Version: 2 - Added idempotency support via external_id

-- Drop existing tables to start fresh (no data to preserve)
DROP TABLE IF EXISTS transactions CASCADE;
DROP TABLE IF EXISTS profiles CASCADE;
DROP FUNCTION IF EXISTS handle_new_user CASCADE;
DROP FUNCTION IF EXISTS deduct_credits CASCADE;
DROP FUNCTION IF EXISTS add_credits CASCADE;

-- User profiles with credit balance
CREATE TABLE profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    credit_balance NUMERIC(15, 9) DEFAULT 0 NOT NULL CHECK (credit_balance >= 0),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Auto-create profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id)
    VALUES (NEW.id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Transaction ledger (immutable audit log)
CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('top_up', 'usage', 'bonus', 'correction')),
    amount NUMERIC(15, 9) NOT NULL,
    description TEXT,
    metadata JSONB,
    external_id TEXT UNIQUE,  -- For idempotency (e.g., Stripe session ID)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for faster queries
CREATE INDEX idx_transactions_user_id ON transactions(user_id);
CREATE INDEX idx_transactions_created_at ON transactions(created_at);
CREATE INDEX idx_transactions_external_id ON transactions(external_id) WHERE external_id IS NOT NULL;

-- RLS Policies
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

-- Users can read their own profile but NOT update credit_balance directly
CREATE POLICY "Users can read own profile"
    ON profiles FOR SELECT USING (auth.uid() = id);

-- Users can read their own transactions
CREATE POLICY "Users can read own transactions"
    ON transactions FOR SELECT USING (auth.uid() = user_id);

-- RPC function to deduct credits (service role only)
-- Uses FOR UPDATE lock to prevent race conditions
CREATE OR REPLACE FUNCTION deduct_credits(
    p_user_id UUID, 
    p_amount NUMERIC, 
    p_description TEXT DEFAULT NULL, 
    p_metadata JSONB DEFAULT NULL
)
RETURNS BOOLEAN AS $$
DECLARE
    current_balance NUMERIC;
BEGIN
    -- Lock the user's row to prevent double-spending
    SELECT credit_balance INTO current_balance 
    FROM profiles 
    WHERE id = p_user_id 
    FOR UPDATE;
    
    IF current_balance IS NULL THEN
        RAISE EXCEPTION 'User profile not found';
    END IF;
    
    IF current_balance < p_amount THEN
        RETURN FALSE;  -- Insufficient credits
    END IF;
    
    -- Apply deduction
    UPDATE profiles 
    SET credit_balance = credit_balance - p_amount 
    WHERE id = p_user_id;
    
    -- Log transaction
    INSERT INTO transactions (user_id, type, amount, description, metadata)
    VALUES (p_user_id, 'usage', -p_amount, p_description, p_metadata);
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- RPC function to add credits (for webhooks, service role only)
-- Includes idempotency check via external_id
CREATE OR REPLACE FUNCTION add_credits(
    p_user_id UUID, 
    p_amount NUMERIC, 
    p_description TEXT DEFAULT NULL, 
    p_metadata JSONB DEFAULT NULL,
    p_external_id TEXT DEFAULT NULL
)
RETURNS BOOLEAN AS $$
DECLARE
    existing_id UUID;
BEGIN
    -- Idempotency check: if external_id provided, check if already processed
    IF p_external_id IS NOT NULL THEN
        SELECT id INTO existing_id 
        FROM transactions 
        WHERE external_id = p_external_id;
        
        IF existing_id IS NOT NULL THEN
            -- Already processed, return FALSE to indicate no action taken
            RETURN FALSE;
        END IF;
    END IF;
    
    -- Update balance
    UPDATE profiles 
    SET credit_balance = credit_balance + p_amount 
    WHERE id = p_user_id;
    
    IF NOT FOUND THEN
        RAISE EXCEPTION 'User profile not found';
    END IF;
    
    -- Log transaction with external_id for idempotency
    INSERT INTO transactions (user_id, type, amount, description, metadata, external_id)
    VALUES (p_user_id, 'top_up', p_amount, p_description, p_metadata, p_external_id);
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
