import pytest
from pydantic import ValidationError

from mcp_email_server.config import (
    AiSendsEmailToolSettings,
    EmailServer,
    EmailSettings,
    ProviderSettings,
    get_settings,
    store_settings,
)


def test_config():
    settings = get_settings()
    assert settings.emails == []
    settings.emails.append(
        EmailSettings(
            account_name="email_test",
            full_name="Test User",
            email_address="1oBbE@example.com",
            incoming=EmailServer(
                user_name="test",
                password="test",
                host="imap.gmail.com",
                port=993,
                ssl=True,
            ),
            outgoing=EmailServer(
                user_name="test",
                password="test",
                host="smtp.gmail.com",
                port=587,
                ssl=True,
            ),
        )
    )
    settings.providers.append(ProviderSettings(account_name="provider_test", provider_name="test", api_key="test"))
    store_settings(settings)
    reloaded_settings = get_settings(reload=True)
    assert reloaded_settings == settings

    with pytest.raises(ValidationError):
        settings.add_email(
            EmailSettings(
                account_name="email_test",
                full_name="Test User",
                email_address="1oBbE@example.com",
                incoming=EmailServer(
                    user_name="test",
                    password="test",
                    host="imap.gmail.com",
                    port=993,
                    ssl=True,
                ),
                outgoing=EmailServer(
                    user_name="test",
                    password="test",
                    host="smtp.gmail.com",
                    port=587,
                    ssl=True,
                ),
            )
        )


def test_delete_email_clears_ai_send_tool_config():
    settings = get_settings()
    settings.emails = [
        EmailSettings(
            account_name="email_test",
            full_name="Test User",
            email_address="test@example.com",
            incoming=EmailServer(
                user_name="test",
                password="test",
                host="imap.gmail.com",
                port=993,
                ssl=True,
            ),
            outgoing=EmailServer(
                user_name="test",
                password="test",
                host="smtp.gmail.com",
                port=587,
                ssl=True,
            ),
        )
    ]
    settings.ai_sends_email_tool = AiSendsEmailToolSettings(
        allowed_account_name="email_test",
        allowed_recipients=["allowed@example.com"],
    )

    settings.delete_email("email_test")

    assert settings.emails == []
    assert settings.ai_sends_email_tool.allowed_account_name is None
    assert settings.ai_sends_email_tool.allowed_recipients == []
