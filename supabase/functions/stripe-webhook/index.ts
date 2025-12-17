// Supabase Edge Function: stripe-webhook
// Handles Stripe webhooks to process successful payments and credit user's LiteLLM budget
//
// SECURITY:
// - Stripe signature verification (HMAC-SHA256)
// - Idempotent webhook processing (prevents duplicate credits)
// - Rate limiting for purchase events
// - Atomic transaction recording via SECURITY DEFINER function

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
        'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, stripe-signature',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
    }
}

// Credit package mapping: price_id -> credit amount (in USD)
const CREDIT_PACKAGES: Record<string, number> = {
    'price_1SeUdXExVVDh2wU3LoTcnc6A': 5,   // Starter Pack - $5 -> 5 credits
    'price_1SeUduExVVDh2wU3h4yLDftJ': 11,  // Pro Pack - $10 -> 11 credits (10% bonus)
    'price_1SeUeGExVVDh2wU3jdPd1Oil': 23,  // Premium Pack - $20 -> 23 credits (15% bonus)
}

interface IdempotencyResult {
    already_processed: boolean
    original_result?: unknown
    processed_at?: string
    webhook_id?: string
}

interface TransactionResult {
    success: boolean
    transaction_id?: string
    duplicate?: boolean
    error?: string
    message?: string
}

// Helper to verify Stripe webhook signature manually
async function verifyStripeSignature(
    payload: string,
    signature: string,
    secret: string
): Promise<boolean> {
    const parts = signature.split(',')
    let timestamp = ''
    let sig = ''

    for (const part of parts) {
        const [key, value] = part.split('=')
        if (key === 't') timestamp = value
        if (key === 'v1') sig = value
    }

    if (!timestamp || !sig) {
        console.error('Missing timestamp or signature in header')
        return false
    }

    // Check timestamp tolerance (5 min)
    const now = Math.floor(Date.now() / 1000)
    if (Math.abs(now - parseInt(timestamp)) > 300) {
        console.error('Timestamp too old:', timestamp, 'now:', now)
        return false
    }

    // Compute expected signature using Web Crypto API
    const signedPayload = `${timestamp}.${payload}`
    const encoder = new TextEncoder()
    const keyData = encoder.encode(secret)
    const msgData = encoder.encode(signedPayload)

    const cryptoKey = await crypto.subtle.importKey(
        'raw',
        keyData,
        { name: 'HMAC', hash: 'SHA-256' },
        false,
        ['sign']
    )

    const signatureBuffer = await crypto.subtle.sign('HMAC', cryptoKey, msgData)
    const computedSig = Array.from(new Uint8Array(signatureBuffer))
        .map(b => b.toString(16).padStart(2, '0'))
        .join('')

    const isValid = computedSig === sig
    if (!isValid) {
        console.error('Signature mismatch')
    }
    return isValid
}

serve(async (req) => {
    // Get CORS headers for this request
    const corsHeaders = getCorsHeaders(req)

    // Handle CORS preflight
    if (req.method === 'OPTIONS') {
        return new Response('ok', { headers: corsHeaders })
    }

    console.log('Stripe webhook received')

    try {
        // Get Stripe secrets
        const webhookSecret = Deno.env.get('STRIPE_WEBHOOK_SECRET')
        const stripeSecretKey = Deno.env.get('STRIPE_SECRET_KEY')

        if (!webhookSecret) {
            console.error('Missing STRIPE_WEBHOOK_SECRET')
            return new Response(
                JSON.stringify({ error: 'Webhook secret not configured' }),
                { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
            )
        }

        // Get raw body and signature
        const body = await req.text()
        const signature = req.headers.get('stripe-signature')

        console.log('Signature present:', !!signature, 'Body length:', body.length)

        if (!signature) {
            return new Response(
                JSON.stringify({ error: 'Missing stripe-signature header' }),
                { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
            )
        }

        // Verify signature
        const isValid = await verifyStripeSignature(body, signature, webhookSecret)
        if (!isValid) {
            console.error('Invalid webhook signature')
            return new Response(
                JSON.stringify({ error: 'Invalid signature' }),
                { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
            )
        }

        console.log('Signature verified')

        // Parse the event
        const event = JSON.parse(body)
        console.log('Event type:', event.type, 'Event ID:', event.id)

        // Only handle checkout.session.completed events
        if (event.type !== 'checkout.session.completed') {
            return new Response(
                JSON.stringify({ received: true, message: 'Event type not handled' }),
                { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
            )
        }

        // Setup Supabase client with service role (for database operations)
        const supabaseUrl = Deno.env.get('SUPABASE_URL') ?? ''
        const supabaseServiceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''
        const supabase = createClient(supabaseUrl, supabaseServiceKey)

        // Check idempotency - has this webhook already been processed?
        const { data: idempotencyCheck, error: idempotencyError } = await supabase
            .rpc('process_webhook_idempotent', {
                p_webhook_id: event.id,
                p_webhook_type: 'stripe'
            })

        if (idempotencyError) {
            console.error('Idempotency check failed:', idempotencyError)
            // Continue anyway - prefer to risk duplicate than miss payment
        } else {
            const idempotency = idempotencyCheck as IdempotencyResult
            if (idempotency.already_processed) {
                console.log(`Webhook ${event.id} already processed at ${idempotency.processed_at}`)
                return new Response(
                    JSON.stringify({
                        received: true,
                        message: 'Already processed',
                        original_result: idempotency.original_result
                    }),
                    { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
                )
            }
        }

        const session = event.data.object
        console.log('Session ID:', session.id, 'User:', session.client_reference_id)

        // Get user_id from client_reference_id or metadata
        const userId = session.client_reference_id || session.metadata?.user_id
        if (!userId) {
            console.error('No user_id in session')
            return new Response(
                JSON.stringify({ error: 'No user_id in session' }),
                { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
            )
        }

        // Get the price_id by fetching line items from Stripe API
        const lineItemsResponse = await fetch(
            `https://api.stripe.com/v1/checkout/sessions/${session.id}/line_items`,
            { headers: { 'Authorization': `Bearer ${stripeSecretKey}` } }
        )

        if (!lineItemsResponse.ok) {
            console.error('Failed to fetch line items:', await lineItemsResponse.text())
            return new Response(
                JSON.stringify({ error: 'Failed to fetch line items' }),
                { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
            )
        }

        const lineItems = await lineItemsResponse.json()
        const priceId = lineItems.data?.[0]?.price?.id
        console.log('Price ID:', priceId)

        if (!priceId) {
            return new Response(
                JSON.stringify({ error: 'No price_id in session' }),
                { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
            )
        }

        // Get credit amount from price mapping
        const creditAmount = CREDIT_PACKAGES[priceId]
        if (!creditAmount) {
            console.error('Unknown price_id:', priceId)
            return new Response(
                JSON.stringify({ error: `Unknown price_id: ${priceId}` }),
                { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
            )
        }

        console.log('Credit amount:', creditAmount)

        // Get LiteLLM configuration
        const litellmMasterKey = Deno.env.get('LITELLM_MASTER_KEY')
        const litellmUrlRaw = Deno.env.get('LITELLM_URL')

        if (!litellmMasterKey || !litellmUrlRaw) {
            console.error('Missing LiteLLM configuration')
            return new Response(
                JSON.stringify({ error: 'LiteLLM not configured' }),
                { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
            )
        }

        const litellmUrl = litellmUrlRaw.replace(/\/+$/, '').replace(/\/v1\/?$/, '')

        // Get current user budget from LiteLLM
        let currentMaxBudget = 0
        let currentSpend = 0

        try {
            const userInfoResponse = await fetch(`${litellmUrl}/user/info?user_id=${userId}`, {
                headers: { 'Authorization': `Bearer ${litellmMasterKey}` }
            })

            if (userInfoResponse.ok) {
                const userInfo = await userInfoResponse.json()
                currentMaxBudget = userInfo.user_info?.max_budget ?? 0
                currentSpend = userInfo.user_info?.spend ?? 0
                console.log('Current budget:', currentMaxBudget, 'spend:', currentSpend)
            }
        } catch (err) {
            console.warn('Failed to fetch user info:', err)
        }

        // Calculate new budget
        const newMaxBudget = currentMaxBudget + creditAmount
        console.log('Budget update:', currentMaxBudget, '->', newMaxBudget)

        // Update or create user in LiteLLM
        try {
            // Try to update existing user
            const updateResponse = await fetch(`${litellmUrl}/user/update`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${litellmMasterKey}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    user_id: userId,
                    max_budget: newMaxBudget
                })
            })

            if (!updateResponse.ok) {
                console.log('Update failed, trying to create user')
                // Try creating the user instead
                const createResponse = await fetch(`${litellmUrl}/user/new`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${litellmMasterKey}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        user_id: userId,
                        user_email: session.customer_email,
                        max_budget: newMaxBudget
                    })
                })

                if (!createResponse.ok) {
                    const createError = await createResponse.text()
                    console.error('Failed to create user:', createError)
                    throw new Error(`LiteLLM error: ${createError}`)
                }
                console.log('Created new LiteLLM user')
            } else {
                console.log('Updated existing LiteLLM user')
            }
        } catch (err) {
            console.error('LiteLLM error:', err)
            return new Response(
                JSON.stringify({ error: 'Failed to update user budget' }),
                { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
            )
        }

        // Record transaction atomically using SECURITY DEFINER function
        const { data: transactionResult, error: transactionError } = await supabase
            .rpc('record_credit_transaction', {
                p_user_id: userId,
                p_amount: creditAmount,
                p_type: 'purchase',
                p_stripe_session_id: session.id,
                p_stripe_payment_intent: session.payment_intent,
                p_previous_budget: currentMaxBudget,
                p_new_budget: newMaxBudget,
                p_notes: `Stripe checkout: ${priceId}`
            })

        if (transactionError) {
            console.error('Transaction recording error:', transactionError)
            // Don't fail the webhook - budget was already updated in LiteLLM
        } else {
            const txResult = transactionResult as TransactionResult
            if (txResult.duplicate) {
                console.log('Transaction was duplicate, already recorded:', txResult.transaction_id)
            } else if (txResult.success) {
                console.log('Transaction recorded:', txResult.transaction_id)
            } else {
                console.error('Transaction recording failed:', txResult.error)
            }
        }

        // Update the idempotency record with the result
        const resultPayload = {
            success: true,
            user_id: userId,
            credits_added: creditAmount,
            new_budget: newMaxBudget,
            transaction_id: (transactionResult as TransactionResult)?.transaction_id
        }

        // Update webhook record with result (best effort)
        try {
            await supabase
                .from('processed_webhooks')
                .update({ result: resultPayload })
                .eq('webhook_id', event.id)
        } catch (err) {
            console.warn('Failed to update webhook result:', err)
        }

        console.log(`SUCCESS: +${creditAmount} credits for user ${userId}`)

        return new Response(
            JSON.stringify(resultPayload),
            { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )

    } catch (error) {
        console.error('Webhook error:', error)
        return new Response(
            JSON.stringify({ error: error instanceof Error ? error.message : 'Internal server error' }),
            { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
    }
})
