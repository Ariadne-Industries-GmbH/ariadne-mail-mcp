# How To Start The Server

## Install
- Quick run: `uvx mcp-email-server@latest ui`
- Or: `pip install mcp-email-server` then use `mcp-email-server`

## Configure An Account (UI)
- Run `mcp-email-server` with no arguments (or `mcp-email-server ui`) to open the UI.
- Enter IMAP/SMTP settings and Save.
- Config path controlled by `MCP_EMAIL_SERVER_CONFIG_PATH`.
  - Default: `./mcp_email_server/config.toml`
  - Recommended: `MCP_EMAIL_SERVER_CONFIG_PATH=~/.config/zerolib/mcp_email_server/config.toml`
- Reset config: `mcp-email-server reset`

## Configure Via Environment (optional)
- You can skip the UI by setting env vars (e.g., `MCP_EMAIL_SERVER_EMAIL_ADDRESS`, `MCP_EMAIL_SERVER_IMAP_HOST`, `MCP_EMAIL_SERVER_SMTP_HOST`, etc.).
- Environment variables override the TOML file. See README for the full list.

## Start The MCP Server
- Stdio: `mcp-email-server stdio`
- SSE: `mcp-email-server sse --host localhost --port 9557`
- The installed script and the packaged binary behave the same; running with no flags opens the UI by default.

## Email Sending Safety
- Sending is disabled by default. Enable explicitly if needed:
  - `export MCP_EMAIL_SERVER_ENABLE_SENDING=true` (also accepts `1/yes/on`)
- If disabled, the `send_email` tool raises a permission error.

## Notes
- Provider accounts (API-based) are not supported yet; use classic IMAP/SMTP accounts.
- For client integration (e.g., Claude Desktop), see README examples for MCP configuration.
