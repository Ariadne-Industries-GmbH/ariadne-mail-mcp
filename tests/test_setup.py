# ruff: noqa: S105 - isolated test credentials
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from mcp_email_server.cli import app as cli_app
from mcp_email_server.config import AiSendsEmailToolSettings, Settings, delete_settings, get_settings
from mcp_email_server.integrations import client_config, register_ariadne
from mcp_email_server.paths import (
    atomic_private_write,
    get_config_path,
    get_migration_marker_path,
    get_migration_record_path,
    get_profile_config_path,
    migrate_legacy_config,
)
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
    with pytest.raises(SetupError, match="environment variables"):
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


def test_frozen_binary_uses_directory_beside_executable(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_EMAIL_SERVER_CONFIG_PATH")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "profile"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "profile"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "app" / "mcp-email-server"))
    assert get_config_path() == tmp_path / "app" / "mcp_email_server" / "config.toml"
    assert get_profile_config_path() == tmp_path / "profile" / "zerolib" / "mcp_email_server" / "config.toml"
    monkeypatch.setenv("MCP_EMAIL_SERVER_CONFIG_PATH", str(tmp_path / "custom.toml"))
    assert get_config_path() == tmp_path / "custom.toml"


def test_python_install_keeps_profile_config_path(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_EMAIL_SERVER_CONFIG_PATH")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "profile"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "profile"))
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert get_config_path() == get_profile_config_path()


def test_frozen_binary_imports_profile_config_and_oauth_clients(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_EMAIL_SERVER_CONFIG_PATH")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "profile"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "profile"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "app" / "mcp-email-server"))
    source = get_profile_config_path()
    atomic_private_write(source, "enable_attachment_download = true\n")
    atomic_private_write(source.with_name("oauth-clients.json"), '{"google": {"client_id": "app"}}')
    assert migrate_legacy_config() == source
    assert get_config_path().read_text() == source.read_text()
    assert (
        get_config_path().with_name("oauth-clients.json").read_text()
        == source.with_name("oauth-clients.json").read_text()
    )
    assert source.exists()
    assert migrate_legacy_config() is None


def test_frozen_binary_preserves_existing_local_config(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_EMAIL_SERVER_CONFIG_PATH")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "profile"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "profile"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "app" / "mcp-email-server"))
    atomic_private_write(get_profile_config_path(), "enable_attachment_download = true\n")
    atomic_private_write(get_config_path(), "enable_attachment_download = false\n")
    assert migrate_legacy_config() is None
    assert get_config_path().read_text() == "enable_attachment_download = false\n"


def test_reset_removes_migrated_settings_and_prevents_reimport(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.delenv("MCP_EMAIL_SERVER_CONFIG_PATH")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "profile"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "profile"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "app" / "mcp-email-server"))
    profile = get_profile_config_path()
    atomic_private_write(profile, '[[emails]]\n[emails.oauth]\ncredential_id = "stored-token"\n')
    atomic_private_write(profile.with_name("oauth-clients.json"), "{}")
    migrate_legacy_config()
    assert get_migration_record_path().exists()
    with patch("mcp_email_server.oauth.remove_tokens") as remove_tokens:
        removed = delete_settings()
    remove_tokens.assert_called_once_with("stored-token")
    assert profile in removed
    assert not profile.exists()
    assert not profile.with_name("oauth-clients.json").exists()
    assert not get_config_path().exists()
    assert not get_config_path().with_name("oauth-clients.json").exists()
    assert get_migration_marker_path().exists()
    assert not get_migration_record_path().exists()
    assert migrate_legacy_config() is None


def test_reset_removes_recorded_working_directory_source_after_chdir(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.delenv("MCP_EMAIL_SERVER_CONFIG_PATH")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "profile"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "profile"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "app" / "ariadne-mail-mcp"))
    first_working_dir = tmp_path / "legacy-working-dir"
    first_working_dir.mkdir()
    monkeypatch.chdir(first_working_dir)
    source = first_working_dir / "mcp_email_server" / "config.toml"
    atomic_private_write(
        source,
        '[[emails]]\n[emails.incoming]\npassword = "old-password"\n[emails.oauth]\ncredential_id = "old-token"\n',
    )
    atomic_private_write(source.with_name("oauth-clients.json"), '{"google": {"client_id": "old-client"}}')
    assert migrate_legacy_config() == source
    assert get_migration_record_path().exists()

    later_working_dir = tmp_path / "later-working-dir"
    later_working_dir.mkdir()
    monkeypatch.chdir(later_working_dir)
    with patch("mcp_email_server.oauth.remove_tokens") as remove_tokens:
        removed = delete_settings()
    remove_tokens.assert_called_once_with("old-token")
    assert source in removed
    assert not source.exists()
    assert not source.with_name("oauth-clients.json").exists()
    assert not get_config_path().exists()
    assert not get_migration_record_path().exists()
    assert get_migration_marker_path().exists()


def test_reset_removes_current_legacy_working_directory_without_record(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.delenv("MCP_EMAIL_SERVER_CONFIG_PATH")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "profile"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "profile"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "app" / "ariadne-mail-mcp"))
    monkeypatch.chdir(tmp_path)
    old = tmp_path / "mcp_email_server" / "config.toml"
    atomic_private_write(old, '[[emails]]\n[emails.incoming]\npassword = "old-password"\n')
    atomic_private_write(old.with_name("oauth-clients.json"), "{}")

    removed = delete_settings()
    assert old in removed
    assert not old.exists()
    assert not old.with_name("oauth-clients.json").exists()


def test_reset_fails_closed_if_migration_record_is_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.delenv("MCP_EMAIL_SERVER_CONFIG_PATH")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "profile"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "profile"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "app" / "ariadne-mail-mcp"))
    target = get_config_path()
    atomic_private_write(target, '[[emails]]\n[emails.incoming]\npassword = "secret"\n')
    atomic_private_write(get_migration_record_path(), '{"source": "/unexpected/config.toml"}')

    with pytest.raises(ValueError, match="Invalid migration record"):
        delete_settings()
    assert target.exists()


def test_reset_command_reports_removed_locations(tmp_path):
    with patch("mcp_email_server.cli.delete_settings", return_value=[tmp_path / "mcp_email_server" / "config.toml"]):
        result = CliRunner().invoke(cli_app, ["reset", "--yes"])
    assert result.exit_code == 0
    assert str(tmp_path / "mcp_email_server" / "config.toml") in result.stdout


def test_reset_keeps_config_if_keyring_cleanup_fails(tmp_path, monkeypatch):
    path = get_config_path()
    atomic_private_write(path, '[[emails]]\n[emails.oauth]\ncredential_id = "stored-token"\n')
    with patch("mcp_email_server.oauth.remove_tokens", side_effect=RuntimeError("locked")):
        with pytest.raises(RuntimeError, match="locked"):
            delete_settings()
    assert path.exists()
    assert not get_migration_marker_path().exists()


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
    command = r"C:\Program Files\Mail\ariadne-mail-mcp.exe"
    document = json.loads(client_config(command))
    assert set(document) == {"mcpServers"}
    exported = document["mcpServers"]["ariadne-mail-mcp"]
    assert set(exported) == {"command", "args", "env"}
    assert exported["command"] == command
    assert exported["args"] == ["stdio"]
    assert exported["env"]["MCP_EMAIL_SERVER_CONFIG_PATH"] == str(get_config_path())


def test_cli_has_no_network_mcp_transport():
    help_text = CliRunner().invoke(cli_app, ["--help"])
    assert help_text.exit_code == 0
    assert "stdio" in help_text.stdout
    assert "sse" not in help_text.stdout
    assert "streamable-http" not in help_text.stdout


def test_setup_ui_binds_to_loopback_only():
    from mcp_email_server.ui import main as ui_main

    with patch("mcp_email_server.ui.migrate_legacy_config"), patch("mcp_email_server.ui.create_ui") as create_ui:
        ui_main(port=8766, open_browser=False)
    launch = create_ui.return_value.launch.call_args.kwargs
    assert launch["server_name"] == "127.0.0.1"
    assert launch["share"] is False
    assert launch["server_port"] == 8766


def test_ariadne_handles_wrapped_lookup_and_redacts_errors():
    with patch("mcp_email_server.integrations.httpx.Client") as factory:
        client = factory.return_value.__enter__.return_value
        response = client.post.return_value
        response.status_code = 200
        response.is_success = True
        response.json.return_value = {"data": {"key": "existing"}}
        result = register_ariadne("token", "https://engine.example/api", "email", "/mail", "", "")
        assert "updated" in result
        request = client.post.call_args.kwargs["json"]
        assert request["thread_name"] == "update-mcp-server-spec"
        assert request["payload"]["path_params"] == {"key": "existing"}
