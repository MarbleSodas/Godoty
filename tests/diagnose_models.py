#!/usr/bin/env python3
"""
Quick diagnostic script for LiteLLM virtual key model access issues.

This script specifically diagnoses why models might not be fetching properly
with virtual keys. Common issues include:
1. Key has no models array (should have access to all)
2. Key has empty models array (might block all)
3. Models in key don't match actual model names in LiteLLM config
4. User-level restrictions override key permissions

Usage:
    export LITELLM_TEST_KEY="sk-your-virtual-key"
    python tests/diagnose_models.py
"""

import asyncio
import os
import sys
import json

import httpx

LITELLM_URL = os.getenv("LITELLM_URL", "https://litellm-production-150c.up.railway.app")
LITELLM_TEST_KEY = os.getenv("LITELLM_TEST_KEY", "")
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "")


async def diagnose():
    if not LITELLM_TEST_KEY:
        print("❌ LITELLM_TEST_KEY not set")
        print("Usage: export LITELLM_TEST_KEY='sk-...' && python tests/diagnose_models.py")
        sys.exit(1)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {"Authorization": f"Bearer {LITELLM_TEST_KEY}"}
        master_headers = {"Authorization": f"Bearer {LITELLM_MASTER_KEY}"} if LITELLM_MASTER_KEY else None
        
        print("\n🔍 LITELLM VIRTUAL KEY MODEL DIAGNOSTIC")
        print("=" * 60)
        print(f"Proxy URL: {LITELLM_URL}")
        print(f"Key: {LITELLM_TEST_KEY[:25]}..." if len(LITELLM_TEST_KEY) > 25 else f"Key: {LITELLM_TEST_KEY}")
        print("=" * 60)
        
        # 1. Check key info
        print("\n📌 Step 1: Fetching Key Info...")
        try:
            resp = await client.get(f"{LITELLM_URL}/key/info", headers=headers)
            if resp.status_code == 200:
                key_data = resp.json()
                key_info = key_data.get("info", key_data)
                
                print(f"   ✓ Key found")
                print(f"   • user_id: {key_info.get('user_id')}")
                print(f"   • key_name: {key_info.get('key_name')}")
                
                key_models = key_info.get('models')
                print(f"\n   📋 Key Model Restrictions:")
                if key_models is None:
                    print(f"   • models: None (UNRESTRICTED - all models allowed)")
                elif isinstance(key_models, list) and len(key_models) == 0:
                    print(f"   • models: [] (EMPTY ARRAY - may block all models!)")
                    print(f"   ⚠️  WARNING: An empty models array might block access to all models")
                else:
                    print(f"   • models: {key_models}")
                    print(f"   ℹ️  Key is restricted to {len(key_models)} specific models")
                
                # Check spend/budget
                print(f"\n   💰 Budget Info:")
                print(f"   • max_budget: {key_info.get('max_budget')}")
                print(f"   • spend: {key_info.get('spend')}")
                
                user_id = key_info.get('user_id')
            else:
                print(f"   ❌ Failed to get key info: {resp.status_code}")
                print(f"   Response: {resp.text}")
                return
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return
        
        # 2. Check user info (if master key available)
        if master_headers and user_id:
            print(f"\n📌 Step 2: Fetching User Info (user_id: {user_id})...")
            try:
                resp = await client.get(
                    f"{LITELLM_URL}/user/info?user_id={user_id}",
                    headers=master_headers
                )
                if resp.status_code == 200:
                    user_data = resp.json()
                    user_info = user_data.get("user_info", {})
                    
                    print(f"   ✓ User found")
                    print(f"   • user_email: {user_info.get('user_email')}")
                    print(f"   • max_budget: {user_info.get('max_budget')}")
                    print(f"   • spend: {user_info.get('spend')}")
                    
                    user_models = user_info.get('models')
                    print(f"\n   📋 User Model Restrictions:")
                    if user_models is None:
                        print(f"   • models: None (no user-level restrictions)")
                    elif isinstance(user_models, list) and len(user_models) == 0:
                        print(f"   • models: [] (empty - may use defaults)")
                    else:
                        print(f"   • models: {user_models}")
                else:
                    print(f"   ⚠️  Could not get user info: {resp.status_code}")
            except Exception as e:
                print(f"   ⚠️  Error getting user info: {e}")
        else:
            print(f"\n📌 Step 2: Skipping user info (no LITELLM_MASTER_KEY)")
        
        # 3. Check /models endpoint
        print(f"\n📌 Step 3: Fetching Available Models via /models endpoint...")
        try:
            resp = await client.get(f"{LITELLM_URL}/models", headers=headers)
            if resp.status_code == 200:
                models_data = resp.json()
                models = models_data.get("data", [])
                model_ids = [m.get("id") for m in models]
                
                print(f"   ✓ Found {len(models)} models")
                print(f"   Models: {model_ids[:10]}{'...' if len(models) > 10 else ''}")
                
                if len(models) == 0:
                    print(f"\n   ⚠️  WARNING: No models returned!")
                    print(f"   This could mean:")
                    print(f"   1. Key has empty models[] array restriction")
                    print(f"   2. LiteLLM config has no models defined")
                    print(f"   3. User/team restrictions blocking access")
            else:
                print(f"   ❌ Failed: {resp.status_code}")
                print(f"   Response: {resp.text[:500]}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # 4. Check /model/info endpoint
        print(f"\n📌 Step 4: Fetching Model Info via /model/info endpoint...")
        try:
            resp = await client.get(f"{LITELLM_URL}/model/info", headers=headers)
            if resp.status_code == 200:
                model_info = resp.json()
                data = model_info.get("data", [])
                print(f"   ✓ Found {len(data)} model configs")
                for m in data[:5]:
                    print(f"   • {m.get('model_name')}: {m.get('litellm_params', {}).get('model')}")
            else:
                print(f"   ⚠️  Status: {resp.status_code}")
        except Exception as e:
            print(f"   ⚠️  Error: {e}")
        
        # 5. Try actual model calls
        print(f"\n📌 Step 5: Testing Actual Model Calls...")
        test_models = ["gpt-4o-mini", "gpt-4o", "claude-3-5-sonnet-20241022"]
        
        for model in test_models:
            try:
                resp = await client.post(
                    f"{LITELLM_URL}/chat/completions",
                    headers={**headers, "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "1"}],
                        "max_tokens": 1,
                    }
                )
                if resp.status_code == 200:
                    print(f"   ✅ {model} - Works!")
                else:
                    error = resp.text
                    try:
                        error = resp.json().get("error", {}).get("message", error)
                    except:
                        pass
                    print(f"   ❌ {model} - {resp.status_code}: {error[:100]}")
            except Exception as e:
                print(f"   ❌ {model} - Error: {e}")
        
        # Summary
        print("\n" + "=" * 60)
        print("🔧 COMMON FIXES:")
        print("=" * 60)
        print("""
1. If key has empty models[]:
   - Regenerate key without models restriction, OR
   - Set models to null/undefined when creating key

2. If /models returns empty:
   - Check LiteLLM config.yaml has model_list defined
   - Ensure models are not team/org restricted

3. If specific model fails:
   - Verify model name matches exactly in LiteLLM config
   - Check API key for that provider is configured

4. To generate key with all models access:
   POST /key/generate
   {
     "user_id": "user-uuid",
     "duration": null,
     "models": null  // null = all models, NOT []
   }
""")


if __name__ == "__main__":
    asyncio.run(diagnose())
