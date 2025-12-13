// Supabase Edge Function: generate-litellm-key
// Securely generates LiteLLM virtual keys for authenticated users
// The LITELLM_MASTER_KEY never leaves this edge environment
//
// KEY ARCHITECTURE:
// - Budget is managed at the USER level in LiteLLM, not the KEY level
// - Users can regenerate/have multiple keys sharing the same wallet
// - Stripe webhook updates user's max_budget (cumulative)
// - Keys are linked to user_id for spend tracking

import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

interface LiteLLMUserInfo {
  user_id: string
  max_budget?: number | null
  spend?: number
  user_email?: string
}

serve(async (req) => {
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    // 1. Setup Supabase Client to verify the user
    const authHeader = req.headers.get('Authorization')
    if (!authHeader) {
      return new Response(
        JSON.stringify({ error: 'Missing authorization header' }),
        { status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    const supabaseUrl = Deno.env.get('SUPABASE_URL') ?? ''
    const supabaseAnonKey = Deno.env.get('SUPABASE_ANON_KEY') ?? ''

    const supabase = createClient(supabaseUrl, supabaseAnonKey, {
      global: { headers: { Authorization: authHeader } }
    })

    // 2. Get the User from the Token
    const { data: { user }, error: authError } = await supabase.auth.getUser()

    if (authError || !user) {
      return new Response(
        JSON.stringify({ error: 'Unauthorized', details: authError?.message }),
        { status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 3. Check if user already has a valid key in our database
    const { data: existingKey } = await supabase
      .from('user_virtual_keys')
      .select('litellm_key, expires_at, allowed_models')
      .eq('user_id', user.id)
      .single()

    // 4. Get LiteLLM configuration
    const litellmMasterKey = Deno.env.get('LITELLM_MASTER_KEY')
    const litellmUrlRaw = Deno.env.get('LITELLM_URL')

    if (!litellmMasterKey || !litellmUrlRaw) {
      return new Response(
        JSON.stringify({ error: 'Server configuration error' }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // Sanitize URL: remove trailing slashes and optional /v1 suffix (admin endpoints are usually at root)
    const litellmUrl = litellmUrlRaw.replace(/\/+$/, '').replace(/\/v1\/?$/, '')

    // 5. Get user's current budget info from LiteLLM (budget is at USER level)
    let userBudgetInfo = { maxBudget: 0, spend: 0, remainingBudget: 0 }

    try {
      const userInfoResponse = await fetch(`${litellmUrl}/user/info?user_id=${user.id}`, {
        headers: { 'Authorization': `Bearer ${litellmMasterKey}` }
      })

      if (userInfoResponse.ok) {
        const userInfo: { user_info: LiteLLMUserInfo } = await userInfoResponse.json()
        const maxBudget = userInfo.user_info?.max_budget ?? 0
        const spend = userInfo.user_info?.spend ?? 0
        userBudgetInfo = {
          maxBudget,
          spend,
          remainingBudget: Math.max(0, maxBudget - spend)
        }
      }
    } catch (err) {
      console.warn('Failed to fetch user budget info:', err)
    }

    // If key exists and hasn't expired, return it with current budget info
    if (existingKey && new Date(existingKey.expires_at) > new Date()) {
      return new Response(
        JSON.stringify({
          apiKey: existingKey.litellm_key,
          expiresAt: existingKey.expires_at,
          ...userBudgetInfo,
          allowedModels: existingKey.allowed_models,
          cached: true
        }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 6. Parse request body for optional parameters
    let requestBody: { models?: string[] } = {}
    try {
      if (req.body) {
        requestBody = await req.json()
      }
    } catch {
      // No body or invalid JSON, use defaults
    }

    // Models can be restricted per key, but budget comes from user
    const allowedModels = requestBody.models ?? [
      'gpt-4o',
      'gpt-4o-mini',
      'claude-3-5-sonnet-20241022',
      'claude-3-5-haiku-20241022'
    ]

    // 7. Ensure user exists in LiteLLM (create if not)
    try {
      const checkUserResponse = await fetch(`${litellmUrl}/user/info?user_id=${user.id}`, {
        headers: { 'Authorization': `Bearer ${litellmMasterKey}` }
      })

      if (!checkUserResponse.ok) {
        // Create user in LiteLLM with $0 budget (they need to purchase credits)
        await fetch(`${litellmUrl}/user/new`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${litellmMasterKey}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            user_id: user.id,
            user_email: user.email,
            max_budget: 0 // Start with $0, Stripe webhook will add credits
          })
        })
      }
    } catch (err) {
      console.warn('Failed to ensure user exists:', err)
    }

    // 8. Generate key linked to user (budget controlled by user, not key)
    const response = await fetch(`${litellmUrl}/key/generate`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${litellmMasterKey}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        user_id: user.id, // Links this key to the user's budget
        duration: null,   // Infinite duration - budget controls access, not key expiry
        models: allowedModels,
        metadata: {
          supabase_user_id: user.id,
          email: user.email,
          created_by: 'godoty-edge-function'
        }
        // NOTE: No max_budget on key - budget is controlled at USER level
      })
    })

    if (!response.ok) {
      const errorText = await response.text()
      const keyGenUrl = `${litellmUrl}/key/generate`
      console.error(`LiteLLM key generation failed:`)
      console.error(`  Configured URL: ${litellmUrlRaw}`)
      console.error(`  Target URL: ${keyGenUrl}`)
      console.error(`  Status: ${response.status}`)
      console.error(`  Response: ${errorText}`)
      console.error(`  Note: If status is 404, the LiteLLM proxy may not have DATABASE_URL configured, or the URL path is incorrect.`)
      return new Response(
        JSON.stringify({
          error: 'Failed to generate key',
          details: errorText,
          hint: response.status === 404
            ? 'LiteLLM proxy may not have virtual keys enabled. Ensure DATABASE_URL is configured on the proxy.'
            : undefined
        }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    const litellmData = await response.json()
    // Keys don't expire by time - they expire when user budget is depleted
    // We set a long expiry for cache invalidation purposes only
    const expiresAt = new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toISOString() // 1 year

    // 9. Store the key in our database for caching
    const { error: upsertError } = await supabase
      .from('user_virtual_keys')
      .upsert({
        user_id: user.id,
        litellm_key: litellmData.key,
        litellm_key_id: litellmData.key_name || litellmData.token,
        expires_at: expiresAt,
        allowed_models: allowedModels,
        updated_at: new Date().toISOString()
      }, {
        onConflict: 'user_id'
      })

    if (upsertError) {
      console.error('Failed to cache key:', upsertError)
      // Continue anyway - key was generated successfully
    }

    // 10. Return the new key with current budget info
    return new Response(
      JSON.stringify({
        apiKey: litellmData.key,
        expiresAt: expiresAt,
        ...userBudgetInfo,
        allowedModels: allowedModels,
        cached: false
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (error) {
    console.error('Edge function error:', error)
    return new Response(
      JSON.stringify({ error: 'Internal server error', details: error.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }
})
