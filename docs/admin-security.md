# Administrator security overview

This page describes the current local deployment so an administrator can decide whether it fits their workstation and mail policies. Review the source and lockfile for the exact release being delivered.

## Trust boundary and network access

| Component | Access and controls |
| --- | --- |
| MCP server | Started by the AI client as a child process using local `stdio`. The CLI does not expose SSE or HTTP transports. The AI client and its users can invoke the published tools. There is no separate MCP authentication layer. |
| Setup UI | Binds to `127.0.0.1` only, with sharing disabled. It has no login. Any local process or user that can reach the loopback port may interact with it. Close the UI after setup. |
| OAuth callback | Temporary HTTP listener on `127.0.0.1` with a random free port during sign-in. The flow checks OAuth state and uses PKCE. |
| Outbound connections | IMAP/SMTP servers configured for each account, Google or Microsoft OAuth endpoints when applicable, and an optional Ariadne Engine registration endpoint if the user invokes that UI action. No inbound LAN listener is required. |

Treat the workstation user account, the AI client, and its access to MCP tools as trusted. A compromised client can read mail through the available tools and may change mailbox state or configuration. The `add_email_account` tool can add an account, so administrators should review the complete published tool list before giving the client access. Do not register the server for untrusted client users.

## Data, credentials, and permissions

| Data | Location / behavior |
| --- | --- |
| Classic IMAP/SMTP passwords | Plaintext in the local `config.toml`. New files use mode `0600` on Linux. Protect the containing folder and backups; on Windows, verify its ACL. |
| OAuth app client data | `oauth-clients.json` beside `config.toml`. A Google desktop client secret may be present here. |
| OAuth user tokens | System keyring only; no plaintext fallback. The keyring must be available to the same operating system user that runs the MCP process. |
| Environment settings | `MCP_EMAIL_SERVER_*` account values override file values. Managed account passwords are not copied into TOML when the UI saves other settings. Protect the client or process configuration that holds them. |
| Mail content | Returned to the AI client over local stdio. The client's storage, logs, model routing, and retention policies then apply. |

The native binary keeps `mcp_email_server/config.toml` in a folder beside the executable. An installed Python command uses the user profile config directory. `MCP_EMAIL_SERVER_CONFIG_PATH` sets an explicit path. `config-path` prints the active path. On first start, the native binary may copy an old profile config and OAuth app data into its local folder while leaving the source intact. Review both locations during migration. `reset` removes known local/profile copies and stored OAuth tokens it can identify, then prevents an old working-directory copy from being imported again. Backups, environment variables, client registrations, and provider consent must be handled separately.

The restricted sending tool requires a configured sending account and recipient allowlist. Unrestricted send and delete functions are not published as MCP tools. The internal unrestricted Python sender has a separate `MCP_EMAIL_SERVER_ENABLE_SENDING` gate, defaulting to off; it does not control the published tool. Read, move, mark, and account-creation tools are published. Attachment download is disabled by default, but the current implementation can be enabled by local UI, file setting, or `MCP_EMAIL_SERVER_ENABLE_ATTACHMENT_DOWNLOAD`; when enabled, the MCP caller supplies a destination path. Keep it disabled for this release. Path restrictions are planned for a later update.

IMAP and SMTP support TLS/STARTTLS as well as unencrypted modes. Require encrypted connections in the account settings and at the mail provider if your policy mandates transport encryption.

## OAuth grants

Google IMAP/SMTP uses the `https://mail.google.com/` scope. Google describes this as broad access to read, compose, send, and permanently delete mail; the application's exposed MCP tools are narrower. Evaluate the provider grant itself, because a stolen token or changed application code could use the broader provider permission. See [Google's scope reference](https://developers.google.com/workspace/gmail/api/auth/scopes) and [IMAP/SMTP OAuth guide](https://developers.google.com/workspace/gmail/imap/xoauth2-protocol).

Microsoft requests delegated `IMAP.AccessAsUser.All`, `SMTP.Send`, and `offline_access`. Mailbox and tenant policies can further restrict access. See [Microsoft's IMAP/SMTP OAuth guide](https://learn.microsoft.com/en-us/exchange/client-developer/legacy-protocols/how-to-authenticate-an-imap-pop-smtp-application-by-using-oauth).

Each customer uses their own OAuth app. Review consent, test-user and verification requirements, tenant restrictions, and revocation procedures in the provider console.

## Dependency status for this release

The current lockfile resolves Gradio 6.0.1. [GHSA-39mp-8hj3-5c49](https://github.com/gradio-app/gradio/security/advisories/GHSA-39mp-8hj3-5c49) reports a Gradio issue affecting versions below 6.7 on Windows with Python 3.13 or later. The supplied frozen binaries are built with Python 3.12; Python installations on the affected Windows/Python combination need separate assessment. Dependency remediation is deferred to a later update. This is a documented known issue, not a comprehensive vulnerability audit. Administrators should check the exact lockfile and advisories again before deployment.

## Deployment review

1. Run the released binary on the target Windows or Linux version and verify `config-path`, the setup UI, and the client's stdio connection.
2. Restrict the executable, config directory, backups, and AI client to the intended workstation user. Check Windows ACLs or Linux permissions and keyring availability.
3. Approve the mail provider, outbound endpoints, OAuth scopes, and SMTP AUTH/IMAP policy. Keep attachment download disabled.
4. Review the tool list and the AI client's access to mail content. Configure restricted sending recipients only when required.
5. Preserve the included `LICENSE` and `NOTICE` with redistributed source or binary packages.
