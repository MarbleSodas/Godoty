import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

/**
 * Chat Proxy - The "Thin Router" for LLM Requests
 * 
 * This function handles streaming LLM requests:
 * 1. Auth check (via JWT)
 * 2. Balance check (fail fast with 402)
 * 3. Stream response from OpenRouter
 * 4. Deduct credits after stream completes
 * 
 * OpenRouter API key is retrieved from Supabase Vault for security.
 */

const MARKUP_RATE = 1.50; // 50% markup

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

        const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
        const supabaseAnonKey = Deno.env.get("SUPABASE_ANON_KEY")!;
        const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

        // User client for auth verification
        const supabaseUser = createClient(supabaseUrl, supabaseAnonKey, {
            global: { headers: { Authorization: authHeader } },
        });

        const { data: { user }, error: authError } = await supabaseUser.auth.getUser();
        if (authError || !user) {
            console.error("Auth error:", authError?.message || "No user found");
            return new Response(JSON.stringify({ 
                error: "Invalid token",
                details: authError?.message || "Token validation failed"
            }), {
                status: 401,
                headers: { "Content-Type": "application/json" }
            });
        }

        // Service client for balance operations
        const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey);

        // 2. Check Balance (Fail fast)
        const { data: profile, error: profileError } = await supabaseAdmin
            .from("profiles")
            .select("credit_balance")
            .eq("id", user.id)
            .single();

        if (profileError || !profile) {
            return new Response(JSON.stringify({ error: "Profile not found" }), {
                status: 404,
                headers: { "Content-Type": "application/json" }
            });
        }

        const balance = Number(profile.credit_balance);
        if (balance <= 0) {
            return new Response(JSON.stringify({
                error: "Insufficient credits",
                balance: profile.credit_balance
            }), {
                status: 402,
                headers: { "Content-Type": "application/json" }
            });
        }

        // 3. Get OpenRouter Key
        // Can use Supabase Vault via RPC, or env var for simplicity
        // 3. Get OpenRouter Key from Vault (Secure)
        // We use the admin client (service role) to call the secured RPC
        const { data: openRouterKey, error: secretError } = await supabaseAdmin.rpc("get_openrouter_key");

        if (secretError || !openRouterKey) {
            console.error("Failed to retrieve API key from Vault:", {
                error: secretError?.message || "Unknown error",
                code: secretError?.code,
                details: secretError?.details,
                hint: secretError?.hint,
                hasKey: !!openRouterKey
            });
            return new Response(JSON.stringify({ 
                error: "Configuration error",
                details: secretError?.message || "API key not found in Vault. Please add 'openrouter_api_key' secret to Supabase Vault."
            }), {
                status: 500,
                headers: { "Content-Type": "application/json" }
            });
        }

        // 4. Forward request to OpenRouter
        const body = await req.json();
        const isStreaming = body.stream === true;

        const openRouterResponse = await fetch("https://openrouter.ai/api/v1/chat/completions", {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${openRouterKey}`,
                "Content-Type": "application/json",
                "HTTP-Referer": "https://godoty.app",
                "X-Title": "Godoty",
            },
            body: JSON.stringify({
                ...body,
                stream_options: isStreaming ? { include_usage: true } : undefined,
            }),
        });

        if (!openRouterResponse.ok) {
            const error = await openRouterResponse.text();
            return new Response(error, {
                status: openRouterResponse.status,
                headers: { "Content-Type": "application/json" }
            });
        }

        if (isStreaming) {
            // 5. Streaming - pipe through and capture usage at end
            const { readable, writable } = new TransformStream();
            const writer = writable.getWriter();
            const decoder = new TextDecoder();

            let totalCost = 0;
            let promptTokens = 0;
            let completionTokens = 0;
            const model = body.model || "unknown";

            (async () => {
                const reader = openRouterResponse.body!.getReader();
                try {
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;

                        const chunk = decoder.decode(value);
                        await writer.write(value);

                        // Parse SSE for usage data (in final chunk)
                        const lines = chunk.split("\n");
                        for (const line of lines) {
                            if (line.startsWith("data: ") && line !== "data: [DONE]") {
                                try {
                                    const data = JSON.parse(line.slice(6));
                                    if (data.usage) {
                                        totalCost = data.usage.total_cost || data.usage.cost || 0;
                                        promptTokens = data.usage.prompt_tokens || promptTokens;
                                        completionTokens = data.usage.completion_tokens || completionTokens;
                                    }
                                } catch {
                                    // Ignore parse errors in SSE
                                }
                            }
                        }
                    }
                } finally {
                    await writer.close();

                    // 6. Deduct Credits asynchronously after stream
                    if (totalCost > 0) {
                        const billableAmount = totalCost * MARKUP_RATE;
                        await supabaseAdmin.rpc("deduct_credits", {
                            p_user_id: user.id,
                            p_amount: billableAmount,
                            p_description: `Chat: ${model}`,
                            p_metadata: {
                                model,
                                raw_cost: totalCost,
                                markup: MARKUP_RATE,
                                prompt_tokens: promptTokens,
                                completion_tokens: completionTokens
                            },
                        });
                        console.log(`Billed ${user.id}: $${billableAmount.toFixed(6)}`);
                    }
                }
            })();

            return new Response(readable, {
                headers: {
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*",
                },
            });
        } else {
            // Non-streaming - bill immediately
            const data = await openRouterResponse.json();
            const usage = data.usage || {};
            const totalCost = usage.total_cost || usage.cost || 0;

            if (totalCost > 0) {
                const billableAmount = totalCost * MARKUP_RATE;
                await supabaseAdmin.rpc("deduct_credits", {
                    p_user_id: user.id,
                    p_amount: billableAmount,
                    p_description: `Chat: ${body.model}`,
                    p_metadata: {
                        model: body.model,
                        raw_cost: totalCost,
                        markup: MARKUP_RATE,
                        prompt_tokens: usage.prompt_tokens,
                        completion_tokens: usage.completion_tokens
                    },
                });
                console.log(`Billed ${user.id}: $${billableAmount.toFixed(6)}`);
            }

            return new Response(JSON.stringify(data), {
                headers: {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
            });
        }
    } catch (error) {
        console.error("Proxy error:", error);
        return new Response(JSON.stringify({ error: "Internal server error" }), {
            status: 500,
            headers: { "Content-Type": "application/json" }
        });
    }
});
