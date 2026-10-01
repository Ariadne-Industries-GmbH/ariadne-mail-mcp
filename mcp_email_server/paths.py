"""Configuration paths shared by the setup UI, MCP process and frozen binary."""

import json
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


def get_migration_record_path() -> Path:
    """Store the source of a copied config so reset can find it later."""
    return get_config_path().with_name(".migration-source.json")


def legacy_config_candidates() -> list[Path]:
    """Locations imported by older versions or by the current migration."""
    return [
        get_profile_config_path(),
        Path.cwd() / "mcp_email_server" / "config.toml",
        Path.home() / ".config" / "zerolib" / "mcp_email_server" / "config.toml",
    ]


def recorded_migration_source() -> Path | None:
    """Read a recorded source only if it has the expected legacy config shape."""
    record = get_migration_record_path()
    if not record.exists():
        return None
    try:
        source = json.loads(record.read_text(encoding="utf-8"))["source"]
        path = Path(source)
        if path.is_absolute() and path.name == "config.toml" and path.parent.name == "mcp_email_server":
            return path
    except (ValueError, TypeError, KeyError):
        raise ValueError(f"Invalid migration record: {record}") from None
    raise ValueError(f"Invalid migration record: {record}")


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
    for source in legacy_config_candidates():
        if source.is_file() and source.resolve() != target:
            clients_source = source.with_name("oauth-clients.json")
            clients_target = target.with_name("oauth-clients.json")
            if clients_source.is_file() and not clients_target.exists():
                atomic_private_write(clients_target, clients_source.read_text(encoding="utf-8"))
            atomic_private_write(get_migration_record_path(), json.dumps({"source": str(source.absolute())}))
            atomic_private_write(target, source.read_text(encoding="utf-8"))
            return source
    return None
