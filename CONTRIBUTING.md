# Contributing to Ariadne Mail MCP

Open an issue or pull request in this repository after it is published. Until then, share reproducible reports directly with the maintainer.

For a bug report, include your operating system, Python or binary version, the command used, and steps to reproduce. Remove passwords, OAuth codes, tokens, email bodies, and personal addresses from logs.

## Local development

Install [uv](https://docs.astral.sh/uv/) and Python 3.10 or later, then run:

```sh
uv sync --locked
uv run pytest -q
make check
uv run mkdocs build -s
```

Add focused tests for behavior changes and update the customer or administrator documentation when setup, permissions, or MCP tools change. Keep the original BSD 3-Clause notice in `LICENSE` and the origin record in `NOTICE`.
