"""Tests for authentication providers."""

from __future__ import annotations

import base64

import pytest

from civicrm_py.core.auth import (
    APIKeyAuth,
    AuthProvider,
    BasicAuth,
    JWTAuth,
)
from civicrm_py.core.config import CiviSettings


class TestAPIKeyAuth:
    """Tests for APIKeyAuth authentication provider."""

    def test_get_headers_with_api_key_only(self) -> None:
        """Test get_headers returns correct headers with API key only."""
        auth = APIKeyAuth(api_key="test-api-key")
        headers = auth.get_headers()

        assert headers["Authorization"] == "Bearer test-api-key"
        assert headers["X-Requested-With"] == "XMLHttpRequest"
        assert "X-Civi-Key" not in headers

    def test_get_headers_with_site_key(self) -> None:
        """Test get_headers includes site key when provided."""
        auth = APIKeyAuth(api_key="test-api-key", site_key="test-site-key")
        headers = auth.get_headers()

        assert headers["Authorization"] == "Bearer test-api-key"
        assert headers["X-Requested-With"] == "XMLHttpRequest"
        assert headers["X-Civi-Key"] == "test-site-key"

    def test_is_valid_with_api_key(self) -> None:
        """Test is_valid returns True when API key is set."""
        auth = APIKeyAuth(api_key="test-api-key")
        assert auth.is_valid() is True

    def test_is_valid_with_empty_api_key(self) -> None:
        """Test is_valid returns False when API key is empty."""
        auth = APIKeyAuth(api_key="")
        assert auth.is_valid() is False

    def test_is_valid_with_whitespace_api_key(self) -> None:
        """Test is_valid returns True for whitespace-only API key (non-empty)."""
        auth = APIKeyAuth(api_key="   ")
        assert auth.is_valid() is True

    def test_site_key_is_optional(self) -> None:
        """Test that site_key is optional."""
        auth = APIKeyAuth(api_key="test-api-key")
        assert auth.site_key is None

    def test_stores_credentials(self) -> None:
        """Test that credentials are stored correctly."""
        auth = APIKeyAuth(api_key="my-key", site_key="my-site")
        assert auth.api_key == "my-key"
        assert auth.site_key == "my-site"


class TestJWTAuth:
    """Tests for JWTAuth authentication provider."""

    def test_get_headers(self) -> None:
        """Test get_headers returns correct Bearer token header."""
        auth = JWTAuth(token="jwt-token-value")  # noqa: S106
        headers = auth.get_headers()

        assert headers["Authorization"] == "Bearer jwt-token-value"
        assert len(headers) == 1

    def test_is_valid_with_token(self) -> None:
        """Test is_valid returns True when token is set."""
        auth = JWTAuth(token="jwt-token-value")  # noqa: S106
        assert auth.is_valid() is True

    def test_is_valid_with_empty_token(self) -> None:
        """Test is_valid returns False when token is empty."""
        auth = JWTAuth(token="")
        assert auth.is_valid() is False

    def test_stores_token(self) -> None:
        """Test that token is stored correctly."""
        auth = JWTAuth(token="my-jwt-token")  # noqa: S106
        assert auth.token == "my-jwt-token"

    def test_get_headers_with_complex_token(self) -> None:
        """Test get_headers handles complex JWT tokens."""
        # Simulating a realistic JWT token structure
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        auth = JWTAuth(token=token)
        headers = auth.get_headers()

        assert headers["Authorization"] == f"Bearer {token}"


class TestBasicAuth:
    """Tests for BasicAuth authentication provider."""

    def test_get_headers(self) -> None:
        """Test get_headers returns correctly encoded Basic auth header."""
        auth = BasicAuth(username="testuser", password="testpass")  # noqa: S106
        headers = auth.get_headers()

        # Verify the Authorization header format
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Basic ")

        # Decode and verify the credentials
        encoded_part = headers["Authorization"].replace("Basic ", "")
        decoded = base64.b64decode(encoded_part).decode()
        assert decoded == "testuser:testpass"

    def test_is_valid_with_both_credentials(self) -> None:
        """Test is_valid returns True when both username and password are set."""
        auth = BasicAuth(username="user", password="pass")  # noqa: S106
        assert auth.is_valid() is True

    def test_is_valid_with_empty_username(self) -> None:
        """Test is_valid returns False when username is empty."""
        auth = BasicAuth(username="", password="pass")  # noqa: S106
        assert auth.is_valid() is False

    def test_is_valid_with_empty_password(self) -> None:
        """Test is_valid returns False when password is empty."""
        auth = BasicAuth(username="user", password="")
        assert auth.is_valid() is False

    def test_is_valid_with_both_empty(self) -> None:
        """Test is_valid returns False when both credentials are empty."""
        auth = BasicAuth(username="", password="")
        assert auth.is_valid() is False

    def test_stores_credentials(self) -> None:
        """Test that credentials are stored correctly."""
        auth = BasicAuth(username="myuser", password="mypass")  # noqa: S106
        assert auth.username == "myuser"
        assert auth.password == "mypass"

    def test_get_headers_with_special_characters(self) -> None:
        """Test get_headers handles special characters in credentials."""
        auth = BasicAuth(username="user@domain.com", password="p@ss:word!")  # noqa: S106
        headers = auth.get_headers()

        # Decode and verify
        encoded_part = headers["Authorization"].replace("Basic ", "")
        decoded = base64.b64decode(encoded_part).decode()
        assert decoded == "user@domain.com:p@ss:word!"

    def test_get_headers_with_unicode(self) -> None:
        """Test get_headers handles unicode characters in credentials."""
        auth = BasicAuth(username="user", password="passe")  # noqa: S106
        headers = auth.get_headers()

        # Decode and verify
        encoded_part = headers["Authorization"].replace("Basic ", "")
        decoded = base64.b64decode(encoded_part).decode()
        assert decoded == "user:passe"


class TestAuthProviderFromSettings:
    """Tests for AuthProvider.from_settings factory method."""

    def test_creates_api_key_auth(self) -> None:
        """Test from_settings creates APIKeyAuth for api_key auth_type."""
        settings = CiviSettings(
            base_url="https://example.org/api4",
            auth_type="api_key",
            api_key="test-api-key",
            site_key="test-site-key",
        )

        auth = AuthProvider.from_settings(settings)

        assert isinstance(auth, APIKeyAuth)
        assert auth.api_key == "test-api-key"
        assert auth.site_key == "test-site-key"

    def test_creates_api_key_auth_without_site_key(self) -> None:
        """Test from_settings creates APIKeyAuth without site key."""
        settings = CiviSettings(
            base_url="https://example.org/api4",
            auth_type="api_key",
            api_key="test-api-key",
        )

        auth = AuthProvider.from_settings(settings)

        assert isinstance(auth, APIKeyAuth)
        assert auth.api_key == "test-api-key"
        assert auth.site_key is None

    def test_creates_jwt_auth(self) -> None:
        """Test from_settings creates JWTAuth for jwt auth_type."""
        settings = CiviSettings(
            base_url="https://example.org/api4",
            auth_type="jwt",
            jwt_token="test-jwt-token",  # noqa: S106
        )

        auth = AuthProvider.from_settings(settings)

        assert isinstance(auth, JWTAuth)
        assert auth.token == "test-jwt-token"

    def test_creates_basic_auth(self) -> None:
        """Test from_settings creates BasicAuth for basic auth_type."""
        settings = CiviSettings(
            base_url="https://example.org/api4",
            auth_type="basic",
            username="testuser",
            password="testpass",  # noqa: S106
        )

        auth = AuthProvider.from_settings(settings)

        assert isinstance(auth, BasicAuth)
        assert auth.username == "testuser"
        assert auth.password == "testpass"

    def test_raises_for_unknown_auth_type(self) -> None:
        """Test from_settings raises ValueError for unknown auth_type."""
        # Create a settings object with a valid auth_type first,
        # then we need to test the factory with an invalid one.
        # Since CiviSettings validates auth_type, we need to use object.__setattr__
        # to bypass the frozen dataclass for testing purposes.
        settings = CiviSettings(
            base_url="https://example.org/api4",
            auth_type="api_key",
            api_key="test-key",
        )
        # Override auth_type for testing (bypass frozen dataclass)
        object.__setattr__(settings, "auth_type", "unknown")

        with pytest.raises(ValueError, match="Unknown auth_type: unknown"):
            AuthProvider.from_settings(settings)


class TestAuthProviderABC:
    """Tests for AuthProvider abstract base class behavior."""

    def test_cannot_instantiate_abstract_class(self) -> None:
        """Test that AuthProvider cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            AuthProvider()  # type: ignore[abstract]

    def test_api_key_auth_is_auth_provider(self) -> None:
        """Test that APIKeyAuth is an AuthProvider subclass."""
        auth = APIKeyAuth(api_key="test")
        assert isinstance(auth, AuthProvider)

    def test_jwt_auth_is_auth_provider(self) -> None:
        """Test that JWTAuth is an AuthProvider subclass."""
        auth = JWTAuth(token="test")  # noqa: S106
        assert isinstance(auth, AuthProvider)

    def test_basic_auth_is_auth_provider(self) -> None:
        """Test that BasicAuth is an AuthProvider subclass."""
        auth = BasicAuth(username="user", password="pass")  # noqa: S106
        assert isinstance(auth, AuthProvider)


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_api_key_auth_empty_site_key_string(self) -> None:
        """Test APIKeyAuth with empty string site key (should not include header)."""
        auth = APIKeyAuth(api_key="test-key", site_key="")
        headers = auth.get_headers()

        # Empty string is falsy, so X-Civi-Key should not be included
        assert "X-Civi-Key" not in headers

    def test_api_key_with_special_characters(self) -> None:
        """Test APIKeyAuth handles special characters in API key."""
        special_key = "api-key_with.special+chars/and=equals"
        auth = APIKeyAuth(api_key=special_key)
        headers = auth.get_headers()

        assert headers["Authorization"] == f"Bearer {special_key}"

    def test_jwt_with_very_long_token(self) -> None:
        """Test JWTAuth handles very long tokens."""
        long_token = "a" * 10000
        auth = JWTAuth(token=long_token)
        headers = auth.get_headers()

        assert headers["Authorization"] == f"Bearer {long_token}"

    def test_basic_auth_with_empty_colon_in_password(self) -> None:
        """Test BasicAuth handles passwords containing colons."""
        auth = BasicAuth(username="user", password="pass:with:colons")  # noqa: S106
        headers = auth.get_headers()

        # Decode and verify - colons after the first should be in password
        encoded_part = headers["Authorization"].replace("Basic ", "")
        decoded = base64.b64decode(encoded_part).decode()
        assert decoded == "user:pass:with:colons"

    def test_auth_headers_are_new_dict_each_call(self) -> None:
        """Test that get_headers returns a new dict on each call."""
        auth = APIKeyAuth(api_key="test-key")
        headers1 = auth.get_headers()
        headers2 = auth.get_headers()

        assert headers1 is not headers2
        assert headers1 == headers2
