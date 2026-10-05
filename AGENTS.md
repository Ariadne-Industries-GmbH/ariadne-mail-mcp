# Repository Guidelines

## Project Structure & Module Organization

- Source: `mcp_email_server/` (CLI `cli.py`, MCP tools `app.py`, config `config.py`, email handlers under `emails/`).
- Entry points: `ariadne-mail-mcp` (installed script), `main.py` for binary builds.
- Tests: `tests/`; Docs: `docs/`; Build artifacts: `dist/`, `build/`.
- Config file: frozen binaries use `mcp_email_server/config.toml` beside the executable; Python installs use the user
  config directory. `MCP_EMAIL_SERVER_CONFIG_PATH` and account env vars take precedence.

## Build, Test, and Development Commands

- `make install` — create venv with `uv` and install pre-commit.
- `make check` — run Ruff lint/format, dependency checks.
- `make test` — run pytest with coverage (writes `coverage.xml`).
- `make build` — build wheels; `make docs`, `make docs-test`.
- Run locally: `uv run ariadne-mail-mcp ui` (loopback UI), `uv run ariadne-mail-mcp stdio` (MCP).
- Matrix: `tox`.

## Coding Style & Naming Conventions

- Python 3.10+; 4 spaces; max line length 120.
- Type hints required; prefer Pydantic models where applicable.
- Naming: modules/functions `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE_CASE`.
- Lint/format via Ruff: `pre-commit run -a` or `make check`. Prettier formats JSON/YAML. See `.editorconfig`.

## Testing Guidelines

- Use pytest with `pytest-asyncio` (asyncio_mode=auto).
- Place tests in `tests/` using `test_*.py`.
- Add focused unit tests; mock network/IMAP/SMTP like existing tests.
- Aim to keep or improve coverage; run `make test` locally.

## Commit & Pull Request Guidelines

- Commits: short, imperative (optionally scoped), e.g., `fix: handle Unicode in SMTP`, `feat: add folder listing (#123)`.
- PRs: clear description, linked issues, tests for changes, and docs updates when CLI or tools change. Include screenshots for UI updates.

## Security & Configuration Tips

- Do not commit secrets. Use `MCP_EMAIL_SERVER_*` env vars.
- Avoid logging credentials; verify masks in outputs.
- Changes to MCP tools or config schema require updating tests in `tests/test_mcp_tools.py` and docs.
