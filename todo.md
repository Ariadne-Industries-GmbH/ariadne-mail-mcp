# Ariadne Mail MCP: capabilities and open work

## Current behavior

- The MCP server uses local `stdio`. The setup UI listens on `127.0.0.1`.
- Published MCP resource: `email://{account_name}` returns a masked account configuration.
- Published MCP tools: `list_available_accounts`, `add_email_account`, `get_allowed_recipients`, `send_email_to_allowed_recipients`, `list_emails_metadata`, `get_emails_content`, `download_attachment`, `list_folders`, `move_email`, `get_full_email_body`, and `mark_email`.
- `send_email_to_allowed_recipients` requires a configured account and recipient allowlist. Unrestricted `send_email` and `delete_emails` are internal functions, not published MCP tools. `MCP_EMAIL_SERVER_ENABLE_SENDING` gates only the internal sender.
- Attachment download is published but disabled by default. The current setting can enable it; keep it disabled for this release because the caller chooses the destination path.
- Classic IMAP/SMTP accounts and Google/Microsoft OAuth accounts stored as `EmailSettings` use the classic IMAP/SMTP handler. Legacy `ProviderSettings` entries have no handler.
- Tool-level tests cover folder listing, moving, body retrieval, and marking with mocked handlers. The binary smoke test checks the MCP handshake, tool list, reset, and UI. These checks do not establish compatibility with every mail provider or target workstation.

## Open work

- [ ] Make `get_full_email_body` genuinely return the full body. The shared parser currently truncates bodies after 20,000 characters; clarify the intended limit for `get_emails_content` separately and add focused tests.
- [ ] Test `email://{account_name}` through MCP resource registration and verify masking of sensitive fields.
- [ ] Add IMAP-level tests for `mark_email` flag addition/removal and `move_email` success and failure paths. The current MCP tool tests mock the handler.
- [ ] Define and document consistent tool error and result shapes, especially for IMAP/SMTP failures. `get_full_email_body` currently returns an empty string on fetch errors, making an error hard to distinguish from an empty message.
- [ ] Decide whether to remove or implement legacy `ProviderSettings` entries. They currently raise `NotImplementedError` when used for mail operations; Google/Microsoft OAuth accounts do not use this legacy type.
- [ ] Restrict attachment download destinations before recommending that the feature be enabled.
- [ ] Update and reassess the locked Gradio dependency; see `docs/admin-security.md` for the documented advisory and affected environment.
- [ ] Validate the release on the intended Windows and Linux workstations with real IMAP/SMTP and OAuth accounts, including keyring availability and Ariadne Engine registration.

## Later release decisions

- [ ] If unrestricted MCP sending is introduced, require a separate explicit approval and review its permissions and tests. The existing environment flag alone does not publish that tool.
