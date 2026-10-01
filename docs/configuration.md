# Configuration reference

The setup UI writes `config.toml` for you. This page describes the file for administrators who edit or provision it directly. Run `ariadne-mail-mcp config-path` to print the active location. Restart an AI client's MCP process after changing its launch settings; a running process reloads TOML account changes on its next tool call.

## Minimal classic account

Replace every example address, host, and password with values supplied by your mail administrator. Keep the file outside Git and protect it from other users.

```toml
enable_attachment_download = false

[[emails]]
account_name = "work"
full_name = "Example User"
email_address = "user@example.com"
save_to_sent = true

[emails.incoming]
user_name = "user@example.com"
password = "IMAP_APP_PASSWORD"
host = "imap.example.com"
port = 993
use_ssl = true

[emails.outgoing]
user_name = "user@example.com"
password = "SMTP_APP_PASSWORD"
host = "smtp.example.com"
port = 465
use_ssl = true
start_ssl = false

[ai_sends_email_tool]
allowed_account_name = "work"
allowed_recipients = ["approved@example.com"]
```

Each `[[emails]]` section defines one mailbox. Add another `[[emails]]` section with its nested `[emails.incoming]` and `[emails.outgoing]` tables for each additional account. Account names must be unique. The UI may also write `description`, `created_at`, and `updated_at`; direct configuration does not require them.

## File fields

| TOML field | Meaning |
| --- | --- |
| `emails[].account_name` | Unique identifier used in MCP tool calls and sending permissions. |
| `emails[].full_name` | Sender display name. |
| `emails[].email_address` | Mailbox address. |
| `emails[].save_to_sent` | Save sent mail to an IMAP Sent folder. Defaults to `true`. |
| `emails[].sent_folder_name` | Optional Sent folder override; omitted means auto-detect. |
| `emails[].incoming.user_name`, `password`, `host`, `port` | IMAP login and server. These four fields are required for a classic account. |
| `emails[].incoming.use_ssl` | Direct TLS for IMAP; defaults to `true`. Port 993 is typical. |
| `emails[].outgoing.user_name`, `password`, `host`, `port` | SMTP login and server. These four fields are required for a classic account. |
| `emails[].outgoing.use_ssl` | Direct TLS for SMTP; defaults to `true`. Port 465 is typical. |
| `emails[].outgoing.start_ssl` | Upgrade SMTP with STARTTLS, commonly on port 587. For STARTTLS set `use_ssl = false` and `start_ssl = true`. |
| `ai_sends_email_tool.allowed_account_name` | The single account used by the restricted sending tool. Omit or leave unset to block sending. |
| `ai_sends_email_tool.allowed_recipients` | Email addresses accepted by the restricted sending tool. An empty list blocks sending. Addresses are normalized to lowercase. |
| `enable_attachment_download` | Defaults to `false`. Keep it disabled in this release; when enabled, an MCP caller can choose a destination path. |
| `db_location` | Optional internal database path. Normal mail setup does not need it. |
| `providers` | Legacy provider entries are part of the schema but have no mail handler. Use an `emails` entry for Google or Microsoft OAuth. |

The server supports unencrypted IMAP/SMTP settings, but they can expose credentials in transit. Use TLS or STARTTLS according to the provider's instructions.

## Email sending safety

The **published** sending tool is `send_email_to_allowed_recipients`. It is blocked by default because `allowed_account_name` and `allowed_recipients` are empty. To allow sending, set both fields as shown above or use the UI's **Permissions** tab. Every requested recipient must be on the allowlist. The unrestricted `send_email` function exists internally but is not published as an MCP tool.

`MCP_EMAIL_SERVER_ENABLE_SENDING` controls only the internal, unrestricted Python `send_email` function. That function is disabled by default and raises `PermissionError` unless the variable is true. It is **not published as an MCP tool**, and the variable does not grant or block the published restricted sending tool. Explicit unrestricted MCP sending is reserved for a later release. Provider OAuth consent is separate from the local allowlist; a provider may grant broader mail access than the published tools expose.

## OAuth accounts

Use **Mailboxes** in the UI to create a Google or Microsoft OAuth account. The UI writes a normal `[[emails]]` entry plus an `[emails.oauth]` section containing `provider`, `client_id`, `credential_id`, and (for Microsoft) `tenant`. `credential_id` is only a reference to the user token in the operating system keyring; copying `config.toml` alone does not transfer login. The customer-owned OAuth app settings are stored separately in `oauth-clients.json` beside the TOML file. Do not manually insert an access or refresh token into TOML.

## Environment variables

The `MCP_EMAIL_SERVER_*` names are kept for compatibility after the project rename. They take precedence over a file account with the same `account_name`; the UI marks that account as managed and does not write its environment password to TOML. An environment account is created only when the address, password, IMAP host, and SMTP host are all supplied.

| Variable | Purpose / default |
| --- | --- |
| `MCP_EMAIL_SERVER_CONFIG_PATH` | Explicit `config.toml` path; disables automatic migration. |
| `MCP_EMAIL_SERVER_ACCOUNT_NAME` | Environment account name; default `default`. |
| `MCP_EMAIL_SERVER_EMAIL_ADDRESS` | Required environment account address. |
| `MCP_EMAIL_SERVER_PASSWORD` | Required environment account password or app password. |
| `MCP_EMAIL_SERVER_IMAP_HOST`, `MCP_EMAIL_SERVER_SMTP_HOST` | Required environment server hostnames. |
| `MCP_EMAIL_SERVER_FULL_NAME` | Sender name; default is the part before `@`. |
| `MCP_EMAIL_SERVER_USER_NAME` | Shared login name; default is the email address. |
| `MCP_EMAIL_SERVER_IMAP_USER_NAME`, `MCP_EMAIL_SERVER_SMTP_USER_NAME` | Optional separate login names. |
| `MCP_EMAIL_SERVER_IMAP_PASSWORD`, `MCP_EMAIL_SERVER_SMTP_PASSWORD` | Optional separate passwords. |
| `MCP_EMAIL_SERVER_IMAP_PORT` | IMAP port; default `993`. |
| `MCP_EMAIL_SERVER_SMTP_PORT` | SMTP port; default `465`. |
| `MCP_EMAIL_SERVER_IMAP_SSL`, `MCP_EMAIL_SERVER_SMTP_SSL` | Direct TLS flags; default `true`. |
| `MCP_EMAIL_SERVER_SMTP_START_SSL` | SMTP STARTTLS flag; default `false`. |
| `MCP_EMAIL_SERVER_SAVE_TO_SENT` | Save sent mail in IMAP; default `true`. |
| `MCP_EMAIL_SERVER_SENT_FOLDER_NAME` | Optional Sent folder override. |
| `MCP_EMAIL_SERVER_ENABLE_ATTACHMENT_DOWNLOAD` | Overrides the file flag; default is `false` if absent. Keep it disabled for this release. |
| `MCP_EMAIL_SERVER_ENABLE_SENDING` | Enables only the internal unrestricted Python sender; default `false`. Does not control the published MCP sending tool. |
| `MCP_EMAIL_SERVER_GOOGLE_CLIENT_ID`, `MCP_EMAIL_SERVER_GOOGLE_CLIENT_SECRET` | Optional Google desktop OAuth app values. |
| `MCP_EMAIL_SERVER_MICROSOFT_CLIENT_ID`, `MCP_EMAIL_SERVER_MICROSOFT_TENANT` | Optional Microsoft OAuth app values. |

Boolean environment values accept `true`, `1`, `yes`, and `on` (case-insensitive); other values are false. Protect environment variables in client configuration and process supervision. See [user setup](user-setup.md) for path migration and reset, and the [administrator security overview](admin-security.md) for the trust boundary.
