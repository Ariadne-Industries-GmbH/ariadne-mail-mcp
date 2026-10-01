"""Testable account editing and connection diagnostics for the local setup UI."""

import asyncio
import os
from contextlib import suppress
from typing import Any

from mcp_email_server.config import EMAIL_ADDRESS_REGEX, EmailSettings, OAuthAccount, get_settings
from mcp_email_server.emails.classic import ClassicEmailHandler
from mcp_email_server.oauth import HOSTS, LoginError, remove_tokens

PROVIDERS = [("IMAP / SMTP", "manual"), ("Google / Gmail", "google"), ("Microsoft 365 / Outlook", "microsoft")]
TLS = "SSL/TLS"
STARTTLS = "STARTTLS"
PLAIN = "Unencrypted"
FIELDS = [
    "account_name",
    "full_name",
    "email_address",
    "provider",
    "user_name",
    "password",
    "imap_host",
    "imap_port",
    "imap_security",
    "imap_user_name",
    "imap_password",
    "smtp_host",
    "smtp_port",
    "smtp_security",
    "smtp_user_name",
    "smtp_password",
    "save_to_sent",
    "sent_folder_name",
]
DEFAULTS: list[Any] = ["", "", "", "manual", "", "", "", 993, TLS, "", "", "", 465, TLS, "", "", True, ""]


class SetupError(Exception):
    """An error safe to display without serializing a credential-bearing model."""


def env_managed(name: str) -> bool:
    return bool(
        os.getenv("MCP_EMAIL_SERVER_EMAIL_ADDRESS") and os.getenv("MCP_EMAIL_SERVER_PASSWORD")
    ) and name == os.getenv("MCP_EMAIL_SERVER_ACCOUNT_NAME", "default")


def load_form(name: str | None) -> list[Any]:
    account = get_settings(reload=True).get_account(name or "")
    if not isinstance(account, EmailSettings):
        return DEFAULTS.copy()
    i, o = account.incoming, account.outgoing
    return [
        account.account_name,
        account.full_name,
        account.email_address,
        account.oauth.provider if account.oauth else "manual",
        i.user_name,
        "",
        i.host,
        i.port,
        TLS if i.use_ssl else PLAIN,
        i.user_name,
        "",
        o.host,
        o.port,
        TLS if o.use_ssl else STARTTLS if o.start_ssl else PLAIN,
        o.user_name,
        "",
        account.save_to_sent,
        account.sent_folder_name or "",
    ]


def _port(raw: Any, label: str) -> int:
    try:
        port = int(raw)
        if port != float(raw) or not 1 <= port <= 65535:
            raise ValueError  # noqa: TRY301 - handled here as a field-specific validation error
        return port
    except (TypeError, ValueError, OverflowError):
        raise SetupError(f"{label}: Enter a port between 1 and 65535.") from None


def build_account(  # noqa: C901
    values: dict[str, Any], original: str | None = None, oauth: OAuthAccount | None = None
) -> EmailSettings:
    values = values.copy()
    for field in FIELDS:
        if isinstance(values.get(field), str) and "password" not in field:
            values[field] = values[field].strip()
    name, address = values["account_name"], values["email_address"]
    if not name:
        name = address
    if not EMAIL_ADDRESS_REGEX.fullmatch(address):
        raise SetupError("Enter a valid email address.")
    settings = get_settings(reload=True)
    existing = settings.get_account(original or "")
    if original and not isinstance(existing, EmailSettings):
        raise SetupError("This account no longer exists. Refresh the account list.")
    if (original and env_managed(original)) or env_managed(name):
        raise SetupError("This account is managed through environment variables. Change it there.")
    if original and name != original:
        raise SetupError("The internal account name cannot be changed while editing.")
    if not original and settings.get_account(name):
        raise SetupError("This account name is already in use. Choose another name.")
    provider = values["provider"]
    if provider not in {"manual", "google", "microsoft"}:
        raise SetupError("Select a valid provider.")
    if provider != "manual":
        if oauth is None and isinstance(existing, EmailSettings) and existing.oauth:
            if existing.email_address != address or existing.oauth.provider != provider:
                raise SetupError("Sign in again after changing the address or provider.")
            oauth = existing.oauth
        if oauth is None:
            raise SetupError("Sign in with the provider first.")
        if oauth.provider != provider:
            raise SetupError("This sign-in belongs to another provider.")
        imap_host, smtp_host = HOSTS[provider]
        account = EmailSettings.init(
            account_name=name,
            full_name=values["full_name"] or address,
            email_address=address,
            user_name=address,
            password="",
            imap_host=imap_host,
            smtp_host=smtp_host,
            smtp_port=587,
            smtp_ssl=False,
            smtp_start_ssl=True,
            save_to_sent=False,  # These providers file submitted mail themselves.
        )
        account.oauth = oauth
    else:
        old_i = existing.incoming if isinstance(existing, EmailSettings) and not existing.oauth else None
        old_o = existing.outgoing if isinstance(existing, EmailSettings) and not existing.oauth else None
        incoming_password = values["imap_password"] or values["password"] or (old_i.password if old_i else "")
        outgoing_password = values["smtp_password"] or values["password"] or (old_o.password if old_o else "")
        if not incoming_password or not outgoing_password:
            raise SetupError("Enter the password or app password.")
        for field in ("imap_host", "smtp_host"):
            host = values[field]
            if not host or any(c.isspace() for c in host) or "://" in host or "/" in host:
                raise SetupError("Enter server names without https:// or a path.")
        account = EmailSettings.init(
            account_name=name,
            full_name=values["full_name"] or address,
            email_address=address,
            user_name=values["user_name"] or address,
            password="",
            imap_host=values["imap_host"],
            smtp_host=values["smtp_host"],
            imap_port=_port(values["imap_port"], "IMAP"),
            smtp_port=_port(values["smtp_port"], "SMTP"),
            imap_ssl=values["imap_security"] == TLS,
            smtp_ssl=values["smtp_security"] == TLS,
            smtp_start_ssl=values["smtp_security"] == STARTTLS,
            imap_user_name=values["imap_user_name"] or None,
            smtp_user_name=values["smtp_user_name"] or None,
            imap_password=incoming_password,
            smtp_password=outgoing_password,
            save_to_sent=values["save_to_sent"],
            sent_folder_name=values["sent_folder_name"] or None,
        )
    if isinstance(existing, EmailSettings):
        account.created_at = existing.created_at
        account.description = existing.description
    return account


def save_account(account: EmailSettings, original: str | None = None) -> None:
    settings = get_settings(reload=True)
    old = settings.get_account(original or "")
    if env_managed(account.account_name):
        raise SetupError("This account is managed through environment variables.")
    if original:
        if not isinstance(old, EmailSettings):
            raise SetupError("The account was removed. Refresh and try again.")
        settings.emails = [account if e.account_name == original else e for e in settings.emails]
    else:
        if settings.get_account(account.account_name):
            raise SetupError("This account name is now in use. Refresh and try again.")
        settings.add_email(account)
    settings.store()
    if isinstance(old, EmailSettings) and old.oauth and old.oauth != account.oauth:
        with suppress(LoginError):
            remove_tokens(old.oauth.credential_id)


async def check_account(account: EmailSettings) -> list[tuple[str, bool, str]]:
    handler = ClassicEmailHandler(account)

    async def check(protocol: str) -> tuple[str, bool, str]:
        client = handler.incoming_client if protocol == "IMAP" else handler.outgoing_client
        try:
            await asyncio.wait_for(client.test_connection(protocol), timeout=25)
            return protocol, True, "Connection and sign-in succeeded."
        except LoginError as error:
            return protocol, False, str(error)
        except Exception:
            return protocol, False, "Sign-in failed. Check the server, credentials, TLS, and provider permissions."

    return list(await asyncio.gather(check("IMAP"), check("SMTP")))
