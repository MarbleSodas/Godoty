// Supabase Edge Function: stripe-webhook
// Handles Stripe checkout completion and updates user budgets in LiteLLM
// This implements a user-based wallet system where budgets are cumulative

import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import Stripe from 'https://esm.sh/stripe@12.0.0'
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const stripe = new Stripe(Deno.env.get('STRIPE_SECRET_KEY') ?? '', {
  apiVersion: '2022-11-15'
})

const LITELLM_MASTER_KEY = Deno.env.get('LITELLM_MASTER_KEY')
const LITELLM_URL_RAW = Deno.env.get('LITELLM_URL')
// Sanitize URL: remove trailing slashes and optional /v1 suffix
const LITELLM_URL = LITELLM_URL_RAW ? LITELLM_URL_RAW.replace(/\/+$/, '').replace(/\/v1\/?$/, '') : undefined

interface LiteLLMUserInfo {
  user_id: string
  max_budget?: number | null
  spend?: number
  user_email?: string
}

serve(async (req) => {
  // Only accept POST requests for webhooks
  if (req.method !== 'POST') {
    return new Response('Method not allowed', { status: 405 })
  }

  const signature = req.headers.get('Stripe-Signature')
  if (!signature) {
    return new Response('Missing Stripe signature', { status: 400 })
  }

  const body = await req.text()

  try {
    // Verify the webhook signature
    const webhookSecret = Deno.env.get('STRIPE_WEBHOOK_SECRET')
    if (!webhookSecret) {
      console.error('STRIPE_WEBHOOK_SECRET not configured')
      return new Response('Server configuration error', { status: 500 })
    }

    const event = stripe.webhooks.constructEvent(body, signature, webhookSecret)

    // Handle checkout.session.completed event
    if (event.type === 'checkout.session.completed') {
      const session = event.data.object as Stripe.Checkout.Session

      // The Supabase Auth User ID should be passed as client_reference_id
      const userId = session.client_reference_id
      if (!userId) {
        console.error('No client_reference_id in checkout session')
        return new Response(JSON.stringify({ error: 'Missing user reference' }), { status: 400 })
      }

      // Convert cents to dollars
      const amountPaid = (session.amount_total ?? 0) / 100

      if (!LITELLM_MASTER_KEY || !LITELLM_URL) {
        console.error('LiteLLM configuration missing')
        return new Response('Server configuration error', { status: 500 })
      }

      // 1. Get current User Info from LiteLLM to find existing budget/spend
      let currentBudget = 0
      let userExists = false

      try {
        const userInfoResponse = await fetch(`${LITELLM_URL}/user/info?user_id=${userId}`, {
          headers: { 'Authorization': `Bearer ${LITELLM_MASTER_KEY}` }
        })

        if (userInfoResponse.ok) {
          const userInfo: { user_info: LiteLLMUserInfo } = await userInfoResponse.json()
          userExists = true
          // Get current max_budget (null means unlimited, treat as 0 for adding credits)
          currentBudget = userInfo.user_info?.max_budget ?? 0
        }
      } catch (err) {
        console.warn('Failed to fetch user info, will create new user:', err)
      }

      // 2. Calculate new cumulative budget
      // Key insight: We're increasing the LIMIT, not resetting the SPEND
      const newBudget = currentBudget + amountPaid

      // 3. Update or create LiteLLM user with new budget
      const endpoint = userExists ? `${LITELLM_URL}/user/update` : `${LITELLM_URL}/user/new`
      const method = 'POST'

      const updateResponse = await fetch(endpoint, {
        method,
        headers: {
          'Authorization': `Bearer ${LITELLM_MASTER_KEY}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          user_id: userId,
          max_budget: newBudget,
          // Include email if available from Stripe
          ...(session.customer_email && { user_email: session.customer_email })
        })
      })

      if (!updateResponse.ok) {
        const errorText = await updateResponse.text()
        console.error('Failed to update LiteLLM user budget:', errorText)
        throw new Error(`Failed to update LiteLLM: ${errorText}`)
      }

      // 4. Log the transaction in Supabase for audit trail
      const supabaseUrl = Deno.env.get('SUPABASE_URL') ?? ''
      const supabaseServiceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''

      if (supabaseUrl && supabaseServiceKey) {
        const supabase = createClient(supabaseUrl, supabaseServiceKey)

        // Update or record the transaction
        await supabase
          .from('credit_transactions')
          .insert({
            user_id: userId,
            amount: amountPaid,
            type: 'purchase',
            stripe_session_id: session.id,
            stripe_payment_intent: session.payment_intent,
            previous_budget: currentBudget,
            new_budget: newBudget,
            created_at: new Date().toISOString()
          })
          .catch((err: unknown) => {
            // Log but don't fail - the LiteLLM update is the critical part
            console.warn('Failed to log transaction:', err)
          })
      }

      console.log(`Successfully updated budget for user ${userId}: $${currentBudget} -> $${newBudget}`)

      return new Response(
        JSON.stringify({
          received: true,
          user_id: userId,
          previous_budget: currentBudget,
          new_budget: newBudget,
          amount_added: amountPaid
        }),
        {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        }
      )
    }

    // Handle other event types if needed
    if (event.type === 'payment_intent.succeeded') {
      // Could handle direct payment intents here if not using Checkout
      console.log('Payment intent succeeded:', event.data.object.id)
    }

    return new Response(JSON.stringify({ received: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    })

  } catch (err) {
    console.error('Webhook error:', err)
    return new Response(
      `Webhook Error: ${err instanceof Error ? err.message : 'Unknown error'}`,
      { status: 400 }
    )
  }
})
