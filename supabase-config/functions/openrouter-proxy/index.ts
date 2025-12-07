import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

const MARKUP_RATE = 1.20; // 20% markup
const MIN_BALANCE_BUFFER = 0.05; // Minimum $0.05 balance required

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

    try {
        // Authenticate user via JWT
        const authHeader = req.headers.get("Authorization");
        if (!authHeader?.startsWith("Bearer ")) {
            return new Response(JSON.stringify({ error: "Missing authorization" }), {
                status: 401,
                headers: { "Content-Type": "application/json" }
            });
        }

        const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
        const supabaseAnonKey = Deno.env.get("SUPABASE_ANON_KEY")!;
        const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
        const openRouterKey = Deno.env.get("OPENROUTER_API_KEY")!;

        // User client for auth verification
        const supabaseUser = createClient(supabaseUrl, supabaseAnonKey, {
            global: { headers: { Authorization: authHeader } },
        });

        const { data: { user }, error: authError } = await supabaseUser.auth.getUser();
        if (authError || !user) {
            return new Response(JSON.stringify({ error: "Invalid token" }), {
                status: 401,
                headers: { "Content-Type": "application/json" }
            });
        }

        // Service client for balance operations
        const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey);

        // Check balance
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

        if (Number(profile.credit_balance) < MIN_BALANCE_BUFFER) {
            return new Response(JSON.stringify({
                error: "Insufficient credits",
                balance: profile.credit_balance
            }), {
                status: 402,
                headers: { "Content-Type": "application/json" }
            });
        }

        // Forward request to OpenRouter
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
            // Streaming response - pass through and bill at end
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

                        // Parse SSE for usage data
                        const lines = chunk.split("\n");
                        for (const line of lines) {
                            if (line.startsWith("data: ") && line !== "data: [DONE]") {
                                try {
                                    const data = JSON.parse(line.slice(6));
                                    if (data.usage) {
                                        // OpenRouter provides cost directly in some responses
                                        if (data.usage.total_cost !== undefined) {
                                            totalCost = data.usage.total_cost;
                                        } else if (data.usage.cost !== undefined) {
                                            totalCost = data.usage.cost;
                                        }
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

                    // Bill user after stream completes
                    if (totalCost > 0) {
                        const billableAmount = totalCost * MARKUP_RATE;
                        await supabaseAdmin.rpc("deduct_credits", {
                            p_user_id: user.id,
                            p_amount: billableAmount,
                            p_description: `API usage: ${model}`,
                            p_metadata: {
                                model,
                                raw_cost: totalCost,
                                markup: MARKUP_RATE,
                                prompt_tokens: promptTokens,
                                completion_tokens: completionTokens
                            },
                        });
                        console.log(`Billed user ${user.id}: $${billableAmount.toFixed(6)} (raw: $${totalCost.toFixed(6)})`);
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
                    p_description: `API usage: ${body.model}`,
                    p_metadata: {
                        model: body.model,
                        raw_cost: totalCost,
                        markup: MARKUP_RATE,
                        prompt_tokens: usage.prompt_tokens,
                        completion_tokens: usage.completion_tokens
                    },
                });
                console.log(`Billed user ${user.id}: $${billableAmount.toFixed(6)} (raw: $${totalCost.toFixed(6)})`);
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
