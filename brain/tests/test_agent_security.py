"""Security tests for agent.py API key handling."""

import os
import pytest

from app.agents.agent import _get_model, set_jwt_token


class TestAgentSecurity:
    """Test API key validation and security."""

    def test_get_model_requires_api_key(self):
        """Test that _get_model raises ValueError when no API key is provided."""
        # Clear environment
        original_key = os.environ.pop("GODOTY_API_KEY", None)

        try:
            with pytest.raises(ValueError, match="API key is required"):
                _get_model(jwt_token=None)
        finally:
            # Restore environment
            if original_key:
                os.environ["GODOTY_API_KEY"] = original_key

    def test_get_model_works_with_env_var(self):
        """Test that _get_model works with GODOTY_API_KEY environment variable."""
        # Set environment variable
        os.environ["GODOTY_API_KEY"] = "test-key-from-env"
        try:
            model = _get_model(jwt_token=None)
            assert model is not None
            assert model.api_key == "test-key-from-env"
        finally:
            os.environ.pop("GODOTY_API_KEY", None)

    def test_get_model_prefers_jwt_token(self):
        """Test that jwt_token takes precedence over environment variable."""
        os.environ["GODOTY_API_KEY"] = "env-key"
        try:
            model = _get_model(jwt_token="jwt-token-key")
            assert model is not None
            assert model.api_key == "jwt-token-key"
        finally:
            os.environ.pop("GODOTY_API_KEY", None)

    def test_no_hardcoded_fallback(self):
        """Test that there is no hardcoded fallback API key."""
        # Clear environment
        original_key = os.environ.pop("GODOTY_API_KEY", None)

        try:
            # This should raise ValueError, not return a model with hardcoded key
            with pytest.raises(ValueError, match="API key is required"):
                _get_model(jwt_token=None)
        finally:
            # Restore environment
            if original_key:
                os.environ["GODOTY_API_KEY"] = original_key

    def test_jwt_token_global_state(self):
        """Test JWT token global state management."""
        set_jwt_token("global-jwt-token")
        try:
            model = _get_model()
            assert model is not None
            assert model.api_key == "global-jwt-token"
        finally:
            set_jwt_token(None)  # Clear state

    def test_model_id_parameter(self):
        """Test that model_id parameter is respected."""
        os.environ["GODOTY_API_KEY"] = "test-key"
        try:
            model = _get_model(jwt_token=None, model_id="custom-model-id")
            assert model is not None
            assert model.id == "custom-model-id"
        finally:
            os.environ.pop("GODOTY_API_KEY", None)

    def test_base_url_defaults(self):
        """Test that base_url has sensible defaults."""
        os.environ["GODOTY_API_KEY"] = "test-key"
        try:
            model = _get_model(jwt_token=None)
            assert model is not None
            # Default URL should be set
            assert model.base_url is not None
        finally:
            os.environ.pop("GODOTY_API_KEY", None)

    def test_base_url_from_env(self):
        """Test that base_url can be overridden via environment variable."""
        os.environ["GODOTY_API_KEY"] = "test-key"
        os.environ["GODOTY_LITELLM_BASE_URL"] = "https://custom-litellm.example.com"
        try:
            model = _get_model(jwt_token=None)
            assert model is not None
            assert model.base_url == "https://custom-litellm.example.com"
        finally:
            os.environ.pop("GODOTY_API_KEY", None)
            os.environ.pop("GODOTY_LITELLM_BASE_URL", None)
