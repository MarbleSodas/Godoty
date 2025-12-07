import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

/**
 * Lemon Squeezy webhook handler for payment processing.
 * Verifies webhook signature and credits user account on successful payments.
 */

async function verifySignature(body: string, signature: string, secret: string): Promise<boolean> {
    const encoder = new TextEncoder();
    const key = await crypto.subtle.importKey(
        "raw",
        encoder.encode(secret),
        { name: "HMAC", hash: "SHA-256" },
        false,
        ["sign"]
    );
    const signatureBuffer = await crypto.subtle.sign("HMAC", key, encoder.encode(body));
    const expectedSignature = Array.from(new Uint8Array(signatureBuffer))
        .map(b => b.toString(16).padStart(2, "0"))
        .join("");
    return signature === expectedSignature;
}

Deno.serve(async (req: Request) => {
    // Only accept POST requests
    if (req.method !== "POST") {
        return new Response("Method not allowed", { status: 405 });
    }

    try {
        const signature = req.headers.get("X-Signature") || req.headers.get("x-signature");
        const body = await req.text();

        // Verify webhook signature
        const secret = Deno.env.get("LEMON_SQUEEZY_WEBHOOK_SECRET");
        if (!secret) {
            console.error("LEMON_SQUEEZY_WEBHOOK_SECRET not configured");
            return new Response("Server configuration error", { status: 500 });
        }

        if (!signature || !(await verifySignature(body, signature, secret))) {
            console.error("Invalid webhook signature");
            return new Response("Invalid signature", { status: 401 });
        }

        const event = JSON.parse(body);
        const eventName = event.meta?.event_name;

        console.log(`Received Lemon Squeezy webhook: ${eventName}`);

        // Handle order_created event (successful payment)
        if (eventName === "order_created") {
            const orderId = event.data?.id;
            const customData = event.meta?.custom_data || {};
            const userId = customData.user_id;

            // Get order total in dollars (API returns cents)
            const totalCents = event.data?.attributes?.total || 0;
            const amount = totalCents / 100;

            if (!userId) {
                console.error("Missing user_id in custom_data for order:", orderId);
                return new Response("Missing user_id in custom_data", { status: 400 });
            }

            if (amount <= 0) {
                console.error("Invalid order amount:", amount);
                return new Response("Invalid order amount", { status: 400 });
            }

            const supabaseAdmin = createClient(
                Deno.env.get("SUPABASE_URL")!,
                Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
            );

            // Idempotency check - prevent double-crediting
            const { data: existing } = await supabaseAdmin
                .from("transactions")
                .select("id")
                .eq("metadata->>lemon_squeezy_order_id", orderId.toString())
                .single();

            if (existing) {
                console.log(`Order ${orderId} already processed, skipping`);
                return new Response("Already processed", { status: 200 });
            }

            // Add credits to user account
            const { data: success, error } = await supabaseAdmin.rpc("add_credits", {
                p_user_id: userId,
                p_amount: amount,
                p_description: `Credit top-up: $${amount.toFixed(2)}`,
                p_metadata: {
                    lemon_squeezy_order_id: orderId,
                    order_number: event.data?.attributes?.order_number,
                    customer_email: event.data?.attributes?.user_email
                },
            });

            if (error) {
                console.error("Failed to add credits:", error);
                return new Response("Failed to add credits", { status: 500 });
            }

            console.log(`Added $${amount.toFixed(2)} credits to user ${userId}`);
            return new Response("Credits added", { status: 200 });
        }

        // Handle other events (refunds, etc.) - log but don't process yet
        console.log(`Unhandled event type: ${eventName}`);
        return new Response("OK", { status: 200 });

    } catch (error) {
        console.error("Webhook processing error:", error);
        return new Response("Internal server error", { status: 500 });
    }
});
