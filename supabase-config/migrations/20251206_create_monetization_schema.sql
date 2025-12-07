-- Migration: Create monetization schema for Godoty
-- Handles user credit balances and transaction ledger

-- User profiles with credit balance
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    credit_balance NUMERIC(15, 9) DEFAULT 0 NOT NULL,
    lemon_squeezy_customer_id TEXT,
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
CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('top_up', 'usage', 'bonus', 'correction')),
    amount NUMERIC(15, 9) NOT NULL,
    description TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at);

-- RLS Policies
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

-- Users can read their own profile but NOT update credit_balance directly
DROP POLICY IF EXISTS "Users can read own profile" ON profiles;
CREATE POLICY "Users can read own profile"
    ON profiles FOR SELECT USING (auth.uid() = id);

-- Users can read their own transactions
DROP POLICY IF EXISTS "Users can read own transactions" ON transactions;
CREATE POLICY "Users can read own transactions"
    ON transactions FOR SELECT USING (auth.uid() = user_id);

-- RPC function to deduct credits (service role only)
CREATE OR REPLACE FUNCTION deduct_credits(
    p_user_id UUID, 
    p_amount NUMERIC, 
    p_description TEXT, 
    p_metadata JSONB
)
RETURNS BOOLEAN AS $$
DECLARE
    current_balance NUMERIC;
BEGIN
    SELECT credit_balance INTO current_balance 
    FROM profiles 
    WHERE id = p_user_id 
    FOR UPDATE;
    
    IF current_balance < p_amount THEN
        RETURN FALSE;
    END IF;
    
    UPDATE profiles 
    SET credit_balance = credit_balance - p_amount 
    WHERE id = p_user_id;
    
    INSERT INTO transactions (user_id, type, amount, description, metadata)
    VALUES (p_user_id, 'usage', -p_amount, p_description, p_metadata);
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- RPC function to add credits (for webhooks, service role only)
CREATE OR REPLACE FUNCTION add_credits(
    p_user_id UUID, 
    p_amount NUMERIC, 
    p_description TEXT, 
    p_metadata JSONB
)
RETURNS BOOLEAN AS $$
BEGIN
    UPDATE profiles 
    SET credit_balance = credit_balance + p_amount 
    WHERE id = p_user_id;
    
    INSERT INTO transactions (user_id, type, amount, description, metadata)
    VALUES (p_user_id, 'top_up', p_amount, p_description, p_metadata);
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
