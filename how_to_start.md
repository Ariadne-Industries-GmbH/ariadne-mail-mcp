# Start Ariadne Mail MCP

For user setup, use the [full guide](docs/user-setup.md).

## Native binary

Extract the release archive and start `ariadne-mail-mcp.exe` on Windows or `./ariadne-mail-mcp` on Linux. The setup UI opens on `127.0.0.1`. Configure a mailbox, then copy the local MCP entry from **Connect to Ariadne** into Ariadne Engine's `mcp_servers.json`. See the [configuration reference](docs/configuration.md) for direct TOML setup.

## Python development install

```sh
uv sync --locked
uv run ariadne-mail-mcp ui
uv run ariadne-mail-mcp stdio
```

Running without arguments opens the setup UI. Only stdio is available for MCP. Run `ariadne-mail-mcp config-path` to inspect the active settings path and `ariadne-mail-mcp reset` to remove local account settings and stored OAuth tokens.
