import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";
import Stripe from "https://esm.sh/stripe@20.0.0?target=denonext";

/**
 * Stripe Checkout - Creates checkout sessions for credit purchases
 * 
 * This function:
 * 1. Verifies user authentication via JWT
 * 2. Creates a Stripe Checkout Session
 * 3. Sets client_reference_id to user UUID (for webhook reconciliation)
 * 4. Returns checkout URL to open in browser
 */


const corsHeaders = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

Deno.serve(async (req: Request) => {
    // CORS handling
    if (req.method === "OPTIONS") {
        return new Response("ok", { headers: corsHeaders });
    }

    if (req.method !== "POST") {
        return new Response("Method not allowed", {
            status: 405,
            headers: corsHeaders
        });
    }

    try {
        // 1. Auth Check
        const authHeader = req.headers.get("Authorization");
        if (!authHeader?.startsWith("Bearer ")) {
            return new Response(JSON.stringify({ error: "Unauthorized" }), {
                status: 401,
                headers: { ...corsHeaders, "Content-Type": "application/json" }
            });
        }

        const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
        const supabaseAnonKey = Deno.env.get("SUPABASE_ANON_KEY")!;

        // Verify user with their JWT
        const supabaseUser = createClient(supabaseUrl, supabaseAnonKey, {
            global: { headers: { Authorization: authHeader } },
        });

        const { data: { user }, error: authError } = await supabaseUser.auth.getUser();
        if (authError || !user) {
            console.error("Auth error:", authError);
            return new Response(JSON.stringify({ error: "Invalid token" }), {
                status: 401,
                headers: { ...corsHeaders, "Content-Type": "application/json" }
            });
        }

        // 2. Get request body
        const body = await req.json();
        const priceId = body.price_id;

        if (!priceId) {
            return new Response(JSON.stringify({ error: "price_id is required" }), {
                status: 400,
                headers: { ...corsHeaders, "Content-Type": "application/json" }
            });
        }

        // 3. Initialize Stripe
        const stripeSecretKey = Deno.env.get("STRIPE_SECRET_KEY");
        if (!stripeSecretKey) {
            console.error("STRIPE_SECRET_KEY not configured");
            return new Response(JSON.stringify({ error: "Stripe not configured" }), {
                status: 500,
                headers: { ...corsHeaders, "Content-Type": "application/json" }
            });
        }

        const stripe = new Stripe(stripeSecretKey, { apiVersion: "2025-11-17.clover" });

        // 4. Create Checkout Session
        // Success/cancel URLs - these can be customized per-environment
        const successUrl = Deno.env.get("STRIPE_SUCCESS_URL") || "https://godoty.app/checkout/success";
        const cancelUrl = Deno.env.get("STRIPE_CANCEL_URL") || "https://godoty.app/checkout/cancel";

        const session = await stripe.checkout.sessions.create({
            mode: "payment",
            payment_method_types: ["card"],
            line_items: [
                {
                    price: priceId,
                    quantity: 1,
                },
            ],
            // CRITICAL: This links the Stripe session to the Supabase user
            // The webhook uses this to credit the correct account
            client_reference_id: user.id,
            customer_email: user.email,
            success_url: successUrl,
            cancel_url: cancelUrl,
            metadata: {
                supabase_user_id: user.id,
                user_email: user.email || "",
            },
        });

        console.log(`Checkout session created: ${session.id} for user ${user.id}`);

        return new Response(JSON.stringify({
            success: true,
            url: session.url,
            session_id: session.id,
        }), {
            headers: {
                ...corsHeaders,
                "Content-Type": "application/json",
            },
        });

    } catch (error) {
        console.error("Checkout error:", error);
        return new Response(JSON.stringify({
            error: error instanceof Error ? error.message : "Failed to create checkout"
        }), {
            status: 500,
            headers: { ...corsHeaders, "Content-Type": "application/json" }
        });
    }
});
