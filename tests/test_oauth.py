# ruff: noqa: S105 - isolated test credentials
import base64
import io
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
from pydantic import ValidationError

from mcp_email_server.config import OAuthAccount, get_settings
from mcp_email_server.emails.classic import EmailClient
from mcp_email_server.oauth import LoginError, PendingLogin, _access_token, _exchange, save_clients
from mcp_email_server.setup import build_account, save_account
from tests.test_setup import form


@pytest.fixture
def auth():
    return OAuthAccount(provider="google", client_id="customer-id", credential_id="test-credential")


@pytest.fixture
def vault(monkeypatch):
    records = {}
    monkeypatch.setattr("keyring.get_password", lambda service, key: records.get(key))
    monkeypatch.setattr("keyring.set_password", lambda service, key, value: records.update({key: value}))
    monkeypatch.setattr("keyring.delete_password", lambda service, key: records.pop(key, None))
    return records


def test_refresh_rotation_and_secret_not_in_configuration(auth, vault):
    vault[auth.credential_id] = json.dumps({"refresh_token": "old-refresh", "expires_at": 0})
    with patch(
        "mcp_email_server.oauth.httpx.post",
        return_value=httpx.Response(
            200,
            json={
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 3600,
            },
        ),
    ) as post:
        assert _access_token(auth) == "new-access"
        assert _access_token(auth) == "new-access"
        assert post.call_count == 1
    assert json.loads(vault[auth.credential_id])["refresh_token"] == "new-refresh"
    account = build_account(form(provider="google"), oauth=auth)
    save_account(account)
    assert "new-access" not in get_settings()._to_toml()
    assert "new-refresh" not in get_settings()._to_toml()
    assert auth.credential_id not in account.masked().model_dump_json()


def test_refresh_keeps_old_refresh_when_provider_omits_it(auth, vault):
    vault[auth.credential_id] = json.dumps({"refresh_token": "old-refresh", "expires_at": 0})
    with patch("mcp_email_server.oauth.httpx.post", return_value=httpx.Response(200, json={"access_token": "access"})):
        _access_token(auth)
    assert json.loads(vault[auth.credential_id])["refresh_token"] == "old-refresh"


@pytest.mark.parametrize("status", [400, 401, 500])
def test_token_errors_do_not_expose_response(status, auth):
    with patch("mcp_email_server.oauth.httpx.post", return_value=httpx.Response(status, text="secret")):
        with pytest.raises(LoginError) as error:
            _exchange(auth, {})
    assert "secret" not in str(error.value)


def test_missing_keyring_has_actionable_message(auth, monkeypatch):
    monkeypatch.setattr("keyring.get_password", MagicMock(side_effect=RuntimeError("secret")))
    with pytest.raises(LoginError, match="Schlüsselbund") as error:
        _access_token(auth)
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("provider", ["google", "microsoft"])
def test_login_pkce_state_callback_and_one_use(provider, vault):
    save_clients("google-client", "desktop-value", "microsoft-client", "common")
    with patch("mcp_email_server.oauth.HTTPServer") as server, patch.object(PendingLogin, "_listen"):
        server.return_value.server_port = 9843
        login = PendingLogin(provider, "test@example.com")
        params = parse_qs(urlsplit(login.url).query)
        assert params["code_challenge_method"] == ["S256"]
        assert params["state"] == [login.state]
        assert "code_verifier" not in params
        assert login.verifier not in login.url
        assert urlsplit(login.redirect_uri).hostname == ("localhost" if provider == "microsoft" else "127.0.0.1")
        callback_cls = server.call_args.args[1]
        callback = object.__new__(callback_cls)
        callback.send_error = MagicMock()
        callback.send_response = MagicMock()
        callback.send_header = MagicMock()
        callback.end_headers = MagicMock()
        callback.wfile = io.BytesIO()
        callback.path = "/?" + urlencode({"state": "incorrect", "code": "stolen"})
        callback.do_GET()
        assert not login.done.is_set()
        callback.send_error.assert_called_once()
        callback.path = "/?" + urlencode({"state": login.state, "code": "one-use"})
        callback.do_GET()
        assert login.done.is_set()
        with patch(
            "mcp_email_server.oauth.httpx.post",
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "access",
                    "refresh_token": "refresh",
                    "expires_in": 3600,
                },
            ),
        ) as post:
            account = login.finish()
            assert post.call_args.kwargs["data"]["code_verifier"] == login.verifier
            assert account.provider == provider
            assert account.credential_id in vault
            with pytest.raises(LoginError, match="verwendet"):
                login.finish()


def test_oauth_requires_registration_before_opening_listener():
    with patch("mcp_email_server.oauth.HTTPServer") as server, pytest.raises(LoginError, match="eingerichtet"):
        PendingLogin("google", "test@example.com")
    server.assert_not_called()


async def test_imap_and_smtp_use_xoauth2_not_password(auth, vault):
    vault[auth.credential_id] = json.dumps({"access_token": "access", "expires_at": time.time() + 3600})
    account = build_account(form(provider="google"), oauth=auth)
    incoming = EmailClient(account.incoming, oauth=auth)
    outgoing = EmailClient(account.outgoing, oauth=auth)
    imap = AsyncMock()
    imap.xoauth2.return_value = ("OK", [])
    smtp = AsyncMock()
    smtp.execute_command.return_value = MagicMock(code=235)
    await incoming.login_imap(imap)
    await outgoing.login_smtp(smtp)
    imap.login.assert_not_called()
    smtp.login.assert_not_called()
    imap.xoauth2.assert_awaited_once_with("test@example.com", "access")
    payload = base64.b64decode(smtp.execute_command.call_args.args[2]).decode()
    assert payload == "user=test@example.com\x01auth=Bearer access\x01\x01"


async def test_imap_rejected_password_is_not_reported_as_success(email_server):
    imap = AsyncMock()
    imap.login.return_value = ("NO", [b"invalid"])
    with pytest.raises(PermissionError):
        await EmailClient(email_server).login_imap(imap)


def test_oauth_cannot_redirect_tokens_to_custom_servers(auth):
    account = build_account(form(provider="google"), oauth=auth)
    data = account.model_dump()
    data["incoming"]["host"] = "attacker.example"
    with pytest.raises(ValidationError, match="selected provider"):
        type(account).model_validate(data)
