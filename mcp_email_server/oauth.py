"""Desktop authorization-code + PKCE login and OS-keyring token persistence."""

import asyncio
import base64
import hashlib
import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import keyring

from mcp_email_server.config import OAuthAccount
from mcp_email_server.paths import atomic_private_write, get_config_path

SERVICE = "mcp-email-server"
SCOPES = {
    "google": "https://mail.google.com/",
    "microsoft": "offline_access https://outlook.office.com/IMAP.AccessAsUser.All https://outlook.office.com/SMTP.Send",
}
HOSTS = {
    "google": ("imap.gmail.com", "smtp.gmail.com"),
    "microsoft": ("outlook.office365.com", "smtp.office365.com"),
}


class LoginError(Exception):
    """Safe, actionable message; never include raw provider responses or tokens."""


def load_clients() -> dict[str, dict[str, str]]:
    bundled = Path(__file__).with_name("oauth-clients.json")
    local = get_config_path().with_name("oauth-clients.json")
    clients = {provider: {} for provider in SCOPES}
    for path in (bundled, local):
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for provider in clients:
                    clients[provider].update(data.get(provider, {}))
            except (ValueError, TypeError, AttributeError):
                raise LoginError("The OAuth app configuration is invalid. Check the setup.") from None
    for provider, values in clients.items():
        for field in ("client_id", "client_secret", "tenant"):
            value = os.getenv(f"MCP_EMAIL_SERVER_{provider.upper()}_{field.upper()}")
            if value is not None:
                values[field] = value
    return clients


def save_clients(google_id: str, google_secret: str, microsoft_id: str, tenant: str) -> None:
    clients = load_clients()
    # A desktop Google client secret identifies a public app; it is not a user token.
    clients["google"] = {"client_id": google_id.strip(), "client_secret": google_secret.strip()}
    clients["microsoft"] = {"client_id": microsoft_id.strip(), "tenant": tenant.strip() or "common"}
    OAuthAccount(provider="microsoft", client_id=microsoft_id, credential_id="validation", tenant=tenant or "common")
    atomic_private_write(get_config_path().with_name("oauth-clients.json"), json.dumps(clients, indent=2))


def _read_tokens(credential_id: str) -> dict[str, Any]:
    try:
        raw = keyring.get_password(SERVICE, credential_id)
        if raw:
            return json.loads(raw)
    except Exception:
        raise LoginError("The system keyring is unavailable or locked. Unlock it and try again.") from None
    raise LoginError("Sign-in credentials are missing. Reconnect the account with the provider.")


def _write_tokens(credential_id: str, tokens: dict[str, Any]) -> None:
    try:
        keyring.set_password(SERVICE, credential_id, json.dumps(tokens))
    except Exception:
        raise LoginError(
            "Sign-in credentials could not be saved to the system keyring. "
            "On Linux, an unlocked Secret Service keyring is required."
        ) from None


def remove_tokens(credential_id: str) -> None:
    try:
        keyring.delete_password(SERVICE, credential_id)
    except keyring.errors.PasswordDeleteError:
        pass
    except Exception:
        raise LoginError("Credentials could not be removed from the system keyring.") from None


def endpoints(account: OAuthAccount) -> tuple[str, str]:
    if account.provider == "google":
        return "https://accounts.google.com/o/oauth2/v2/auth", "https://oauth2.googleapis.com/token"
    base = f"https://login.microsoftonline.com/{account.tenant}/oauth2/v2.0"
    return f"{base}/authorize", f"{base}/token"


def _exchange(account: OAuthAccount, data: dict[str, str], client_secret: str = "") -> dict[str, Any]:
    data = {"client_id": account.client_id, **data}
    if account.provider == "google" and client_secret:
        data["client_secret"] = client_secret
    try:
        response = httpx.post(endpoints(account)[1], data=data, timeout=20)
        if response.status_code != 200:
            raise LoginError("Sign-in expired or was not approved. Reconnect and check the app permissions.")
        result = response.json()
        if not isinstance(result.get("access_token"), str) or not result["access_token"]:
            raise ValueError  # noqa: TRY301 - normalize provider failures at this boundary
        result["expires_at"] = time.time() + float(result.get("expires_in", 3600))
        return result
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        raise LoginError("The sign-in service is unavailable or returned an invalid response.") from None


def _access_token(account: OAuthAccount) -> str:
    tokens = _read_tokens(account.credential_id)
    if tokens.get("access_token") and tokens.get("expires_at", 0) > time.time() + 60:
        return tokens["access_token"]
    if not tokens.get("refresh_token"):
        raise LoginError("Reconnect the account to renew access.")
    renewed = _exchange(
        account,
        {
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
        },
        tokens.get("client_secret", ""),
    )
    # Some providers rotate refresh tokens; others omit them on refresh.
    tokens.update(renewed)
    _write_tokens(account.credential_id, tokens)
    return tokens["access_token"]


async def access_token(account: OAuthAccount) -> str:
    return await asyncio.to_thread(_access_token, account)


class PendingLogin:
    """A bounded, one-use loopback listener. Auth state stays server-side, never in Gradio state."""

    def __init__(self, provider: str, email_address: str):
        if provider not in SCOPES:
            raise LoginError("Unknown provider.")
        client = load_clients()[provider]
        if not client.get("client_id"):
            raise LoginError("This provider is not configured yet. Enter its OAuth app details in setup first.")
        self.account = OAuthAccount(
            provider=provider,
            client_id=client["client_id"],
            credential_id=secrets.token_hex(24),
            tenant=client.get("tenant", "common"),
        )
        self.client_secret = client.get("client_secret", "")
        self.state = secrets.token_urlsafe(32)
        self.verifier = secrets.token_urlsafe(64)
        self.code: str | None = None
        self.error: str | None = None
        self.done = threading.Event()
        self.deadline = time.monotonic() + 180
        pending = self

        class Callback(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:
                pass  # The URL contains a one-use authorization code.

            def do_GET(self) -> None:
                parsed = urlsplit(self.path)
                values = parse_qs(parsed.query)
                valid = parsed.path == "/" and secrets.compare_digest(values.get("state", [""])[0], pending.state)
                if not valid:
                    self.send_error(400, "Invalid login request")
                    return
                pending.code = values.get("code", [None])[0]
                if values.get("error") or not pending.code:
                    pending.error = "Sign-in was cancelled or not approved."
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(
                    b"<html lang='en'><title>Connect email</title><h1>Return to setup</h1>"
                    b"<p>You can close this window.</p></html>"
                )
                pending.done.set()

        self.server = HTTPServer(("127.0.0.1", 0), Callback)
        self.server.timeout = 0.5
        redirect_host = "localhost" if provider == "microsoft" else "127.0.0.1"
        self.redirect_uri = f"http://{redirect_host}:{self.server.server_port}/"
        challenge = base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).decode().rstrip("=")
        params = {
            "client_id": self.account.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": SCOPES[provider],
            "state": self.state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "login_hint": email_address,
        }
        if provider == "google":
            params.update(access_type="offline", prompt="consent")
        self.url = f"{endpoints(self.account)[0]}?{urlencode(params)}"
        self.thread = threading.Thread(target=self._listen, daemon=True)
        self.thread.start()

    def _listen(self) -> None:
        try:
            while not self.done.is_set() and time.monotonic() < self.deadline:
                self.server.handle_request()
        finally:
            self.server.server_close()
            if not self.done.is_set():
                self.error = "Sign-in timed out. Start again."
                self.done.set()

    def cancel(self) -> None:
        self.error = "Sign-in cancelled."
        self.done.set()

    def finish(self) -> OAuthAccount:
        if not self.done.is_set():
            raise LoginError("Complete sign-in in the browser.")
        if self.error:
            raise LoginError(self.error)
        if not self.code:
            raise LoginError("This sign-in has already been used.")
        code, self.code = self.code, None
        tokens = _exchange(
            self.account,
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
                "code_verifier": self.verifier,
            },
            self.client_secret,
        )
        if not tokens.get("refresh_token"):
            raise LoginError("Persistent access was not granted. Reconnect with offline access.")
        tokens["client_secret"] = self.client_secret
        _write_tokens(self.account.credential_id, tokens)
        return self.account
