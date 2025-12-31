#!/usr/bin/env python3
"""
LiteLLM Virtual Key Integration Test Script

This script tests the end-to-end flow of the LiteLLM virtual key system:
1. Key Info Test - Verify key details, budget, and permissions
2. Available Models Test - Check what models are accessible with the key
3. Simple Completion Test - Verify actual API calls work
4. Budget Tracking Test - Confirm spend is being tracked

Usage:
    # Set your virtual key (from Supabase Edge Function or LiteLLM dashboard)
    export LITELLM_TEST_KEY="sk-your-virtual-key"
    
    # Set your LiteLLM proxy URL
    export LITELLM_URL="https://your-litellm-proxy.com"
    
    # Run tests
    python tests/test_litellm_integration.py

Or run with pytest:
    pytest tests/test_litellm_integration.py -v
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

import httpx

# Configuration
LITELLM_URL = os.getenv("LITELLM_URL", "https://litellm-production-150c.up.railway.app")
LITELLM_TEST_KEY = os.getenv("LITELLM_TEST_KEY", "")
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "")  # Optional, for admin tests


@dataclass
class TestResult:
    """Result of a single test."""
    name: str
    passed: bool
    message: str
    details: dict[str, Any] | None = None


class LiteLLMTester:
    """Test suite for LiteLLM virtual key integration."""
    
    def __init__(self, base_url: str, virtual_key: str, master_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.virtual_key = virtual_key
        self.master_key = master_key
        self.client = httpx.AsyncClient(timeout=30.0)
        self.results: list[TestResult] = []
    
    async def close(self):
        await self.client.aclose()
    
    def _headers(self, use_master: bool = False) -> dict[str, str]:
        """Get authorization headers."""
        key = self.master_key if use_master and self.master_key else self.virtual_key
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
    
    async def test_health(self) -> TestResult:
        """Test 1: Check if LiteLLM proxy is reachable."""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            if response.status_code == 200:
                return TestResult(
                    name="Health Check",
                    passed=True,
                    message="LiteLLM proxy is healthy",
                    details=response.json()
                )
            return TestResult(
                name="Health Check",
                passed=False,
                message=f"Unhealthy status: {response.status_code}",
                details={"status_code": response.status_code, "body": response.text}
            )
        except Exception as e:
            return TestResult(
                name="Health Check",
                passed=False,
                message=f"Connection failed: {e}",
            )
    
    async def test_key_info(self) -> TestResult:
        """Test 2: Get information about the virtual key."""
        try:
            response = await self.client.get(
                f"{self.base_url}/key/info",
                headers=self._headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                info = data.get("info", data)
                
                return TestResult(
                    name="Key Info",
                    passed=True,
                    message="Successfully retrieved key info",
                    details={
                        "key_name": info.get("key_name"),
                        "key_alias": info.get("key_alias"),
                        "user_id": info.get("user_id"),
                        "max_budget": info.get("max_budget"),
                        "spend": info.get("spend"),
                        "models": info.get("models"),
                        "expires": info.get("expires"),
                        "soft_budget": info.get("soft_budget"),
                        "budget_reset_at": info.get("budget_reset_at"),
                    }
                )
            
            return TestResult(
                name="Key Info",
                passed=False,
                message=f"Failed to get key info: {response.status_code}",
                details={"status_code": response.status_code, "body": response.text}
            )
        except Exception as e:
            return TestResult(
                name="Key Info",
                passed=False,
                message=f"Error: {e}",
            )
    
    async def test_available_models(self) -> TestResult:
        """Test 3: Get available models for the virtual key."""
        try:
            # Try /models endpoint (OpenAI-compatible)
            response = await self.client.get(
                f"{self.base_url}/models",
                headers=self._headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                models = data.get("data", [])
                model_ids = [m.get("id") for m in models]
                
                return TestResult(
                    name="Available Models",
                    passed=True,
                    message=f"Found {len(models)} available models",
                    details={
                        "model_count": len(models),
                        "model_ids": model_ids[:20],  # First 20 models
                        "has_more": len(models) > 20,
                    }
                )
            
            # Try /model/info endpoint as fallback
            response = await self.client.get(
                f"{self.base_url}/model/info",
                headers=self._headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                return TestResult(
                    name="Available Models",
                    passed=True,
                    message="Retrieved model info (fallback endpoint)",
                    details=data
                )
            
            return TestResult(
                name="Available Models",
                passed=False,
                message=f"Failed to get models: {response.status_code}",
                details={"status_code": response.status_code, "body": response.text}
            )
        except Exception as e:
            return TestResult(
                name="Available Models",
                passed=False,
                message=f"Error: {e}",
            )
    
    async def test_user_models(self) -> TestResult:
        """Test 4: Check models allowed for the user (key-restricted models)."""
        try:
            # First get key info to see user_id
            key_response = await self.client.get(
                f"{self.base_url}/key/info",
                headers=self._headers()
            )
            
            if key_response.status_code != 200:
                return TestResult(
                    name="User Models",
                    passed=False,
                    message="Could not get key info to determine user",
                    details={"status_code": key_response.status_code}
                )
            
            key_data = key_response.json()
            key_info = key_data.get("info", key_data)
            
            # Check if key has model restrictions
            key_models = key_info.get("models")
            user_id = key_info.get("user_id")
            
            result_details = {
                "user_id": user_id,
                "key_model_restrictions": key_models,
            }
            
            # If master key available, get more user info
            if self.master_key:
                user_response = await self.client.get(
                    f"{self.base_url}/user/info?user_id={user_id}",
                    headers=self._headers(use_master=True)
                )
                
                if user_response.status_code == 200:
                    user_data = user_response.json()
                    user_info = user_data.get("user_info", {})
                    result_details["user_max_budget"] = user_info.get("max_budget")
                    result_details["user_spend"] = user_info.get("spend")
                    result_details["user_models"] = user_info.get("models")
            
            if key_models is None or len(key_models) == 0:
                return TestResult(
                    name="User Models",
                    passed=True,
                    message="No model restrictions on key (all models allowed)",
                    details=result_details
                )
            
            return TestResult(
                name="User Models",
                passed=True,
                message=f"Key restricted to {len(key_models)} models",
                details=result_details
            )
        except Exception as e:
            return TestResult(
                name="User Models",
                passed=False,
                message=f"Error: {e}",
            )
    
    async def test_simple_completion(self, model: str = "gpt-4o-mini") -> TestResult:
        """Test 5: Make a simple completion request to verify the key works."""
        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Say 'test ok' and nothing else."}],
                    "max_tokens": 10,
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                usage = data.get("usage", {})
                
                return TestResult(
                    name=f"Completion Test ({model})",
                    passed=True,
                    message="Successfully made API call",
                    details={
                        "model_used": data.get("model"),
                        "response": data.get("choices", [{}])[0].get("message", {}).get("content"),
                        "prompt_tokens": usage.get("prompt_tokens"),
                        "completion_tokens": usage.get("completion_tokens"),
                        "total_tokens": usage.get("total_tokens"),
                    }
                )
            
            error_body = response.text
            try:
                error_json = response.json()
                error_body = error_json
            except:
                pass
            
            return TestResult(
                name=f"Completion Test ({model})",
                passed=False,
                message=f"Request failed: {response.status_code}",
                details={"status_code": response.status_code, "error": error_body}
            )
        except Exception as e:
            return TestResult(
                name=f"Completion Test ({model})",
                passed=False,
                message=f"Error: {e}",
            )
    
    async def test_budget_tracking(self) -> TestResult:
        """Test 6: Verify budget/spend is being tracked after a call."""
        try:
            # Get initial spend
            initial_response = await self.client.get(
                f"{self.base_url}/key/info",
                headers=self._headers()
            )
            
            if initial_response.status_code != 200:
                return TestResult(
                    name="Budget Tracking",
                    passed=False,
                    message="Could not get initial key info",
                )
            
            initial_data = initial_response.json()
            initial_info = initial_data.get("info", initial_data)
            initial_spend = initial_info.get("spend", 0) or 0
            
            # Make a small API call
            await self.client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": "1"}],
                    "max_tokens": 1,
                }
            )
            
            # Small delay for spend to update
            await asyncio.sleep(1)
            
            # Get updated spend
            updated_response = await self.client.get(
                f"{self.base_url}/key/info",
                headers=self._headers()
            )
            
            if updated_response.status_code != 200:
                return TestResult(
                    name="Budget Tracking",
                    passed=False,
                    message="Could not get updated key info",
                )
            
            updated_data = updated_response.json()
            updated_info = updated_data.get("info", updated_data)
            updated_spend = updated_info.get("spend", 0) or 0
            
            if updated_spend > initial_spend:
                return TestResult(
                    name="Budget Tracking",
                    passed=True,
                    message="Spend is being tracked correctly",
                    details={
                        "initial_spend": initial_spend,
                        "updated_spend": updated_spend,
                        "difference": updated_spend - initial_spend,
                        "max_budget": updated_info.get("max_budget"),
                        "remaining": (updated_info.get("max_budget") or 0) - updated_spend
                    }
                )
            
            return TestResult(
                name="Budget Tracking",
                passed=False,
                message="Spend did not increase after API call (may be delayed or not tracked on key)",
                details={
                    "initial_spend": initial_spend,
                    "updated_spend": updated_spend,
                    "note": "Budget tracking may be at USER level, not KEY level"
                }
            )
        except Exception as e:
            return TestResult(
                name="Budget Tracking",
                passed=False,
                message=f"Error: {e}",
            )
    
    async def test_model_access(self, models_to_test: list[str] | None = None) -> list[TestResult]:
        """Test 7: Check which specific models the key can access."""
        if models_to_test is None:
            models_to_test = [
                "gpt-4o",
                "gpt-4o-mini",
                "claude-3-5-sonnet-20241022",
                "claude-3-5-haiku-20241022",
            ]
        
        results = []
        for model in models_to_test:
            try:
                response = await self.client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "1"}],
                        "max_tokens": 1,
                    }
                )
                
                if response.status_code == 200:
                    results.append(TestResult(
                        name=f"Model Access: {model}",
                        passed=True,
                        message=f"✅ {model} - Accessible",
                    ))
                else:
                    error = response.text
                    try:
                        error = response.json().get("error", {}).get("message", error)
                    except:
                        pass
                    results.append(TestResult(
                        name=f"Model Access: {model}",
                        passed=False,
                        message=f"❌ {model} - {response.status_code}",
                        details={"error": error}
                    ))
            except Exception as e:
                results.append(TestResult(
                    name=f"Model Access: {model}",
                    passed=False,
                    message=f"❌ {model} - Error: {e}",
                ))
        
        return results
    
    async def run_all_tests(self, skip_completion: bool = False) -> list[TestResult]:
        """Run all tests and return results."""
        results = []
        
        print("\n🧪 LiteLLM Virtual Key Integration Tests")
        print("=" * 50)
        print(f"📍 Proxy URL: {self.base_url}")
        print(f"🔑 Key: {self.virtual_key[:20]}..." if len(self.virtual_key) > 20 else f"🔑 Key: {self.virtual_key}")
        print("=" * 50)
        
        # Test 1: Health
        result = await self.test_health()
        results.append(result)
        self._print_result(result)
        
        if not result.passed:
            print("\n⚠️  LiteLLM proxy unreachable, skipping remaining tests")
            return results
        
        # Test 2: Key Info
        result = await self.test_key_info()
        results.append(result)
        self._print_result(result)
        
        # Test 3: Available Models
        result = await self.test_available_models()
        results.append(result)
        self._print_result(result)
        
        # Test 4: User Models
        result = await self.test_user_models()
        results.append(result)
        self._print_result(result)
        
        if not skip_completion:
            # Test 5: Simple Completion
            result = await self.test_simple_completion()
            results.append(result)
            self._print_result(result)
            
            # Test 6: Budget Tracking
            result = await self.test_budget_tracking()
            results.append(result)
            self._print_result(result)
            
            # Test 7: Model Access
            print("\n📋 Testing individual model access...")
            model_results = await self.test_model_access()
            results.extend(model_results)
            for r in model_results:
                self._print_result(r, indent=True)
        
        # Summary
        print("\n" + "=" * 50)
        passed = sum(1 for r in results if r.passed)
        total = len(results)
        print(f"📊 Results: {passed}/{total} tests passed")
        
        if passed < total:
            print("\n⚠️  Some tests failed. Check the details above.")
        else:
            print("\n✅ All tests passed!")
        
        return results
    
    def _print_result(self, result: TestResult, indent: bool = False):
        prefix = "  " if indent else ""
        status = "✅" if result.passed else "❌"
        print(f"\n{prefix}{status} {result.name}")
        print(f"{prefix}   {result.message}")
        if result.details:
            for key, value in result.details.items():
                if value is not None:
                    print(f"{prefix}   • {key}: {value}")


async def main():
    """Run the test suite."""
    if not LITELLM_TEST_KEY:
        print("❌ Error: LITELLM_TEST_KEY environment variable not set")
        print("\nUsage:")
        print("  export LITELLM_TEST_KEY='sk-your-virtual-key'")
        print("  export LITELLM_URL='https://your-litellm-proxy.com'  # Optional")
        print("  python tests/test_litellm_integration.py")
        sys.exit(1)
    
    tester = LiteLLMTester(
        base_url=LITELLM_URL,
        virtual_key=LITELLM_TEST_KEY,
        master_key=LITELLM_MASTER_KEY,
    )
    
    try:
        skip_completion = "--skip-completion" in sys.argv
        results = await tester.run_all_tests(skip_completion=skip_completion)
        
        # Exit with error code if any tests failed
        failed = any(not r.passed for r in results)
        sys.exit(1 if failed else 0)
    finally:
        await tester.close()


# Pytest-compatible test functions
import pytest

@pytest.fixture
async def tester():
    """Create a tester instance for pytest."""
    if not LITELLM_TEST_KEY:
        pytest.skip("LITELLM_TEST_KEY not set")
    
    t = LiteLLMTester(
        base_url=LITELLM_URL,
        virtual_key=LITELLM_TEST_KEY,
        master_key=LITELLM_MASTER_KEY,
    )
    yield t
    await t.close()


@pytest.mark.asyncio
async def test_health(tester):
    result = await tester.test_health()
    assert result.passed, result.message


@pytest.mark.asyncio
async def test_key_info(tester):
    result = await tester.test_key_info()
    assert result.passed, result.message


@pytest.mark.asyncio
async def test_available_models(tester):
    result = await tester.test_available_models()
    assert result.passed, result.message


@pytest.mark.asyncio
async def test_user_models(tester):
    result = await tester.test_user_models()
    assert result.passed, result.message


@pytest.mark.asyncio
async def test_simple_completion(tester):
    result = await tester.test_simple_completion()
    assert result.passed, result.message


if __name__ == "__main__":
    asyncio.run(main())
