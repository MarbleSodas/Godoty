import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";
import Stripe from "https://esm.sh/stripe@20.0.0?target=denonext";

/**
 * Stripe Webhook Handler - The "Dumb Pipe"
 * 
 * This function does ONLY two things:
 * 1. Verify the Stripe signature (security)
 * 2. Hand off data to the database RPC (logic lives in Postgres)
 * 
 * Credit amount comes from:
 * 1. Stripe Price metadata (credit_amount field) - preferred
 * 2. Fallback: hardcoded CREDIT_MAP based on amount
 * 
 * Idempotency is handled by the database via external_id (Stripe session ID).
 */

// Fallback credit mapping for known packs (when metadata not set)
const CREDIT_MAP: Record<number, number> = {
    500: 5,    // $5.00 -> 5 credits
    1000: 12,  // $10.00 -> 12 credits
    2000: 25   // $20.00 -> 25 credits
};

Deno.serve(async (req: Request) => {
    if (req.method !== "POST") {
        return new Response("Method not allowed", { status: 405 });
    }

    const stripeSecretKey = Deno.env.get("STRIPE_SECRET_KEY");
    const webhookSecret = Deno.env.get("STRIPE_WEBHOOK_SECRET");

    if (!stripeSecretKey || !webhookSecret) {
        console.error("Stripe configuration missing");
        return new Response("Server configuration error", { status: 500 });
    }

    const stripe = new Stripe(stripeSecretKey, { apiVersion: "2025-11-17.clover" });
    const cryptoProvider = Stripe.createSubtleCryptoProvider();

    const signature = req.headers.get("Stripe-Signature")!;
    const body = await req.text();

    try {
        // 1. Verify Signature (Security)
        const event = await stripe.webhooks.constructEventAsync(
            body,
            signature,
            webhookSecret,
            undefined,
            cryptoProvider
        );

        console.log(`Received Stripe webhook: ${event.type}`);

        // 2. Handle "Paid" Event
        if (event.type === "checkout.session.completed") {
            const session = event.data.object as Stripe.Checkout.Session;
            const userId = session.client_reference_id; // The Supabase User UUID

            if (!userId) {
                console.error("Missing client_reference_id for session:", session.id);
                return new Response("Missing user ID", { status: 400 });
            }

            // Get credit amount - try metadata first, then fallback to CREDIT_MAP
            let credits = 0;
            const amountCents = session.amount_total || 0;

            // Try to get credits from line items metadata
            try {
                const lineItems = await stripe.checkout.sessions.listLineItems(session.id, {
                    expand: ['data.price']
                });
                
                if (lineItems.data.length > 0) {
                    const price = lineItems.data[0].price;
                    if (price?.metadata?.credit_amount) {
                        credits = parseInt(price.metadata.credit_amount, 10);
                        console.log(`Credits from metadata: ${credits}`);
                    }
                }
            } catch (err) {
                console.warn("Could not fetch line items metadata:", err);
            }

            // Fallback to CREDIT_MAP if metadata not available
            if (credits <= 0) {
                if (CREDIT_MAP[amountCents]) {
                    credits = CREDIT_MAP[amountCents];
                    console.log(`Credits from fallback map: ${credits} (for ${amountCents} cents)`);
                } else {
                    // Last resort: 1 credit per dollar
                    credits = Math.floor(amountCents / 100);
                    console.log(`Credits from amount fallback: ${credits}`);
                }
            }

            if (credits <= 0) {
                console.error("Invalid credit amount:", credits);
                return new Response("Invalid amount", { status: 400 });
            }

            // 3. Call Database RPC (Logic lives in Postgres)
            // Idempotency is handled by external_id in the database
            const supabase = createClient(
                Deno.env.get("SUPABASE_URL")!,
                Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
            );

            const { data: wasAdded, error } = await supabase.rpc("add_credits", {
                p_user_id: userId,
                p_amount: credits,
                p_description: `Stripe purchase: ${credits} credits`,
                p_metadata: {
                    stripe_session_id: session.id,
                    stripe_payment_intent: session.payment_intent,
                    amount_cents: amountCents,
                },
                p_external_id: session.id,  // Idempotency key
            });

            if (error) {
                console.error("Failed to add credits:", error);
                return new Response("Database error", { status: 500 });
            }

            if (wasAdded) {
                console.log(`Added ${credits} credits to user ${userId} (session: ${session.id})`);
            } else {
                console.log(`Duplicate webhook ignored for session: ${session.id}`);
            }
        }

        return new Response("OK", { status: 200 });

    } catch (err) {
        console.error("Webhook error:", err);
        return new Response((err as Error).message, { status: 400 });
    }
});
