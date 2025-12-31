-- Migration: Create user_virtual_keys table for caching LiteLLM virtual keys
-- This table stores the virtual keys generated for users to enable key reuse

CREATE TABLE IF NOT EXISTS public.user_virtual_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    litellm_key TEXT NOT NULL,
    litellm_key_id TEXT, -- Key identifier from LiteLLM (key_name or token)
    expires_at TIMESTAMPTZ NOT NULL,
    allowed_models TEXT[] DEFAULT ARRAY['gpt-4o', 'gpt-4o-mini', 'claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022'],
    max_budget DECIMAL(10, 4), -- Will be removed in later migration (budget moves to user level)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create index for faster lookups by user_id
CREATE INDEX IF NOT EXISTS idx_user_virtual_keys_user_id ON public.user_virtual_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_user_virtual_keys_expires_at ON public.user_virtual_keys(expires_at);

-- Enable Row Level Security
ALTER TABLE public.user_virtual_keys ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Users can only read their own keys
CREATE POLICY "Users can view their own virtual keys"
    ON public.user_virtual_keys
    FOR SELECT
    USING (auth.uid() = user_id);

-- RLS Policy: Only service role can insert/update/delete keys (from edge functions)
CREATE POLICY "Service role can manage all virtual keys"
    ON public.user_virtual_keys
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- Comment on table
COMMENT ON TABLE public.user_virtual_keys IS 'Caches LiteLLM virtual keys for users to enable key reuse and reduce API calls.';
COMMENT ON COLUMN public.user_virtual_keys.litellm_key IS 'The actual virtual key from LiteLLM';
COMMENT ON COLUMN public.user_virtual_keys.litellm_key_id IS 'Key identifier from LiteLLM for tracking/revocation';
COMMENT ON COLUMN public.user_virtual_keys.allowed_models IS 'Array of model IDs this key can access';
