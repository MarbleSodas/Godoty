// Supabase Edge Function: generate-litellm-key
// Securely generates LiteLLM virtual keys for authenticated users
// The LITELLM_MASTER_KEY never leaves this edge environment
//
// KEY ARCHITECTURE:
// - Budget is managed at the USER level in LiteLLM, not the KEY level
// - One key per user account (prevents key accumulation)
// - Stripe webhook updates user's max_budget (cumulative)
// - Keys are linked to user_id for spend tracking
//
// DEDUPLICATION:
// - Only one active key per user account
// - Returns cached key if valid, only generates new key if expired/missing
// - Deletes old LiteLLM key before generating new one to prevent accumulation
//
// SECURITY:
// - Database-level rate limiting (5 key generations per hour per user)
// - In-memory deduplication for concurrent requests
// - JWT verification for all requests

import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

// Allowed origins for CORS
const ALLOWED_ORIGINS = [
  'https://godoty.app',
  'tauri://localhost',
  'http://localhost:1420',  // Vite dev server
  'http://localhost:5173',  // Vite alt port
]

function getCorsHeaders(req: Request): Record<string, string> {
  const origin = req.headers.get('Origin') ?? ''
  const allowedOrigin = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0]
  return {
    'Access-Control-Allow-Origin': allowedOrigin,
    'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
  }
}

interface LiteLLMUserInfo {
  user_id: string
  max_budget?: number | null
  spend?: number
  user_email?: string
}

interface RateLimitResult {
  allowed: boolean
  remaining: number
  reset_at: string
  current_count: number
  max_requests: number
}

// In-memory lock to prevent concurrent key generation for same user+device
const generationLocks = new Map<string, Promise<Response>>()

serve(async (req) => {
  // Get CORS headers for this request
  const corsHeaders = getCorsHeaders(req)

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
    const supabaseServiceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''

    // Create user client for authentication verification
    const supabaseUser = createClient(supabaseUrl, supabaseAnonKey, {
      global: { headers: { Authorization: authHeader } }
    })

    // Create service client for database operations (bypasses RLS)
    const supabase = createClient(supabaseUrl, supabaseServiceKey)

    // 2. Get the User from the Token
    const { data: { user }, error: authError } = await supabaseUser.auth.getUser()

    if (authError || !user) {
      return new Response(
        JSON.stringify({ error: 'Unauthorized', details: authError?.message }),
        { status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 3. Check for concurrent requests - use lock to prevent race conditions
    const lockKey = user.id
    const existingLock = generationLocks.get(lockKey)
    if (existingLock) {
      // Another request is in progress for same user+device, wait for it
      return existingLock
    }

    // Create the actual handler as a promise
    const handleRequest = async (): Promise<Response> => {
      try {
        // 4. Check database-level rate limit (5 key generations per hour)
        const { data: rateLimitResult, error: rateLimitError } = await supabase
          .rpc('check_key_generation_limit', { p_user_id: user.id })

        if (rateLimitError) {
          console.error('Rate limit check failed:', rateLimitError)
          // Continue anyway - fail open for rate limiting errors
        } else {
          const rateLimit = rateLimitResult as RateLimitResult
          if (!rateLimit.allowed) {
            const resetAt = new Date(rateLimit.reset_at)
            return new Response(
              JSON.stringify({
                error: 'Rate limit exceeded',
                message: `Too many key generation requests. Try again after ${resetAt.toISOString()}`,
                reset_at: rateLimit.reset_at,
                remaining: rateLimit.remaining
              }),
              {
                status: 429,
                headers: {
                  ...corsHeaders,
                  'Content-Type': 'application/json',
                  'Retry-After': Math.ceil((resetAt.getTime() - Date.now()) / 1000).toString(),
                  'X-RateLimit-Limit': rateLimit.max_requests.toString(),
                  'X-RateLimit-Remaining': '0',
                  'X-RateLimit-Reset': resetAt.toISOString()
                }
              }
            )
          }
        }

        // 5. Check if user already has a valid key in our database
        const { data: existingKey, error: keyFetchError } = await supabase
          .from('user_virtual_keys')
          .select('litellm_key, litellm_key_id, expires_at, allowed_models')
          .eq('user_id', user.id)
          .maybeSingle()

        if (keyFetchError) {
          console.warn('Error fetching existing key:', keyFetchError)
        }

        // 6. Get LiteLLM configuration
        const litellmMasterKey = Deno.env.get('LITELLM_MASTER_KEY')
        const litellmUrlRaw = Deno.env.get('LITELLM_URL')

        if (!litellmMasterKey || !litellmUrlRaw) {
          return new Response(
            JSON.stringify({ error: 'Server configuration error' }),
            { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
          )
        }

        // Sanitize URL: remove trailing slashes and optional /v1 suffix
        const litellmUrl = litellmUrlRaw.replace(/\/+$/, '').replace(/\/v1\/?$/, '')

        // 7. Get user's current budget info from LiteLLM (budget is at USER level)
        let userBudgetInfo = { maxBudget: '0.0000', spend: '0.0000', remainingBudget: '0.0000' }

        try {
          const userInfoResponse = await fetch(`${litellmUrl}/user/info?user_id=${user.id}`, {
            headers: { 'Authorization': `Bearer ${litellmMasterKey}` }
          })

          if (userInfoResponse.ok) {
            const userInfo: { user_info: LiteLLMUserInfo } = await userInfoResponse.json()
            const maxBudget = userInfo.user_info?.max_budget ?? 0
            const spend = userInfo.user_info?.spend ?? 0
            userBudgetInfo = {
              maxBudget: maxBudget.toFixed(4),
              spend: spend.toFixed(4),
              remainingBudget: Math.max(0, maxBudget - spend).toFixed(4)
            }
          }
        } catch (err) {
          console.warn('Failed to fetch user budget info:', err)
        }

        // 8. If valid key exists and hasn't expired, return it with current budget info
        if (existingKey && existingKey.litellm_key && new Date(existingKey.expires_at) > new Date()) {
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

        // 9. Ensure user exists in LiteLLM (create if not)
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

        // 10. Delete old key in LiteLLM if it exists (prevents key accumulation)
        if (existingKey?.litellm_key_id) {
          try {
            await fetch(`${litellmUrl}/key/delete`, {
              method: 'POST',
              headers: {
                'Authorization': `Bearer ${litellmMasterKey}`,
                'Content-Type': 'application/json'
              },
              body: JSON.stringify({
                keys: [existingKey.litellm_key_id]
              })
            })
            console.log(`Deleted old LiteLLM key: ${existingKey.litellm_key_id}`)
          } catch (err) {
            console.warn('Failed to delete old LiteLLM key (non-fatal):', err)
            // Continue anyway - generating a new key is still possible
          }
        }

        // 11. Generate key linked to user (budget controlled by user, not key)
        const response = await fetch(`${litellmUrl}/key/generate`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${litellmMasterKey}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            user_id: user.id, // Links this key to the user's budget
            duration: null,   // Infinite duration - budget controls access, not key expiry
            permissions: {
              get_spend_routes: true  // Allow key to access /spend and /key/info endpoints for cost tracking
            },
            metadata: {
              supabase_user_id: user.id,
              email: user.email,
              created_by: 'godoty-edge-function'
            }
            // NOTE: No max_budget on key - budget is controlled at USER level
            // NOTE: No models specified - grants access to all models
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

        // 12. Store the key in our database for caching
        // First delete any existing record for this user to avoid conflicts
        await supabase
          .from('user_virtual_keys')
          .delete()
          .eq('user_id', user.id)

        // Then insert the new key
        const { error: insertError } = await supabase
          .from('user_virtual_keys')
          .insert({
            user_id: user.id,
            litellm_key: litellmData.key,
            litellm_key_id: litellmData.key_name || litellmData.token,
            expires_at: expiresAt,
            allowed_models: null, // No model restrictions - access to all models
            updated_at: new Date().toISOString()
          })

        if (insertError) {
          console.error('Failed to cache key:', insertError)
          // Continue anyway - key was generated successfully
        }

        // 13. Return the new key with current budget info
        return new Response(
          JSON.stringify({
            apiKey: litellmData.key,
            expiresAt: expiresAt,
            ...userBudgetInfo,
            allowedModels: null, // No model restrictions - access to all models
            cached: false
          }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )

      } finally {
        // Clean up the lock
        generationLocks.delete(lockKey)
      }
    }

    // Set the lock and execute
    const responsePromise = handleRequest()
    generationLocks.set(lockKey, responsePromise)
    return responsePromise

  } catch (error) {
    console.error('Edge function error:', error)
    return new Response(
      JSON.stringify({ error: 'Internal server error', details: error.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }
})
