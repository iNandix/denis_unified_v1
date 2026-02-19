"""Tests for Chat CP secrets module."""

import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "denis_unified_v1"))


# Test against the actual module
class TestSecretsModule:
    """Test secrets module with mocked keyring."""

    def test_get_secret_from_keyring(self):
        """Test getting secret from keyring."""
        # Import the module first
        import denis_unified_v1.chat_cp.secrets as secrets_module

        with patch.object(secrets_module, "keyring") as mock_keyring:
            mock_keyring.get_password.return_value = "sk-test-key"

            result = secrets_module.get_secret("OPENAI_API_KEY", required=False)

            assert result == "sk-test-key"
            mock_keyring.get_password.assert_called_once()

    def test_get_secret_not_found(self):
        """Test missing secret returns None when required=False."""
        import denis_unified_v1.chat_cp.secrets as secrets_module

        with patch.object(secrets_module, "keyring") as mock_keyring:
            mock_keyring.get_password.return_value = None

            result = secrets_module.get_secret("OPENAI_API_KEY", required=False)

            assert result is None

    def test_get_secret_required_raises(self):
        """Test missing secret raises SecretNotFoundError when required=True."""
        import denis_unified_v1.chat_cp.secrets as secrets_module

        with patch.object(secrets_module, "keyring") as mock_keyring:
            mock_keyring.get_password.return_value = None

            with pytest.raises(secrets_module.SecretNotFoundError):
                secrets_module.get_secret("OPENAI_API_KEY", required=True)

    def test_set_secret(self):
        """Test setting secret in keyring."""
        import denis_unified_v1.chat_cp.secrets as secrets_module

        with patch.object(secrets_module, "keyring") as mock_keyring:
            result = secrets_module.set_secret("OPENAI_API_KEY", "sk-test-key")

            assert result is True
            mock_keyring.set_password.assert_called_once_with(
                secrets_module.DEFAULT_SERVICE, "OPENAI_API_KEY", "sk-test-key"
            )

    def test_delete_secret(self):
        """Test deleting secret from keyring."""
        import denis_unified_v1.chat_cp.secrets as secrets_module

        with patch.object(secrets_module, "keyring") as mock_keyring:
            result = secrets_module.delete_secret("OPENAI_API_KEY")

            assert result is True
            mock_keyring.delete_password.assert_called_once_with(
                secrets_module.DEFAULT_SERVICE, "OPENAI_API_KEY"
            )

    def test_secret_caching(self):
        """Test that secrets are cached after first lookup."""
        import denis_unified_v1.chat_cp.secrets as secrets_module

        with patch.object(secrets_module, "keyring") as mock_keyring:
            mock_keyring.get_password.return_value = "sk-cached-key"

            # Clear any existing cache
            secrets_module.clear_secret_cache()

            # First call
            result1 = secrets_module.get_secret("OPENAI_API_KEY", required=False)
            # Second call should use cache
            result2 = secrets_module.get_secret("OPENAI_API_KEY", required=False)

            assert result1 == "sk-cached-key"
            assert result2 == "sk-cached-key"
            # Should only call keyring once
            assert mock_keyring.get_password.call_count == 1

    def test_set_clears_cache(self):
        """Test that setting a secret clears the cache."""
        import denis_unified_v1.chat_cp.secrets as secrets_module

        with patch.object(secrets_module, "keyring") as mock_keyring:
            mock_keyring.get_password.return_value = "sk-old-key"

            # Clear any existing cache first
            secrets_module.clear_secret_cache()

            # First lookup
            result1 = secrets_module.get_secret("OPENAI_API_KEY", required=False)
            assert result1 == "sk-old-key"

            # Set new value
            secrets_module.set_secret("OPENAI_API_KEY", "sk-new-key")

            # Next lookup should get new value
            mock_keyring.get_password.return_value = "sk-new-key"
            result2 = secrets_module.get_secret("OPENAI_API_KEY", required=False)

            assert result2 == "sk-new-key"

    def test_keyring_not_available(self):
        """Test behavior when keyring is not available."""
        import denis_unified_v1.chat_cp.secrets as secrets_module

        with patch.object(secrets_module, "keyring") as mock_keyring:
            mock_keyring.get_password.side_effect = Exception("No keyring")

            # Should return None when fallback_to_env is True (default)
            result = secrets_module.get_secret("OPENAI_API_KEY", required=False)
            assert result is None

    def test_convenience_functions(self):
        """Test convenience functions for specific secrets."""
        import denis_unified_v1.chat_cp.secrets as secrets_module

        with patch.object(secrets_module, "keyring") as mock_keyring:
            # Test get_openai_api_key
            mock_keyring.get_password.return_value = "sk-openai-test"
            result = secrets_module.get_openai_api_key(required=False)
            assert result == "sk-openai-test"

            # Test get_anthropic_api_key
            mock_keyring.get_password.return_value = "sk-anthropic-test"
            result = secrets_module.get_anthropic_api_key(required=False)
            assert result == "sk-anthropic-test"

    def test_is_keyring_available(self):
        """Test keyring availability check."""
        import denis_unified_v1.chat_cp.secrets as secrets_module

        with patch.object(secrets_module, "keyring") as mock_keyring:
            # Keyring available
            mock_keyring.get_keyring.return_value = MagicMock()
            assert secrets_module.is_keyring_available() is True

            # Keyring not available
            mock_keyring.get_keyring.side_effect = Exception("No keyring")
            assert secrets_module.is_keyring_available() is False


class TestSecretsWithEnvFallback:
    """Test secrets with environment variable fallback (migration)."""

    def test_fallback_to_env(self):
        """Test falling back to env var if keyring returns None."""
        import denis_unified_v1.chat_cp.secrets as secrets_module

        with patch.object(secrets_module, "keyring") as mock_keyring:
            mock_keyring.get_password.return_value = None

            with patch("os.getenv") as mock_getenv:
                mock_getenv.return_value = "sk-from-env"

                result = secrets_module.get_secret("OPENAI_API_KEY", required=False)

                assert result == "sk-from-env"
                mock_getenv.assert_called_once_with("OPENAI_API_KEY")


class TestProvidersWithSecrets:
    """Test that providers use secrets correctly."""

    def test_openai_provider_uses_secrets(self):
        """Test OpenAI provider gets key from secrets."""
        import denis_unified_v1.chat_cp.secrets as secrets_module

        with patch.object(secrets_module, "get_secret") as mock_get:
            mock_get.return_value = "sk-openai-test"

            # Force reimport
            import importlib
            import denis_unified_v1.chat_cp.providers.openai_chat as openai_module

            importlib.reload(openai_module)

            provider = openai_module.OpenAIChatProvider()

            assert provider.api_key == "sk-openai-test"
            assert provider.is_configured() is True
            mock_get.assert_called_once_with("OPENAI_API_KEY")

    def test_anthropic_provider_uses_secrets(self):
        """Test Anthropic provider gets key from secrets."""
        import denis_unified_v1.chat_cp.secrets as secrets_module

        with patch.object(secrets_module, "get_secret") as mock_get:
            mock_get.return_value = "sk-anthropic-test"

            # Force reimport
            import importlib
            import denis_unified_v1.chat_cp.providers.anthropic_chat as anthropic_module

            importlib.reload(anthropic_module)

            provider = anthropic_module.AnthropicChatProvider()

            assert provider.api_key == "sk-anthropic-test"
            assert provider.is_configured() is True
            mock_get.assert_called_once_with("ANTHROPIC_API_KEY")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
