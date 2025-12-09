import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";
import Stripe from "https://esm.sh/stripe@14?target=denonext";

/**
 * Stripe Webhook Handler - The "Dumb Pipe"
 * 
 * This function does ONLY two things:
 * 1. Verify the Stripe signature (security)
 * 2. Hand off data to the database RPC (logic lives in Postgres)
 * 
 * Credit amount comes from Stripe Price metadata (configured in Stripe Dashboard).
 */

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

    const stripe = new Stripe(stripeSecretKey, { apiVersion: "2024-11-20" });
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

            // Get credit amount from line items
            // In production, configure credit_amount in Stripe Price metadata
            // Fallback: Map amount_total to credits based on known packs
            const amountCents = session.amount_total || 0;
            let credits = 0;

            // Map cents to credits (hardcoded fallback)
            const CREDIT_MAP: Record<number, number> = {
                500: 5,    // $5.00 -> 5 credits
                1000: 12,  // $10.00 -> 12 credits
                2000: 25   // $20.00 -> 25 credits
            };

            if (CREDIT_MAP[amountCents]) {
                credits = CREDIT_MAP[amountCents];
            } else {
                // Fallback for custom amounts (optional)
                credits = Math.floor(amountCents / 100);
            }

            if (credits <= 0) {
                console.error("Invalid credit amount:", credits);
                return new Response("Invalid amount", { status: 400 });
            }

            // 3. Call Database RPC (Logic lives in Postgres)
            const supabase = createClient(
                Deno.env.get("SUPABASE_URL")!,
                Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
            );

            const { error } = await supabase.rpc("add_credits", {
                p_user_id: userId,
                p_amount: credits,
                p_description: `Stripe purchase: $${credits.toFixed(2)}`,
                p_metadata: {
                    stripe_session_id: session.id,
                    stripe_payment_intent: session.payment_intent,
                },
            });

            if (error) {
                console.error("Failed to add credits:", error);
                return new Response("Database error", { status: 500 });
            }

            console.log(`Added ${credits} credits to user ${userId}`);
        }

        return new Response("OK", { status: 200 });

    } catch (err) {
        console.error("Webhook error:", err);
        return new Response((err as Error).message, { status: 400 });
    }
});
