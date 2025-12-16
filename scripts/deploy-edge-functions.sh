#!/bin/bash
# Deploy Supabase Edge Functions for Godoty
# 
# Prerequisites:
#   - Supabase CLI installed: brew install supabase/tap/supabase
#   - Logged into Supabase: supabase login
#   - Project linked: supabase link --project-ref <project-id>

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."
SUPABASE_DEST="$PROJECT_ROOT/supabase"

echo "🚀 Deploying Godoty Supabase Edge Functions..."
echo ""

# Create the supabase/functions directory at the project root if it doesn't exist
# (Supabase CLI expects this structure from the linked project root)
mkdir -p "$SUPABASE_DEST/functions"

# Functions are already in supabase/functions, no need to copy from brain/

# Change to project root where supabase is linked
cd "$PROJECT_ROOT"

# Deploy the generate-litellm-key function
echo "📦 Deploying generate-litellm-key function..."
supabase functions deploy generate-litellm-key --no-verify-jwt

# Deploy the stripe-checkout function (Temporarily disabled - source missing)
# echo "📦 Deploying stripe-checkout function..."
# supabase functions deploy stripe-checkout --no-verify-jwt

# Deploy the stripe-webhook function
echo "📦 Deploying stripe-webhook function..."
supabase functions deploy stripe-webhook --no-verify-jwt

echo ""
echo "✅ Edge Functions deployed successfully!"
echo ""
echo "🔐 Don't forget to set your secrets if you haven't already:"
echo "   supabase secrets set LITELLM_MASTER_KEY=sk-your-master-key"
echo "   supabase secrets set LITELLM_URL=https://your-litellm-proxy.up.railway.app"
echo "   supabase secrets set STRIPE_SECRET_KEY=sk_test_..."
echo "   supabase secrets set STRIPE_WEBHOOK_SECRET=whsec_..."
echo ""
echo "🪝 Set up Stripe Webhook:"
echo "   1. Go to Stripe Dashboard > Developers > Webhooks"
echo "   2. Add endpoint: https://<project-ref>.supabase.co/functions/v1/stripe-webhook"
echo "   3. Select event: checkout.session.completed"
echo "   4. Copy the webhook signing secret and set it above"
echo ""
echo "🗄️  To apply the database migrations:"
echo "   supabase db push"
echo ""
echo "📝 Edge Function URLs:"
echo "   https://<project-ref>.supabase.co/functions/v1/generate-litellm-key"
echo "   https://<project-ref>.supabase.co/functions/v1/stripe-checkout"
echo "   https://<project-ref>.supabase.co/functions/v1/stripe-webhook"
