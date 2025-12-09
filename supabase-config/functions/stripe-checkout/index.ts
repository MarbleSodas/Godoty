import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";
import Stripe from "https://esm.sh/stripe@14?target=denonext";

/**
 * Creates a Stripe Checkout Session for credit top-ups.
 * Uses client_reference_id to pass user UUID (the "Postgres-Centric" approach).
 * Credit amount is stored in Stripe Price metadata, not in this function.
 */

interface CheckoutRequest {
    price_id: string;
}

Deno.serve(async (req: Request) => {
    // CORS handling
    if (req.method === "OPTIONS") {
        return new Response(null, {
            headers: {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Authorization, Content-Type",
            },
        });
    }

    if (req.method !== "POST") {
        return new Response("Method not allowed", { status: 405 });
    }

    try {
        // 1. Auth Check
        const authHeader = req.headers.get("Authorization");
        if (!authHeader?.startsWith("Bearer ")) {
            return new Response(JSON.stringify({ error: "Unauthorized" }), {
                status: 401,
                headers: { "Content-Type": "application/json" }
            });
        }

        const supabase = createClient(
            Deno.env.get("SUPABASE_URL")!,
            Deno.env.get("SUPABASE_ANON_KEY")!,
            { global: { headers: { Authorization: authHeader } } }
        );

        const { data: { user }, error: authError } = await supabase.auth.getUser();
        if (authError || !user) {
            return new Response(JSON.stringify({ error: "Invalid token" }), {
                status: 401,
                headers: { "Content-Type": "application/json" }
            });
        }

        const { price_id }: CheckoutRequest = await req.json();
        if (!price_id) {
            return new Response(JSON.stringify({ error: "Missing price_id" }), {
                status: 400,
                headers: { "Content-Type": "application/json" }
            });
        }

        const stripeSecretKey = Deno.env.get("STRIPE_SECRET_KEY");
        if (!stripeSecretKey) {
            console.error("STRIPE_SECRET_KEY not configured");
            return new Response(JSON.stringify({ error: "Payment system not configured" }), {
                status: 500,
                headers: { "Content-Type": "application/json" }
            });
        }

        const stripe = new Stripe(stripeSecretKey, {
            apiVersion: "2024-11-20",
        });

        // 2. Create Checkout Session
        // Uses client_reference_id for user tracking (cleaner than metadata)
        const session = await stripe.checkout.sessions.create({
            mode: "payment",
            payment_method_types: ["card"],
            line_items: [{ price: price_id, quantity: 1 }],
            client_reference_id: user.id, // The Supabase User UUID
            customer_email: user.email,
            success_url: "https://godoty.app/payment/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url: "https://godoty.app/payment/cancelled",
        });

        if (!session.url) {
            return new Response(JSON.stringify({ error: "No checkout URL returned" }), {
                status: 500,
                headers: { "Content-Type": "application/json" }
            });
        }

        console.log(`Created Stripe checkout for user ${user.id}: ${session.id}`);

        return new Response(JSON.stringify({ url: session.url }), {
            headers: {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
        });

    } catch (error) {
        console.error("Checkout creation error:", error);
        const errorMessage = error instanceof Error ? error.message : "Unknown error";
        return new Response(JSON.stringify({ error: errorMessage, details: error }), {
            status: 500,
            headers: { "Content-Type": "application/json" }
        });
    }
});
