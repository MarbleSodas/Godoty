import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

/**
 * Creates a Lemon Squeezy checkout URL for credit top-ups.
 * Embeds user ID in custom_data for webhook processing.
 */

interface CheckoutRequest {
    variant_id: string;
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
        // Authenticate user
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

        const { variant_id }: CheckoutRequest = await req.json();
        if (!variant_id) {
            return new Response(JSON.stringify({ error: "Missing variant_id" }), {
                status: 400,
                headers: { "Content-Type": "application/json" }
            });
        }

        const lsApiKey = Deno.env.get("LEMON_SQUEEZY_API_KEY");
        const storeId = Deno.env.get("LEMON_SQUEEZY_STORE_ID");

        if (!lsApiKey || !storeId) {
            console.error("Lemon Squeezy not configured");
            return new Response(JSON.stringify({ error: "Payment system not configured" }), {
                status: 500,
                headers: { "Content-Type": "application/json" }
            });
        }

        // Create checkout via Lemon Squeezy API
        const response = await fetch("https://api.lemonsqueezy.com/v1/checkouts", {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${lsApiKey}`,
                "Content-Type": "application/vnd.api+json",
                "Accept": "application/vnd.api+json",
            },
            body: JSON.stringify({
                data: {
                    type: "checkouts",
                    attributes: {
                        checkout_data: {
                            custom: {
                                user_id: user.id
                            },
                            email: user.email,
                        },
                    },
                    relationships: {
                        store: {
                            data: { type: "stores", id: storeId }
                        },
                        variant: {
                            data: { type: "variants", id: variant_id }
                        },
                    },
                },
            }),
        });

        if (!response.ok) {
            const errorData = await response.text();
            console.error("Lemon Squeezy API error:", errorData);
            return new Response(JSON.stringify({ error: "Failed to create checkout" }), {
                status: 500,
                headers: { "Content-Type": "application/json" }
            });
        }

        const data = await response.json();
        const checkoutUrl = data.data?.attributes?.url;

        if (!checkoutUrl) {
            return new Response(JSON.stringify({ error: "No checkout URL returned" }), {
                status: 500,
                headers: { "Content-Type": "application/json" }
            });
        }

        console.log(`Created checkout for user ${user.id}: ${checkoutUrl}`);

        return new Response(JSON.stringify({ url: checkoutUrl }), {
            headers: {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
        });

    } catch (error) {
        console.error("Checkout creation error:", error);
        return new Response(JSON.stringify({ error: "Internal server error" }), {
            status: 500,
            headers: { "Content-Type": "application/json" }
        });
    }
});
