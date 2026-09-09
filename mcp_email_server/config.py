from __future__ import annotations

import datetime
import os
import re
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import tomli_w
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_serializer, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from mcp_email_server.log import logger
from mcp_email_server.paths import atomic_private_write, get_config_path

DEFAULT_CONFIG_PATH = str(get_config_path())

CONFIG_PATH = Path(os.getenv("MCP_EMAIL_SERVER_CONFIG_PATH", DEFAULT_CONFIG_PATH)).expanduser().resolve()
EMAIL_ADDRESS_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class OAuthAccount(BaseModel):
    """Public account metadata. Tokens live exclusively in the OS credential store."""

    provider: Literal["google", "microsoft"]
    client_id: str
    credential_id: str = Field(repr=False)
    tenant: str = "common"

    @field_validator("tenant")
    @classmethod
    def validate_tenant(cls, value: str) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9.-]+", value):
            raise ValueError("Invalid Microsoft tenant.")
        return value


class EmailServer(BaseModel):
    user_name: str
    password: str = Field(repr=False)
    host: str
    port: int
    use_ssl: bool = True  # Usually port 465
    start_ssl: bool = False  # Usually port 587

    def masked(self) -> EmailServer:
        return self.model_copy(update={"password": "********"})


class AccountAttributes(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    account_name: str
    description: str = ""
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(ZoneInfo("UTC")))
    updated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(ZoneInfo("UTC")))

    @model_validator(mode="after")
    def update_updated_at(self) -> AccountAttributes:
        """Update without mutating class-wide validation settings."""
        object.__setattr__(self, "updated_at", datetime.datetime.now(ZoneInfo("UTC")))
        return self

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AccountAttributes):
            return NotImplemented
        return self.model_dump(exclude={"created_at", "updated_at"}) == other.model_dump(
            exclude={"created_at", "updated_at"}
        )

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, v: datetime.datetime) -> str:
        return v.isoformat()

    def masked(self) -> AccountAttributes:
        return self.model_copy()


class EmailSettings(AccountAttributes):
    full_name: str
    email_address: str
    incoming: EmailServer
    outgoing: EmailServer
    save_to_sent: bool = True  # Save sent emails to IMAP Sent folder
    sent_folder_name: str | None = None  # Override Sent folder name (auto-detect if None)
    oauth: OAuthAccount | None = None

    @model_validator(mode="after")
    def validate_oauth_servers(self) -> EmailSettings:
        if self.oauth:
            hosts = {
                "google": ("imap.gmail.com", "smtp.gmail.com"),
                "microsoft": ("outlook.office365.com", "smtp.office365.com"),
            }[self.oauth.provider]
            if (self.incoming.host, self.outgoing.host) != hosts:
                raise ValueError("OAuth credentials must only be sent to the selected provider's mail servers.")
            if not self.incoming.use_ssl or not (self.outgoing.use_ssl or self.outgoing.start_ssl):
                raise ValueError("OAuth requires encrypted IMAP and SMTP connections.")
            if not EMAIL_ADDRESS_REGEX.fullmatch(self.email_address):
                raise ValueError("Invalid OAuth mailbox address.")
            if self.incoming.user_name != self.email_address or self.outgoing.user_name != self.email_address:
                raise ValueError("OAuth login must match the configured mailbox address.")
        return self

    @classmethod
    def init(
        cls,
        *,
        account_name: str,
        full_name: str,
        email_address: str,
        user_name: str,
        password: str,
        imap_host: str,
        smtp_host: str,
        imap_user_name: str | None = None,
        imap_password: str | None = None,
        imap_port: int = 993,
        imap_ssl: bool = True,
        smtp_port: int = 465,
        smtp_ssl: bool = True,
        smtp_start_ssl: bool = False,
        smtp_user_name: str | None = None,
        smtp_password: str | None = None,
        save_to_sent: bool = True,
        sent_folder_name: str | None = None,
    ) -> EmailSettings:
        return cls(
            account_name=account_name,
            full_name=full_name,
            email_address=email_address,
            incoming=EmailServer(
                user_name=imap_user_name or user_name,
                password=imap_password or password,
                host=imap_host,
                port=imap_port,
                use_ssl=imap_ssl,
            ),
            outgoing=EmailServer(
                user_name=smtp_user_name or user_name,
                password=smtp_password or password,
                host=smtp_host,
                port=smtp_port,
                use_ssl=smtp_ssl,
                start_ssl=smtp_start_ssl,
            ),
            save_to_sent=save_to_sent,
            sent_folder_name=sent_folder_name,
        )

    @classmethod
    def from_env(cls) -> EmailSettings | None:
        """Create EmailSettings from environment variables.

        Expected environment variables:
        - MCP_EMAIL_SERVER_ACCOUNT_NAME (default: "default")
        - MCP_EMAIL_SERVER_FULL_NAME
        - MCP_EMAIL_SERVER_EMAIL_ADDRESS
        - MCP_EMAIL_SERVER_USER_NAME
        - MCP_EMAIL_SERVER_PASSWORD
        - MCP_EMAIL_SERVER_IMAP_HOST
        - MCP_EMAIL_SERVER_IMAP_PORT (default: 993)
        - MCP_EMAIL_SERVER_IMAP_SSL (default: true)
        - MCP_EMAIL_SERVER_SMTP_HOST
        - MCP_EMAIL_SERVER_SMTP_PORT (default: 465)
        - MCP_EMAIL_SERVER_SMTP_SSL (default: true)
        - MCP_EMAIL_SERVER_SMTP_START_SSL (default: false)
        - MCP_EMAIL_SERVER_SAVE_TO_SENT (default: true)
        - MCP_EMAIL_SERVER_SENT_FOLDER_NAME (default: auto-detect)
        """
        # Check if minimum required environment variables are set
        email_address = os.getenv("MCP_EMAIL_SERVER_EMAIL_ADDRESS")
        password = os.getenv("MCP_EMAIL_SERVER_PASSWORD")

        if not email_address or not password:
            return None

        # Parse boolean values
        def parse_bool(value: str | None, default: bool = True) -> bool:
            if value is None:
                return default
            return value.lower() in ("true", "1", "yes", "on")

        # Get all environment variables with defaults
        account_name = os.getenv("MCP_EMAIL_SERVER_ACCOUNT_NAME", "default")
        full_name = os.getenv("MCP_EMAIL_SERVER_FULL_NAME", email_address.split("@")[0])
        user_name = os.getenv("MCP_EMAIL_SERVER_USER_NAME", email_address)
        imap_host = os.getenv("MCP_EMAIL_SERVER_IMAP_HOST")
        smtp_host = os.getenv("MCP_EMAIL_SERVER_SMTP_HOST")

        # Required fields check
        if not imap_host or not smtp_host:
            logger.warning("Missing required email configuration environment variables (IMAP_HOST or SMTP_HOST)")
            return None

        try:
            return cls.init(
                account_name=account_name,
                full_name=full_name,
                email_address=email_address,
                user_name=user_name,
                password=password,
                imap_host=imap_host,
                imap_port=int(os.getenv("MCP_EMAIL_SERVER_IMAP_PORT", "993")),
                imap_ssl=parse_bool(os.getenv("MCP_EMAIL_SERVER_IMAP_SSL"), True),
                smtp_host=smtp_host,
                smtp_port=int(os.getenv("MCP_EMAIL_SERVER_SMTP_PORT", "465")),
                smtp_ssl=parse_bool(os.getenv("MCP_EMAIL_SERVER_SMTP_SSL"), True),
                smtp_start_ssl=parse_bool(os.getenv("MCP_EMAIL_SERVER_SMTP_START_SSL"), False),
                smtp_user_name=os.getenv("MCP_EMAIL_SERVER_SMTP_USER_NAME", user_name),
                smtp_password=os.getenv("MCP_EMAIL_SERVER_SMTP_PASSWORD", password),
                imap_user_name=os.getenv("MCP_EMAIL_SERVER_IMAP_USER_NAME", user_name),
                imap_password=os.getenv("MCP_EMAIL_SERVER_IMAP_PASSWORD", password),
                save_to_sent=parse_bool(os.getenv("MCP_EMAIL_SERVER_SAVE_TO_SENT"), True),
                sent_folder_name=os.getenv("MCP_EMAIL_SERVER_SENT_FOLDER_NAME"),
            )
        except (ValueError, TypeError):
            logger.error("Invalid email environment configuration; check required values and ports.")
            return None

    def masked(self) -> EmailSettings:
        return self.model_copy(
            update={
                "incoming": self.incoming.masked(),
                "outgoing": self.outgoing.masked(),
                "oauth": self.oauth.model_copy(update={"credential_id": "********"}) if self.oauth else None,
            }
        )


class ProviderSettings(AccountAttributes):
    provider_name: str
    api_key: str = Field(repr=False)

    def masked(self) -> AccountAttributes:
        return self.model_copy(update={"api_key": "********"})


class AiSendsEmailToolSettings(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    allowed_account_name: str | None = None
    allowed_recipients: list[str] = Field(default_factory=list)

    @field_validator("allowed_account_name", mode="before")
    @classmethod
    def normalize_account_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("allowed_recipients", mode="before")
    @classmethod
    def normalize_recipients(cls, value: list[str] | None) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError("allowed_recipients must be a list of email addresses")

        normalized_recipients: list[str] = []
        seen: set[str] = set()
        invalid: list[str] = []
        for recipient in value:
            if not isinstance(recipient, str):
                invalid.append(str(recipient))
                continue

            normalized = recipient.strip().lower()
            if not normalized:
                continue
            if not EMAIL_ADDRESS_REGEX.fullmatch(normalized):
                invalid.append(recipient)
                continue
            if normalized in seen:
                continue

            seen.add(normalized)
            normalized_recipients.append(normalized)

        if invalid:
            raise ValueError("Invalid email address format.")

        return normalized_recipients


def _parse_bool_env(value: str | None, default: bool = False) -> bool:
    """Parse boolean value from environment variable."""
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes", "on")


class Settings(BaseSettings):
    _config_path: Path = PrivateAttr(default_factory=get_config_path)
    _env_account_name: str | None = PrivateAttr(default=None)
    _original_env_email: EmailSettings | None = PrivateAttr(default=None)
    emails: list[EmailSettings] = []
    providers: list[ProviderSettings] = []
    ai_sends_email_tool: AiSendsEmailToolSettings = Field(default_factory=AiSendsEmailToolSettings)
    db_location: str = CONFIG_PATH.with_name("db.sqlite3").as_posix()
    enable_attachment_download: bool = False

    model_config = SettingsConfigDict(toml_file=CONFIG_PATH, validate_assignment=True, revalidate_instances="always")

    def __init__(self, **data: Any) -> None:
        """Initialize Settings with support for environment variables."""
        super().__init__(**data)
        if "db_location" not in self.model_fields_set:
            self.db_location = str(self._config_path.with_name("db.sqlite3"))

        # Check for enable_attachment_download from environment variable
        env_enable_attachment = os.getenv("MCP_EMAIL_SERVER_ENABLE_ATTACHMENT_DOWNLOAD")
        if env_enable_attachment is not None:
            self.enable_attachment_download = _parse_bool_env(env_enable_attachment, False)
            logger.info(f"Set enable_attachment_download={self.enable_attachment_download} from environment variable")

        # Check for email configuration from environment variables
        env_email = EmailSettings.from_env()
        if env_email:
            self._env_account_name = env_email.account_name
            # Check if this account already exists (from TOML)
            existing_account = None
            for i, email in enumerate(self.emails):
                if email.account_name == env_email.account_name:
                    existing_account = i
                    break

            if existing_account is not None:
                self._original_env_email = self.emails[existing_account].model_copy(deep=True)
                # Replace existing account with env configuration
                self.emails[existing_account] = env_email
                logger.info(f"Overriding email account '{env_email.account_name}' with environment variables")
            else:
                # Add new account from env
                self.emails.insert(0, env_email)
                logger.info(f"Added email account '{env_email.account_name}' from environment variables")

    def add_email(self, email: EmailSettings) -> None:
        """Use re-assigned for validation to work."""
        self.emails = [email, *self.emails]

    def add_provider(self, provider: ProviderSettings) -> None:
        """Use re-assigned for validation to work."""
        self.providers = [provider, *self.providers]

    def delete_email(self, account_name: str) -> None:
        """Use re-assigned for validation to work."""
        self.emails = [email for email in self.emails if email.account_name != account_name]
        if self.ai_sends_email_tool.allowed_account_name == account_name:
            self.ai_sends_email_tool.allowed_account_name = None
            self.ai_sends_email_tool.allowed_recipients = []

    def delete_provider(self, account_name: str) -> None:
        """Use re-assigned for validation to work."""
        self.providers = [provider for provider in self.providers if provider.account_name != account_name]

    def get_account(self, account_name: str, masked: bool = False) -> EmailSettings | ProviderSettings | None:
        for email in self.emails:
            if email.account_name == account_name:
                return email if not masked else email.masked()
        for provider in self.providers:
            if provider.account_name == account_name:
                return provider if not masked else provider.masked()
        return None

    def get_accounts(self, masked: bool = False) -> list[EmailSettings | ProviderSettings]:
        accounts = self.emails + self.providers
        if masked:
            return [account.masked() for account in accounts]
        return accounts

    @model_validator(mode="after")
    def check_unique_account_names(self) -> Settings:
        account_names = set()
        for email in self.emails:
            if email.account_name in account_names:
                raise ValueError(f"Duplicate account name {email.account_name}")
            account_names.add(email.account_name)
        for provider in self.providers:
            if provider.account_name in account_names:
                raise ValueError(f"Duplicate account name {provider.account_name}")
            account_names.add(provider.account_name)

        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, TomlConfigSettingsSource(settings_cls, toml_file=get_config_path()))

    def _to_toml(self) -> str:
        data = self.model_dump(exclude_none=True)
        if self._env_account_name:
            data["emails"] = [e for e in data["emails"] if e["account_name"] != self._env_account_name]
            if self._original_env_email:
                data["emails"].append(self._original_env_email.model_dump(exclude_none=True))
        if os.getenv("MCP_EMAIL_SERVER_ENABLE_ATTACHMENT_DOWNLOAD") is not None:
            # Keep the on-disk value rather than persisting a deployment override.
            stored = TomlConfigSettingsSource(type(self), toml_file=self._config_path)()
            data["enable_attachment_download"] = stored.get("enable_attachment_download", False)
        return tomli_w.dumps(data)

    def store(self) -> None:
        toml_file = self._config_path
        atomic_private_write(toml_file, self._to_toml())
        logger.info(f"Settings stored in {toml_file}")


_settings = None
_settings_signature = None


def get_settings(reload: bool = False) -> Settings:
    global _settings, _settings_signature
    path = get_config_path()
    signature = (path, path.stat().st_mtime_ns if path.exists() else None)
    if not _settings or reload or signature != _settings_signature:
        logger.info(f"Loading settings from {path}")
        _settings = Settings()
        _settings_signature = signature
    return _settings


def store_settings(settings: Settings | None = None) -> None:
    if not settings:
        settings = get_settings()
    settings.store()
    return


def delete_settings() -> None:
    global _settings, _settings_signature
    _settings = None
    _settings_signature = None
    path = get_config_path()
    if not path.exists():
        logger.info(f"Settings file {path} does not exist")
        return
    path.unlink()
    logger.info(f"Deleted settings file {path}")
