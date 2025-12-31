"""Security tests for main.py WebSocket origin validation."""

import os
import pytest

# We need to import the function directly from the module
from app.main import _validate_ws_origin, ALLOWED_WS_ORIGINS


class TestWebSocketSecurity:
    """Test WebSocket origin validation security."""

    def test_validate_ws_origin_rejects_null_origin_by_default(self):
        """Test that None origin is rejected without client_type."""
        assert _validate_ws_origin(None) is False, \
            "None origin should be rejected by default"

    def test_validate_ws_origin_allows_godot_plugin(self):
        """Test that Godot plugin with None origin is allowed with client_type='godot'."""
        assert _validate_ws_origin(None, client_type="godot") is True, \
            "Godot plugin (localhost) should be allowed"

    def test_validate_ws_origin_rejects_tauri_without_origin(self):
        """Test that Tauri without origin header is rejected."""
        assert _validate_ws_origin(None, client_type="tauri") is False, \
            "Tauri without origin header should be rejected"

    def test_validate_ws_origin_rejects_unknown_client_without_origin(self):
        """Test that unknown client types without origin are rejected."""
        assert _validate_ws_origin(None, client_type="unknown") is False, \
            "Unknown client without origin should be rejected"

    def test_validate_ws_origin_allows_valid_tauri_origin(self):
        """Test that valid Tauri origins are accepted."""
        for origin in ["tauri://localhost", "http://localhost:1420"]:
            assert _validate_ws_origin(origin, client_type="tauri") is True, \
                f"Valid origin '{origin}' should be accepted"

    def test_validate_ws_origin_allows_dev_server_origin(self):
        """Test that Vite dev server origins are accepted."""
        for origin in ["http://localhost:5173", "http://127.0.0.1:5173"]:
            assert _validate_ws_origin(origin) is True, \
                f"Dev server origin '{origin}' should be accepted"

    def test_validate_ws_origin_allows_localhost_variants(self):
        """Test that localhost variants are accepted."""
        for origin in ["http://localhost:1420", "http://127.0.0.1:1420"]:
            assert _validate_ws_origin(origin) is True, \
                f"localhost variant '{origin}' should be accepted"

    def test_validate_ws_origin_rejects_invalid_origins(self):
        """Test that invalid origins are rejected."""
        invalid_origins = [
            "http://evil.com",
            "https://malicious.site",
            "http://192.168.1.100:1420",  # Non-localhost IP
            "tauri://evil.com",
            "http://localhost:9999",  # Wrong port
        ]
        for origin in invalid_origins:
            assert _validate_ws_origin(origin) is False, \
                f"Invalid origin '{origin}' should be rejected"

    def test_no_dev_mode_bypass(self):
        """Test that dev mode environment variable no longer bypasses origin check."""
        # Save original value
        original = os.environ.get("GODOTY_DEV_MODE")

        try:
            # Set dev mode to true
            os.environ["GODOTY_DEV_MODE"] = "true"

            # None origin should still be rejected without proper client_type
            assert _validate_ws_origin(None) is False, \
                "Dev mode should not bypass origin validation"

        finally:
            # Restore original value
            if original is None:
                os.environ.pop("GODOTY_DEV_MODE", None)
            else:
                os.environ["GODOTY_DEV_MODE"] = original

    def test_allowed_origins_set_is_not_empty(self):
        """Test that ALLOWED_WS_ORIGINS contains expected values."""
        assert len(ALLOWED_WS_ORIGINS) > 0, \
            "ALLOWED_WS_ORIGINS should not be empty"

        expected_origins = {
            "tauri://localhost",
            "http://localhost:1420",
            "http://localhost:5173",
        }
        for expected in expected_origins:
            assert expected in ALLOWED_WS_ORIGINS, \
                f"Expected origin '{expected}' not in ALLOWED_WS_ORIGINS"

    def test_case_sensitive_origin_check(self):
        """Test that origin validation is case-sensitive."""
        # Uppercase version should be rejected (domains are case-sensitive)
        assert _validate_ws_origin("TAURI://LOCALHOST") is False, \
            "Uppercase origin should be rejected (case-sensitive)"

    def test_origin_with_trailing_slash(self):
        """Test that origins with trailing slashes are handled correctly."""
        # These should be rejected since they're not in ALLOWED_WS_ORIGINS
        assert _validate_ws_origin("http://localhost:1420/") is False, \
            "Origin with trailing slash should be rejected unless explicitly allowed"

    def test_godot_with_valid_origin_also_works(self):
        """Test that Godot plugin with a valid origin header is also accepted."""
        # If Godot somehow sends an origin header that's valid, it should work
        assert _validate_ws_origin("http://localhost:1420", client_type="godot") is True, \
            "Godot with valid origin should be accepted"
