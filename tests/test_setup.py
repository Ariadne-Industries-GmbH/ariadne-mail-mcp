# ruff: noqa: S105 - isolated test credentials
import json
import os
from unittest.mock import AsyncMock, patch

import pytest

from mcp_email_server.config import AiSendsEmailToolSettings, Settings, get_settings
from mcp_email_server.integrations import client_config, register_ariadne
from mcp_email_server.paths import atomic_private_write, get_config_path, migrate_legacy_config
from mcp_email_server.setup import DEFAULTS, FIELDS, SetupError, build_account, check_account, load_form, save_account


def form(**updates):
    values = dict(zip(FIELDS, DEFAULTS, strict=True))
    values.update(
        account_name="work",
        email_address="test@example.com",
        password="secret",
        imap_host="imap.example.com",
        smtp_host="smtp.example.com",
    )
    values.update(updates)
    return values


def test_edit_keeps_passwords_and_send_permissions():
    account = build_account(form())
    save_account(account)
    settings = get_settings(reload=True)
    settings.ai_sends_email_tool = AiSendsEmailToolSettings(
        allowed_account_name="work", allowed_recipients=["a@example.com"]
    )
    settings.store()
    public_form = load_form("work")
    assert "secret" not in public_form
    changed = build_account(form(password="", full_name="New Name"), "work")
    save_account(changed, "work")
    result = get_settings(reload=True)
    assert len(result.emails) == 1
    assert result.emails[0].incoming.password == "secret"
    assert result.emails[0].full_name == "New Name"
    assert result.ai_sends_email_tool.allowed_account_name == "work"


@pytest.mark.parametrize(
    "updates",
    [
        {"email_address": "bad"},
        {"imap_port": 0},
        {"smtp_port": 65536},
        {"smtp_port": 25.5},
        {"imap_host": "https://example.com"},
        {"password": ""},
    ],
)
def test_invalid_form_does_not_persist_or_expose_password(updates):
    with pytest.raises(SetupError) as error:
        build_account(form(**updates))
    assert "secret" not in str(error.value)
    assert not get_config_path().exists()


def test_duplicate_or_renamed_account_rejected():
    save_account(build_account(form()))
    with pytest.raises(SetupError):
        build_account(form())
    with pytest.raises(SetupError):
        build_account(form(account_name="renamed"), "work")


def test_environment_overrides_are_not_written_to_disk(monkeypatch):
    save_account(build_account(form()))
    monkeypatch.setenv("MCP_EMAIL_SERVER_ACCOUNT_NAME", "work")
    monkeypatch.setenv("MCP_EMAIL_SERVER_EMAIL_ADDRESS", "env@example.com")
    monkeypatch.setenv("MCP_EMAIL_SERVER_PASSWORD", "environment-secret")
    monkeypatch.setenv("MCP_EMAIL_SERVER_IMAP_HOST", "imap.env.com")
    monkeypatch.setenv("MCP_EMAIL_SERVER_SMTP_HOST", "smtp.env.com")
    settings = Settings()
    assert settings.emails[0].incoming.password == "environment-secret"
    settings.store()
    assert "environment-secret" not in get_config_path().read_text()
    assert 'password = "secret"' in get_config_path().read_text()
    with pytest.raises(SetupError, match="Umgebungsvariablen"):
        build_account(form(password=""), "work")


def test_new_environment_account_not_persisted(monkeypatch):
    monkeypatch.setenv("MCP_EMAIL_SERVER_EMAIL_ADDRESS", "env@example.com")
    monkeypatch.setenv("MCP_EMAIL_SERVER_PASSWORD", "environment-secret")
    monkeypatch.setenv("MCP_EMAIL_SERVER_IMAP_HOST", "imap.env.com")
    monkeypatch.setenv("MCP_EMAIL_SERVER_SMTP_HOST", "smtp.env.com")
    Settings().store()
    assert "environment-secret" not in get_config_path().read_text()


def test_config_follows_environment_path_and_reloads(tmp_path, monkeypatch):
    first = get_settings()
    other = tmp_path / "other.toml"
    atomic_private_write(other, "enable_attachment_download = true\n")
    monkeypatch.setenv("MCP_EMAIL_SERVER_CONFIG_PATH", str(other))
    assert get_settings() is not first
    assert get_settings().enable_attachment_download
    atomic_private_write(other, "enable_attachment_download = false\n")
    assert not get_settings().enable_attachment_download


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_atomic_config_owner_only_and_preserves_old_file_on_failure(monkeypatch):
    path = get_config_path()
    atomic_private_write(path, "original")
    assert path.stat().st_mode & 0o777 == 0o600
    with patch("mcp_email_server.paths.os.replace", side_effect=OSError("disk full")), pytest.raises(OSError):
        atomic_private_write(path, "replacement")
    assert path.read_text() == "original"
    assert not list(path.parent.glob(".email-*"))


def test_legacy_migration_preserves_source_and_existing_destination(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_EMAIL_SERVER_CONFIG_PATH")
    monkeypatch.setattr("mcp_email_server.paths.get_config_path", lambda: tmp_path / "new" / "config.toml")
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "mcp_email_server" / "config.toml"
    atomic_private_write(source, "emails = []\n")
    assert migrate_legacy_config() == source
    assert source.exists()
    assert (tmp_path / "new" / "config.toml").read_text() == source.read_text()
    assert migrate_legacy_config() is None


async def test_connection_test_reports_both_protocols_without_sending(email_settings):
    with patch("mcp_email_server.setup.ClassicEmailHandler") as factory:
        handler = factory.return_value
        handler.incoming_client.test_connection = AsyncMock()
        handler.outgoing_client.test_connection = AsyncMock(side_effect=PermissionError("secret"))
        results = await check_account(email_settings)
        assert results[0][1] is True
        assert results[1][1] is False
        assert "secret" not in str(results)
        handler.send_email.assert_not_called()


def test_export_is_valid_json_with_windows_paths():
    command = r"C:\Program Files\Mail\mcp-email-server.exe"
    exported = json.loads(client_config(command))["mcpServers"]["email"]
    assert exported["command"] == command
    assert exported["args"] == ["stdio"]
    assert exported["env"]["MCP_EMAIL_SERVER_CONFIG_PATH"] == str(get_config_path())


def test_ariadne_handles_wrapped_lookup_and_redacts_errors():
    with patch("mcp_email_server.integrations.httpx.Client") as factory:
        client = factory.return_value.__enter__.return_value
        response = client.post.return_value
        response.status_code = 200
        response.is_success = True
        response.json.return_value = {"data": {"key": "existing"}}
        result = register_ariadne("token", "https://engine.example/api", "email", "/mail", "", "")
        assert "aktualisiert" in result
        request = client.post.call_args.kwargs["json"]
        assert request["thread_name"] == "update-mcp-server-spec"
        assert request["payload"]["path_params"] == {"key": "existing"}
