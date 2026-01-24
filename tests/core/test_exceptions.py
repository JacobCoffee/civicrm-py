"""Tests for civi-py exception hierarchy."""

from __future__ import annotations

import pytest

from civicrm_py.core.exceptions import (
    CiviAPIError,
    CiviAuthError,
    CiviConfigError,
    CiviConnectionError,
    CiviError,
    CiviIntegrationError,
    CiviNotFoundError,
    CiviPermissionError,
    CiviTimeoutError,
    CiviValidationError,
    DoesNotExist,
    MultipleObjectsReturned,
)


class TestCiviError:
    """Tests for the base CiviError exception."""

    def test_raise_with_message(self) -> None:
        """Test raising CiviError with a message."""
        with pytest.raises(CiviError, match="Test error message"):
            raise CiviError("Test error message")

    def test_message_attribute(self) -> None:
        """Test that message is stored as attribute."""
        exc = CiviError("Test message")
        assert exc.message == "Test message"

    def test_details_default_empty(self) -> None:
        """Test that details defaults to empty dict."""
        exc = CiviError("Test message")
        assert exc.details == {}

    def test_details_stored(self) -> None:
        """Test that details dict is stored correctly."""
        details = {"key": "value", "number": 42}
        exc = CiviError("Test message", details=details)
        assert exc.details == details
        assert exc.details["key"] == "value"
        assert exc.details["number"] == 42

    def test_str_representation(self) -> None:
        """Test string representation is the message."""
        exc = CiviError("Test message")
        assert str(exc) == "Test message"

    def test_inherits_from_exception(self) -> None:
        """Test that CiviError inherits from Exception."""
        exc = CiviError("Test")
        assert isinstance(exc, Exception)


class TestCiviConfigError:
    """Tests for CiviConfigError exception."""

    def test_raise_and_catch(self) -> None:
        """Test raising and catching CiviConfigError."""
        with pytest.raises(CiviConfigError, match="Invalid configuration"):
            raise CiviConfigError("Invalid configuration")

    def test_catch_as_civi_error(self) -> None:
        """Test that CiviConfigError can be caught as CiviError."""
        with pytest.raises(CiviError):
            raise CiviConfigError("Config error")

    def test_inherits_details(self) -> None:
        """Test that CiviConfigError inherits details parameter."""
        details = {"setting": "base_url", "reason": "empty"}
        exc = CiviConfigError("Missing base_url", details=details)
        assert exc.details == details
        assert exc.message == "Missing base_url"


class TestCiviAuthError:
    """Tests for CiviAuthError exception."""

    def test_raise_and_catch(self) -> None:
        """Test raising and catching CiviAuthError."""
        with pytest.raises(CiviAuthError, match="Authentication failed"):
            raise CiviAuthError("Authentication failed")

    def test_catch_as_civi_error(self) -> None:
        """Test that CiviAuthError can be caught as CiviError."""
        with pytest.raises(CiviError):
            raise CiviAuthError("Auth error")

    def test_with_details(self) -> None:
        """Test CiviAuthError with details."""
        details = {"auth_type": "api_key", "reason": "invalid key"}
        exc = CiviAuthError("Invalid API key", details=details)
        assert exc.details == details


class TestCiviConnectionError:
    """Tests for CiviConnectionError exception."""

    def test_raise_and_catch(self) -> None:
        """Test raising and catching CiviConnectionError."""
        with pytest.raises(CiviConnectionError, match="Connection refused"):
            raise CiviConnectionError("Connection refused")

    def test_catch_as_civi_error(self) -> None:
        """Test that CiviConnectionError can be caught as CiviError."""
        with pytest.raises(CiviError):
            raise CiviConnectionError("Connection error")

    def test_with_details(self) -> None:
        """Test CiviConnectionError with details."""
        details = {"host": "example.org", "port": 443}
        exc = CiviConnectionError("Failed to connect", details=details)
        assert exc.details == details


class TestCiviTimeoutError:
    """Tests for CiviTimeoutError exception."""

    def test_raise_and_catch(self) -> None:
        """Test raising and catching CiviTimeoutError."""
        with pytest.raises(CiviTimeoutError, match="Request timed out"):
            raise CiviTimeoutError("Request timed out")

    def test_catch_as_connection_error(self) -> None:
        """Test that CiviTimeoutError can be caught as CiviConnectionError."""
        with pytest.raises(CiviConnectionError):
            raise CiviTimeoutError("Timeout")

    def test_catch_as_civi_error(self) -> None:
        """Test that CiviTimeoutError can be caught as CiviError."""
        with pytest.raises(CiviError):
            raise CiviTimeoutError("Timeout")

    def test_inheritance_chain(self) -> None:
        """Test the complete inheritance chain."""
        exc = CiviTimeoutError("Timeout")
        assert isinstance(exc, CiviTimeoutError)
        assert isinstance(exc, CiviConnectionError)
        assert isinstance(exc, CiviError)
        assert isinstance(exc, Exception)

    def test_with_details(self) -> None:
        """Test CiviTimeoutError with timeout details."""
        details = {"timeout_seconds": 30, "endpoint": "/Contact/get"}
        exc = CiviTimeoutError("Request timed out after 30s", details=details)
        assert exc.details == details


class TestCiviAPIError:
    """Tests for CiviAPIError exception."""

    def test_raise_and_catch(self) -> None:
        """Test raising and catching CiviAPIError."""
        with pytest.raises(CiviAPIError, match="API returned error"):
            raise CiviAPIError("API returned error")

    def test_catch_as_civi_error(self) -> None:
        """Test that CiviAPIError can be caught as CiviError."""
        with pytest.raises(CiviError):
            raise CiviAPIError("API error")

    def test_error_code_string(self) -> None:
        """Test error_code with string value."""
        exc = CiviAPIError("Error", error_code="unauthorized")
        assert exc.error_code == "unauthorized"

    def test_error_code_integer(self) -> None:
        """Test error_code with integer value."""
        exc = CiviAPIError("Error", error_code=401)
        assert exc.error_code == 401

    def test_error_code_none(self) -> None:
        """Test error_code defaults to None."""
        exc = CiviAPIError("Error")
        assert exc.error_code is None

    def test_error_message(self) -> None:
        """Test error_message is stored."""
        exc = CiviAPIError("Error occurred", error_message="Detailed API error message")
        assert exc.error_message == "Detailed API error message"

    def test_error_message_none(self) -> None:
        """Test error_message defaults to None."""
        exc = CiviAPIError("Error")
        assert exc.error_message is None

    def test_all_parameters(self) -> None:
        """Test CiviAPIError with all parameters."""
        details = {"entity": "Contact", "action": "get"}
        exc = CiviAPIError(
            "Contact not found",
            error_code="not_found",
            error_message="The requested contact does not exist",
            details=details,
        )
        assert exc.message == "Contact not found"
        assert exc.error_code == "not_found"
        assert exc.error_message == "The requested contact does not exist"
        assert exc.details == details


class TestCiviNotFoundError:
    """Tests for CiviNotFoundError exception."""

    def test_raise_and_catch(self) -> None:
        """Test raising and catching CiviNotFoundError."""
        with pytest.raises(CiviNotFoundError, match="Entity not found"):
            raise CiviNotFoundError("Entity not found")

    def test_catch_as_api_error(self) -> None:
        """Test that CiviNotFoundError can be caught as CiviAPIError."""
        with pytest.raises(CiviAPIError):
            raise CiviNotFoundError("Not found")

    def test_catch_as_civi_error(self) -> None:
        """Test that CiviNotFoundError can be caught as CiviError."""
        with pytest.raises(CiviError):
            raise CiviNotFoundError("Not found")

    def test_inherits_error_code(self) -> None:
        """Test that CiviNotFoundError inherits error_code parameter."""
        exc = CiviNotFoundError("Not found", error_code=404)
        assert exc.error_code == 404

    def test_inheritance_chain(self) -> None:
        """Test the complete inheritance chain."""
        exc = CiviNotFoundError("Not found")
        assert isinstance(exc, CiviNotFoundError)
        assert isinstance(exc, CiviAPIError)
        assert isinstance(exc, CiviError)
        assert isinstance(exc, Exception)


class TestCiviValidationError:
    """Tests for CiviValidationError exception."""

    def test_raise_and_catch(self) -> None:
        """Test raising and catching CiviValidationError."""
        with pytest.raises(CiviValidationError, match="Validation failed"):
            raise CiviValidationError("Validation failed")

    def test_catch_as_api_error(self) -> None:
        """Test that CiviValidationError can be caught as CiviAPIError."""
        with pytest.raises(CiviAPIError):
            raise CiviValidationError("Validation error")

    def test_catch_as_civi_error(self) -> None:
        """Test that CiviValidationError can be caught as CiviError."""
        with pytest.raises(CiviError):
            raise CiviValidationError("Validation error")

    def test_with_field_details(self) -> None:
        """Test CiviValidationError with field validation details."""
        details = {
            "field": "email",
            "value": "invalid-email",
            "constraint": "email_format",
        }
        exc = CiviValidationError(
            "Invalid email format",
            error_code="validation_error",
            error_message="Email must be a valid email address",
            details=details,
        )
        assert exc.details["field"] == "email"
        assert exc.error_code == "validation_error"


class TestCiviPermissionError:
    """Tests for CiviPermissionError exception."""

    def test_raise_and_catch(self) -> None:
        """Test raising and catching CiviPermissionError."""
        with pytest.raises(CiviPermissionError, match="Permission denied"):
            raise CiviPermissionError("Permission denied")

    def test_catch_as_api_error(self) -> None:
        """Test that CiviPermissionError can be caught as CiviAPIError."""
        with pytest.raises(CiviAPIError):
            raise CiviPermissionError("Permission error")

    def test_catch_as_civi_error(self) -> None:
        """Test that CiviPermissionError can be caught as CiviError."""
        with pytest.raises(CiviError):
            raise CiviPermissionError("Permission error")

    def test_with_permission_details(self) -> None:
        """Test CiviPermissionError with permission details."""
        details = {
            "required_permission": "edit contacts",
            "user_id": 123,
            "entity": "Contact",
            "action": "update",
        }
        exc = CiviPermissionError(
            "User does not have permission to edit contacts",
            error_code=403,
            details=details,
        )
        assert exc.error_code == 403
        assert exc.details["required_permission"] == "edit contacts"


class TestCiviIntegrationError:
    """Tests for CiviIntegrationError exception."""

    def test_raise_and_catch(self) -> None:
        """Test raising and catching CiviIntegrationError."""
        with pytest.raises(CiviIntegrationError, match="Integration error"):
            raise CiviIntegrationError("Integration error")

    def test_catch_as_civi_error(self) -> None:
        """Test that CiviIntegrationError can be caught as CiviError."""
        with pytest.raises(CiviError):
            raise CiviIntegrationError("Integration error")

    def test_with_framework_details(self) -> None:
        """Test CiviIntegrationError with framework details."""
        details = {
            "framework": "django",
            "component": "middleware",
            "reason": "client not initialized",
        }
        exc = CiviIntegrationError("Django client not initialized", details=details)
        assert exc.details == details
        assert exc.details["framework"] == "django"


class TestDoesNotExist:
    """Tests for DoesNotExist exception."""

    def test_raise_with_entity_name(self) -> None:
        """Test raising DoesNotExist with entity name."""
        with pytest.raises(DoesNotExist, match="Contact matching query does not exist"):
            raise DoesNotExist("Contact")

    def test_entity_name_stored(self) -> None:
        """Test that entity_name is stored."""
        exc = DoesNotExist("Contact")
        assert exc.entity_name == "Contact"

    def test_lookup_params_default_empty(self) -> None:
        """Test that lookup_params defaults to empty dict."""
        exc = DoesNotExist("Contact")
        assert exc.lookup_params == {}

    def test_message_without_params(self) -> None:
        """Test message format without lookup params."""
        exc = DoesNotExist("Activity")
        assert exc.message == "Activity matching query does not exist."

    def test_message_with_single_param(self) -> None:
        """Test message format with single lookup param."""
        exc = DoesNotExist("Contact", lookup_params={"id": 99999})
        assert exc.message == "Contact matching query (id=99999) does not exist."

    def test_message_with_multiple_params(self) -> None:
        """Test message format with multiple lookup params."""
        exc = DoesNotExist(
            "Contact",
            lookup_params={"first_name": "John", "last_name": "Doe"},
        )
        assert "first_name='John'" in exc.message
        assert "last_name='Doe'" in exc.message
        assert "does not exist" in exc.message

    def test_lookup_params_stored(self) -> None:
        """Test that lookup_params are stored."""
        params = {"id": 123, "email": "test@example.com"}
        exc = DoesNotExist("Contact", lookup_params=params)
        assert exc.lookup_params == params

    def test_details_populated(self) -> None:
        """Test that details dict is populated correctly."""
        params = {"id": 42}
        exc = DoesNotExist("Contact", lookup_params=params)
        assert exc.details == {"entity": "Contact", "params": params}

    def test_catch_as_civi_error(self) -> None:
        """Test that DoesNotExist can be caught as CiviError."""
        with pytest.raises(CiviError):
            raise DoesNotExist("Contact")

    def test_inheritance(self) -> None:
        """Test the inheritance chain."""
        exc = DoesNotExist("Contact")
        assert isinstance(exc, DoesNotExist)
        assert isinstance(exc, CiviError)
        assert isinstance(exc, Exception)


class TestMultipleObjectsReturned:
    """Tests for MultipleObjectsReturned exception."""

    def test_raise_with_entity_and_count(self) -> None:
        """Test raising MultipleObjectsReturned with entity and count."""
        with pytest.raises(
            MultipleObjectsReturned,
            match=r"get\(\) returned 5 Contact objects; expected 1",
        ):
            raise MultipleObjectsReturned("Contact", count=5)

    def test_entity_name_stored(self) -> None:
        """Test that entity_name is stored."""
        exc = MultipleObjectsReturned("Contact", count=3)
        assert exc.entity_name == "Contact"

    def test_count_stored(self) -> None:
        """Test that count is stored."""
        exc = MultipleObjectsReturned("Contact", count=10)
        assert exc.count == 10

    def test_lookup_params_default_empty(self) -> None:
        """Test that lookup_params defaults to empty dict."""
        exc = MultipleObjectsReturned("Contact", count=2)
        assert exc.lookup_params == {}

    def test_message_without_params(self) -> None:
        """Test message format without lookup params."""
        exc = MultipleObjectsReturned("Activity", count=7)
        assert exc.message == "get() returned 7 Activity objects; expected 1."

    def test_message_with_single_param(self) -> None:
        """Test message format with single lookup param."""
        exc = MultipleObjectsReturned(
            "Contact",
            count=3,
            lookup_params={"last_name": "Smith"},
        )
        assert exc.message == "get() returned 3 Contact objects (last_name='Smith'); expected 1."

    def test_message_with_multiple_params(self) -> None:
        """Test message format with multiple lookup params."""
        exc = MultipleObjectsReturned(
            "Contact",
            count=5,
            lookup_params={"first_name": "John", "is_deleted": False},
        )
        assert "first_name='John'" in exc.message
        assert "is_deleted=False" in exc.message
        assert "expected 1" in exc.message

    def test_lookup_params_stored(self) -> None:
        """Test that lookup_params are stored."""
        params = {"organization_name": "Test Corp"}
        exc = MultipleObjectsReturned("Contact", count=2, lookup_params=params)
        assert exc.lookup_params == params

    def test_details_populated(self) -> None:
        """Test that details dict is populated correctly."""
        params = {"email": "shared@example.com"}
        exc = MultipleObjectsReturned("Contact", count=4, lookup_params=params)
        assert exc.details == {"entity": "Contact", "count": 4, "params": params}

    def test_catch_as_civi_error(self) -> None:
        """Test that MultipleObjectsReturned can be caught as CiviError."""
        with pytest.raises(CiviError):
            raise MultipleObjectsReturned("Contact", count=2)

    def test_inheritance(self) -> None:
        """Test the inheritance chain."""
        exc = MultipleObjectsReturned("Contact", count=2)
        assert isinstance(exc, MultipleObjectsReturned)
        assert isinstance(exc, CiviError)
        assert isinstance(exc, Exception)


class TestExceptionHierarchy:
    """Tests for the complete exception hierarchy."""

    def test_catch_all_with_civi_error(self) -> None:
        """Test catching all civi-py exceptions with CiviError."""
        exceptions = [
            CiviError("base"),
            CiviConfigError("config"),
            CiviAuthError("auth"),
            CiviConnectionError("connection"),
            CiviTimeoutError("timeout"),
            CiviAPIError("api"),
            CiviNotFoundError("not found"),
            CiviValidationError("validation"),
            CiviPermissionError("permission"),
            CiviIntegrationError("integration"),
            DoesNotExist("Contact"),
            MultipleObjectsReturned("Contact", count=2),
        ]

        for exc in exceptions:
            try:
                raise exc
            except CiviError as caught:
                assert caught is exc
            else:
                pytest.fail(f"{type(exc).__name__} was not caught as CiviError")

    def test_api_error_subclasses_caught_together(self) -> None:
        """Test catching all API error subclasses with CiviAPIError."""
        api_exceptions = [
            CiviAPIError("api"),
            CiviNotFoundError("not found"),
            CiviValidationError("validation"),
            CiviPermissionError("permission"),
        ]

        for exc in api_exceptions:
            try:
                raise exc
            except CiviAPIError as caught:
                assert caught is exc
            else:
                pytest.fail(f"{type(exc).__name__} was not caught as CiviAPIError")

    def test_connection_error_hierarchy(self) -> None:
        """Test connection error hierarchy."""
        # CiviTimeoutError should be caught by CiviConnectionError
        try:
            raise CiviTimeoutError("timeout")
        except CiviConnectionError as caught:
            assert isinstance(caught, CiviTimeoutError)
        else:
            pytest.fail("CiviTimeoutError was not caught as CiviConnectionError")

    def test_specific_exception_not_caught_by_sibling(self) -> None:
        """Test that specific exceptions are not caught by sibling classes."""
        # CiviAuthError should not be caught by CiviConfigError
        with pytest.raises(CiviAuthError):
            try:
                raise CiviAuthError("auth error")
            except CiviConfigError:
                pytest.fail("CiviAuthError should not be caught by CiviConfigError")

    def test_exception_messages_preserved(self) -> None:
        """Test that exception messages are preserved through inheritance."""
        original_message = "Original error message"

        # Test base class
        exc = CiviError(original_message)
        assert str(exc) == original_message
        assert exc.message == original_message

        # Test subclass
        config_exc = CiviConfigError(original_message)
        assert str(config_exc) == original_message
        assert config_exc.message == original_message

        # Test API error with all params
        api_exc = CiviAPIError(
            original_message,
            error_code="test_code",
            error_message="API message",
        )
        assert str(api_exc) == original_message
        assert api_exc.message == original_message
