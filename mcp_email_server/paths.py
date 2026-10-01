"""Configuration paths shared by the setup UI, MCP process and frozen binary."""

import os
import sys
import tempfile
from pathlib import Path


def get_profile_config_path() -> Path:
    """Return the user-profile path used by non-frozen installs and older binaries."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return (base / "zerolib" / "mcp_email_server" / "config.toml").resolve()


def get_config_path() -> Path:
    override = os.environ.get("MCP_EMAIL_SERVER_CONFIG_PATH")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return (Path(sys.executable).resolve().parent / "mcp_email_server" / "config.toml").resolve()
    return get_profile_config_path()


def get_migration_marker_path() -> Path:
    """Mark an intentional reset so legacy settings are not imported again."""
    return get_config_path().with_name(".migration-disabled")


def atomic_private_write(path: Path, content: str) -> None:
    """Replace only a complete file; temporary and final files are owner-only on POSIX."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".email-", dir=path.parent)
    try:
        if os.name == "posix":
            os.chmod(temporary, 0o600)
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
    if os.environ.get("MCP_EMAIL_SERVER_CONFIG_PATH") or target.exists() or get_migration_marker_path().exists():
        return None
    candidates = [get_profile_config_path(), Path.cwd() / "mcp_email_server" / "config.toml"]
    candidates.append(Path.home() / ".config" / "zerolib" / "mcp_email_server" / "config.toml")
    for source in candidates:
        if source.is_file() and source.resolve() != target:
            clients_source = source.with_name("oauth-clients.json")
            clients_target = target.with_name("oauth-clients.json")
            if clients_source.is_file() and not clients_target.exists():
                atomic_private_write(clients_target, clients_source.read_text(encoding="utf-8"))
            atomic_private_write(target, source.read_text(encoding="utf-8"))
            return source
    return None
