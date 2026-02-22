# mcp-email-server

[![Release](https://img.shields.io/github/v/release/ai-zerolab/mcp-email-server)](https://img.shields.io/github/v/release/ai-zerolab/mcp-email-server)
[![Build status](https://img.shields.io/github/actions/workflow/status/ai-zerolab/mcp-email-server/main.yml?branch=main)](https://github.com/ai-zerolab/mcp-email-server/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/ai-zerolab/mcp-email-server/branch/main/graph/badge.svg)](https://codecov.io/gh/ai-zerolab/mcp-email-server)
[![Commit activity](https://img.shields.io/github/commit-activity/m/ai-zerolab/mcp-email-server)](https://img.shields.io/github/commit-activity/m/ai-zerolab/mcp-email-server)
[![License](https://img.shields.io/github/license/ai-zerolab/mcp-email-server)](https://img.shields.io/github/license/ai-zerolab/mcp-email-server)
[![smithery badge](https://smithery.ai/badge/@ai-zerolab/mcp-email-server)](https://smithery.ai/server/@ai-zerolab/mcp-email-server)

IMAP and SMTP via MCP Server

- **Github repository**: <https://github.com/ai-zerolab/mcp-email-server/>
- **Documentation** <https://ai-zerolab.github.io/mcp-email-server/>

## Installation

### Manual Installation

We recommend using [uv](https://github.com/astral-sh/uv) to manage your environment.

Try `uvx mcp-email-server@latest ui` to config, and use following configuration for mcp client:

```json
{
  "mcpServers": {
    "zerolib-email": {
      "command": "uvx",
      "args": ["mcp-email-server@latest", "stdio"]
    }
  }
}
```

This package is available on PyPI, so you can install it using `pip install mcp-email-server`

After that, configure your email server using the ui: `mcp-email-server ui`

### Environment Variable Configuration

You can also configure the email server using environment variables, which is particularly useful for CI/CD environments like Jenkins. zerolib-email supports both UI configuration (via TOML file) and environment variables, with environment variables taking precedence.

```json
{
  "mcpServers": {
    "zerolib-email": {
      "command": "uvx",
      "args": ["mcp-email-server@latest", "stdio"],
      "env": {
        "MCP_EMAIL_SERVER_ACCOUNT_NAME": "work",
        "MCP_EMAIL_SERVER_FULL_NAME": "John Doe",
        "MCP_EMAIL_SERVER_EMAIL_ADDRESS": "john@example.com",
        "MCP_EMAIL_SERVER_USER_NAME": "john@example.com",
        "MCP_EMAIL_SERVER_PASSWORD": "your_password",
        "MCP_EMAIL_SERVER_IMAP_HOST": "imap.gmail.com",
        "MCP_EMAIL_SERVER_IMAP_PORT": "993",
        "MCP_EMAIL_SERVER_SMTP_HOST": "smtp.gmail.com",
        "MCP_EMAIL_SERVER_SMTP_PORT": "465"
      }
    }
  }
}
```

#### Available Environment Variables

| Variable                                      | Description                                      | Default       | Required |
| --------------------------------------------- | ------------------------------------------------ | ------------- | -------- |
| `MCP_EMAIL_SERVER_ACCOUNT_NAME`               | Account identifier                               | `"default"`   | No       |
| `MCP_EMAIL_SERVER_FULL_NAME`                  | Display name                                     | Email prefix  | No       |
| `MCP_EMAIL_SERVER_EMAIL_ADDRESS`              | Email address                                    | -             | Yes      |
| `MCP_EMAIL_SERVER_USER_NAME`                  | Login username                                   | Same as email | No       |
| `MCP_EMAIL_SERVER_PASSWORD`                   | Email password                                   | -             | Yes      |
| `MCP_EMAIL_SERVER_IMAP_HOST`                  | IMAP server host                                 | -             | Yes      |
| `MCP_EMAIL_SERVER_IMAP_PORT`                  | IMAP server port                                 | `993`         | No       |
| `MCP_EMAIL_SERVER_IMAP_SSL`                   | Enable IMAP SSL                                  | `true`        | No       |
| `MCP_EMAIL_SERVER_SMTP_HOST`                  | SMTP server host                                 | -             | Yes      |
| `MCP_EMAIL_SERVER_SMTP_PORT`                  | SMTP server port                                 | `465`         | No       |
| `MCP_EMAIL_SERVER_SMTP_SSL`                   | Enable SMTP SSL                                  | `true`        | No       |
| `MCP_EMAIL_SERVER_SMTP_START_SSL`             | Enable STARTTLS                                  | `false`       | No       |
| `MCP_EMAIL_SERVER_ENABLE_ATTACHMENT_DOWNLOAD` | Enable attachment download                       | `false`       | No       |
| `MCP_EMAIL_SERVER_SAVE_TO_SENT`               | Save sent emails to IMAP Sent folder             | `true`        | No       |
| `MCP_EMAIL_SERVER_SENT_FOLDER_NAME`           | Custom Sent folder name (auto-detect if not set) | -             | No       |

### Enabling Attachment Downloads

By default, downloading email attachments is disabled for security reasons. To enable this feature, you can either:

**Option 1: Environment Variable**

```json
{
  "mcpServers": {
    "zerolib-email": {
      "command": "uvx",
      "args": ["mcp-email-server@latest", "stdio"],
      "env": {
        "MCP_EMAIL_SERVER_ENABLE_ATTACHMENT_DOWNLOAD": "true"
      }
    }
  }
}
```

**Option 2: TOML Configuration**

Add `enable_attachment_download = true` to your TOML configuration file (`~/.config/zerolib/mcp_email_server/config.toml`):

```toml
enable_attachment_download = true

[[emails]]
# ... your email configuration
```

Once enabled, you can use the `download_attachment` tool to save email attachments to a specified path.

### Saving Sent Emails to IMAP Sent Folder

By default, sent emails are automatically saved to your IMAP Sent folder. This ensures that emails sent via the MCP server appear in your email client (Thunderbird, webmail, etc.).

The server auto-detects common Sent folder names: `Sent`, `INBOX.Sent`, `Sent Items`, `Sent Mail`, `[Gmail]/Sent Mail`.

**To specify a custom Sent folder name** (useful for providers with non-standard folder names):

**Option 1: Environment Variable**

```json
{
  "mcpServers": {
    "zerolib-email": {
      "command": "uvx",
      "args": ["mcp-email-server@latest", "stdio"],
      "env": {
        "MCP_EMAIL_SERVER_SENT_FOLDER_NAME": "INBOX.Sent"
      }
    }
  }
}
```

**Option 2: TOML Configuration**

```toml
[[emails]]
account_name = "work"
save_to_sent = true
sent_folder_name = "INBOX.Sent"
# ... rest of your email configuration
```

**To disable saving to Sent folder**, set `MCP_EMAIL_SERVER_SAVE_TO_SENT=false` or `save_to_sent = false` in your TOML config.

For separate IMAP/SMTP credentials, you can also use:

- `MCP_EMAIL_SERVER_IMAP_USER_NAME` / `MCP_EMAIL_SERVER_IMAP_PASSWORD`
- `MCP_EMAIL_SERVER_SMTP_USER_NAME` / `MCP_EMAIL_SERVER_SMTP_PASSWORD`

Then you can try it in [Claude Desktop](https://claude.ai/download). If you want to intergrate it with other mcp client, run `$which mcp-email-server` for the path and configure it in your client like:

```json
{
  "mcpServers": {
    "zerolib-email": {
      "command": "{{ ENTRYPOINT }}",
      "args": ["stdio"]
    }
  }
}
```

If `docker` is avaliable, you can try use docker image, but you may need to config it in your client using `tools` via `MCP`. The default config path is `~/.config/zerolib/mcp_email_server/config.toml`

```json
{
  "mcpServers": {
    "zerolib-email": {
      "command": "docker",
      "args": ["run", "-it", "ghcr.io/ai-zerolab/mcp-email-server:latest"]
    }
  }
}
```

### Installing via Smithery

To install Email Server for Claude Desktop automatically via [Smithery](https://smithery.ai/server/@ai-zerolab/mcp-email-server):

```bash
npx -y @smithery/cli install @ai-zerolab/mcp-email-server --client claude
```

## MCP Tools

The server exposes MCP resources/tools for email workflows.

- Resource `email://{account_name}`
  - Returns masked account configuration for the given account.

- Tool `list_available_accounts()` → list of accounts
  - Returns masked attributes for configured email/provider accounts.

- Tool `add_email_account(email: EmailSettings)` → string
  - Adds an account and persists to TOML. Returns a success message.

- Tool `page_email(account_name, page=1, page_size=10, before?, since?, subject?, body?, text?, from_address?, to_address?, order=\"desc\")` → EmailPageResponse
  - Paginates INBOX with filters. Response: `{ page, page_size, before, since, subject, body, text, total, emails[] }` where `emails[]` are previews (truncated bodies).

- Tool `send_email(account_name, recipients, subject, body, cc?, bcc?)` → string
  - Sends an email (UTF‑8 safe subject/sender). Returns: `"Email sent successfully to <first-recipient>"`.
  - Controlled by env: disabled by default. Set `MCP_EMAIL_SERVER_ENABLE_SENDING=true` (or `1/yes/on`) to enable. When disabled, the tool raises a permission error.

- Tool `list_folders(account_name)` → list[str]
  - Lists IMAP folders.

- Tool `move_email(account_name, message_id, source_folder, destination_folder)` → bool
  - Copies to destination, flags deleted in source, expunges.

- Tool `delete_email(account_name, message_id, folder=\"INBOX\")` → bool
  - Flags deleted and expunges.

- Tool `get_full_email_body(account_name, message_id, folder=\"INBOX\")` → str
  - Fetches RFC822 and returns the parsed full body string.

- Tool `mark_email(account_name, message_id, folder=\"INBOX\", mark)` → bool
  - Marks message using IMAP flags. `mark` in `{ "read", "unread", "flagged", "unflagged", "answered", "draft" }`.

### Provider Accounts (Not Supported Yet)

The config schema includes `ProviderSettings` for future API-based providers (e.g., Gmail/Outlook). These are currently not supported by this server — attempting to use a provider account results in a clear error. For provider-backed workflows, use another MCP server that implements provider handlers.

Example invocation (arguments shape) for `page_email`:

```json
{
  "account_name": "work",
  "page": 1,
  "page_size": 10,
  "since": "2024-01-01T00:00:00Z",
  "subject": "invoice",
  "order": "desc"
}
```

## Usage

### Replying to Emails

To reply to an email with proper threading (so it appears in the same conversation in email clients):

1. First, fetch the original email to get its `message_id`:

```python
emails = await get_emails_content(account_name="work", email_ids=["123"])
original = emails.emails[0]
```

2. Send your reply using `in_reply_to` and `references`:

```python
await send_email(
    account_name="work",
    recipients=[original.sender],
    subject=f"Re: {original.subject}",
    body="Thank you for your email...",
    in_reply_to=original.message_id,
    references=original.message_id,
)
```

The `in_reply_to` parameter sets the `In-Reply-To` header, and `references` sets the `References` header. Both are used by email clients to thread conversations properly.

## Development

This project is managed using [uv](https://github.com/ai-zerolab/uv).

Try `make install` to install the virtual environment and install the pre-commit hooks.

Use `uv run mcp-email-server` for local development.

## Releasing a new version

- Create an API Token on [PyPI](https://pypi.org/).
- Add the API Token to your projects secrets with the name `PYPI_TOKEN` by visiting [this page](https://github.com/ai-zerolab/mcp-email-server/settings/secrets/actions/new).
- Create a [new release](https://github.com/ai-zerolab/mcp-email-server/releases/new) on Github.
- Create a new tag in the form `*.*.*`.

For more details, see [here](https://fpgmaas.github.io/cookiecutter-uv/features/cicd/#how-to-trigger-a-release).

## Build Binary

```bash
pyi-makespec --onefile --name mcp_email_server_bin main.py --collect-data gradio --collect-data gradio_client --collect-data safehttpx --hidden-import anyio --hidden-import starlette.routing
```

Adapt mcp_email_server.spec file:

```
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = ['anyio', 'starlette.routing']

# Datenfiles der Pakete einsammeln
datas += collect_data_files('gradio')
datas += collect_data_files('gradio_client')
datas += collect_data_files('safehttpx')

# numpy komplett (Tuple: (datas, binaries, hiddenimports))
d, b, h = collect_all('numpy')
datas += d; binaries += b; hiddenimports += h

# groovy komplett – wichtig wegen version.txt & Co.
d, b, h = collect_all('groovy')
datas += d; binaries += b; hiddenimports += h

# Gradio-Submodule sicherheitshalber explizit
hiddenimports += collect_submodules('gradio')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['rthook_no_pyi.py'],   # Runtime-Hook aktivieren
    excludes=[],
    noarchive=False,
    optimize=0,
    # WICHTIG: Gradio/Groovy als .py sammeln (nicht nur .pyc in der Zipsammlung)
    module_collection_mode={
        "gradio": "py",
        "groovy": "py",
    },
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='mcp_email_server_bin',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

```

Run PyInstaller (recommended after recreating `.venv`):
```bash
uv sync --group dev
.venv/bin/python -m PyInstaller --clean mcp_email_server.spec
```

The executable will be written to:

```bash
dist/mcp_email_server_bin
```

Alternative (if your virtualenv entrypoint scripts are valid):

```bash
.venv/bin/pyinstaller --clean mcp_email_server.spec
```

### Use the CLI (but this currently not works properly)

```bash
pyinstaller --onefile --name mcp_email_server_bin main.py --collect-data gradio --collect-data gradio_client --collect-data safehttpx --hidden-import anyio --hidden-import starlette.routing --collect-data numpy --hidden-import numpy
```

```bash
python -m nuitka --standalone --onefile main.py
```
