from unittest.mock import MagicMock, patch

import pytest

from mcp_email_server.config import EmailServer, EmailSettings, ProviderSettings
from mcp_email_server.emails.classic import ClassicEmailHandler
from mcp_email_server.emails.dispatcher import dispatch_handler


class TestDispatcher:
    def test_dispatch_handler_with_email_settings(self):
        """Test dispatch_handler with valid email account."""
        # Create test email settings
        email_settings = EmailSettings(
            account_name="test_account",
            full_name="Test User",
            email_address="test@example.com",
            incoming=EmailServer(
                user_name="test_user",
                password="test_password",
                host="imap.example.com",
                port=993,
                use_ssl=True,
            ),
            outgoing=EmailServer(
                user_name="test_user",
                password="test_password",
                host="smtp.example.com",
                port=465,
                use_ssl=True,
            ),
        )

        # Mock the get_settings function to return our settings
        mock_settings = MagicMock()
        mock_settings.get_account.return_value = email_settings

        with patch("mcp_email_server.emails.dispatcher.get_settings", return_value=mock_settings):
            # Call the function
            handler = dispatch_handler("test_account")

            # Verify the result
            assert isinstance(handler, ClassicEmailHandler)
            assert handler.email_settings == email_settings

            # Verify get_account was called correctly
            mock_settings.get_account.assert_called_once_with("test_account")

    def test_dispatch_handler_with_provider_settings(self):
        """Test dispatch_handler with provider account (should raise NotImplementedError)."""
        # Create test provider settings
        provider_settings = ProviderSettings(
            account_name="test_provider",
            provider_name="test",
            api_key="test_key",
        )

        # Mock the get_settings function to return our settings
        mock_settings = MagicMock()
        mock_settings.get_account.return_value = provider_settings

        with patch("mcp_email_server.emails.dispatcher.get_settings", return_value=mock_settings):
            # Call the function and expect NotImplementedError
            with pytest.raises(NotImplementedError):
                dispatch_handler("test_provider")

            # Verify get_account was called correctly
            mock_settings.get_account.assert_called_once_with("test_provider")

    def test_dispatch_handler_with_nonexistent_account(self):
        """Test dispatch_handler with non-existent account (should raise ValueError)."""
        configured_email = EmailSettings(
            account_name="account1",
            full_name="Test User",
            email_address="test@example.com",
            incoming=EmailServer(
                user_name="test_user",
                password="test_password",
                host="imap.example.com",
                port=993,
                use_ssl=True,
            ),
            outgoing=EmailServer(
                user_name="test_user",
                password="test_password",
                host="smtp.example.com",
                port=465,
                use_ssl=True,
            ),
        )
        configured_provider = ProviderSettings(
            account_name="account2",
            provider_name="test",
            api_key="test_api_key",
        )

        # Mock the get_settings function to return None for get_account
        mock_settings = MagicMock()
        mock_settings.get_account.return_value = None
        mock_settings.get_accounts.return_value = [configured_email, configured_provider]

        with patch("mcp_email_server.emails.dispatcher.get_settings", return_value=mock_settings):
            # Call the function and expect ValueError
            with pytest.raises(ValueError) as excinfo:
                dispatch_handler("nonexistent_account")

            # Verify the error message
            error_message = str(excinfo.value)
            assert "Account nonexistent_account not found" in error_message
            assert "account1" in error_message
            assert "account2" in error_message
            assert "test_password" not in error_message
            assert "test_api_key" not in error_message

            # Verify get_account was called correctly
            mock_settings.get_account.assert_called_once_with("nonexistent_account")
            mock_settings.get_accounts.assert_called_once()
