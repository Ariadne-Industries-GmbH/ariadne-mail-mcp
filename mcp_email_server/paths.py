"""Stable per-user paths shared by the setup UI, MCP process and frozen binary."""

import os
import sys
import tempfile
from pathlib import Path


def get_config_path() -> Path:
    override = os.environ.get("MCP_EMAIL_SERVER_CONFIG_PATH")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return (base / "zerolib" / "mcp_email_server" / "config.toml").resolve()


def atomic_private_write(path: Path, content: str) -> None:
    """Replace only a complete file; temporary and final files are owner-only on POSIX."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".email-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def migrate_legacy_config() -> Path | None:
    """Copy a legacy config once. Never overwrite a destination or remove the source."""
    target = get_config_path()
    if os.environ.get("MCP_EMAIL_SERVER_CONFIG_PATH") or target.exists():
        return None
    candidates = [Path.cwd() / "mcp_email_server" / "config.toml"]
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent / "mcp_email_server" / "config.toml")
    candidates.append(Path.home() / ".config" / "zerolib" / "mcp_email_server" / "config.toml")
    for source in candidates:
        if source.is_file() and source.resolve() != target:
            atomic_private_write(target, source.read_text(encoding="utf-8"))
            return source
    return None
