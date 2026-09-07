"""Portable MCP configuration export and the existing Ariadne registration."""

import json
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from mcp_email_server.paths import get_config_path
from mcp_email_server.tools.installer import get_endpoint_path


def command_path() -> str:
    return sys.executable if getattr(sys, "frozen", False) else get_endpoint_path()


def client_config(command: str) -> str:
    return json.dumps(
        {
            "mcpServers": {
                "email": {
                    "command": command.strip() or command_path(),
                    "args": ["stdio"],
                    "env": {"MCP_EMAIL_SERVER_CONFIG_PATH": str(get_config_path())},
                }
            }
        },
        ensure_ascii=False,
        indent=2,
    )


def register_ariadne(api_key: str, endpoint: str, name: str, command: str, tags: str, description: str) -> str:
    endpoint, name, command = endpoint.strip(), name.strip(), command.strip()
    parsed = urlsplit(endpoint)
    if not parsed.hostname or (
        parsed.scheme != "https"
        and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"})
    ):
        return "Bitte eine HTTPS-Adresse der Ariadne Engine eingeben (HTTP nur lokal)."
    if not api_key.strip() or not name or not command:
        return "API-Schlüssel, Name und Programmpfad sind erforderlich."
    dto = {
        "key": "",
        "name": name,
        "description": description.strip(),
        "transport": "stdio",
        "command": [command, "stdio"],
        "url": None,
        "bearer_token": None,
        "env": {"MCP_EMAIL_SERVER_CONFIG_PATH": str(get_config_path())},
        "tags": [tag.strip() for tag in tags.split(",") if tag.strip()] or None,
        "is_standard": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with httpx.Client(timeout=15, headers={"Authorization": f"Bearer {api_key.strip()}"}) as client:
            response = client.post(
                endpoint,
                json={
                    "thread_name": "get-mcp-server-spec-by-name",
                    "payload": {
                        "path_params": {"name": name},
                        "query_params": None,
                        "body_params_serialized": None,
                    },
                },
            )
            if response.status_code == 404:
                existing = None
            elif response.is_success:
                existing = response.json()
                if isinstance(existing, dict) and "data" in existing:
                    existing = existing["data"]
            else:
                return f"Engine-Abfrage fehlgeschlagen (HTTP {response.status_code}). URL und Berechtigung prüfen."
            key = existing.get("key") if isinstance(existing, dict) else None
            if existing is not None and not key:
                return "Die Engine hat keinen gültigen Schlüssel für den bestehenden Eintrag geliefert."
            dto["key"] = key or ""
            response = client.post(
                endpoint,
                json={
                    "thread_name": "update-mcp-server-spec" if key else "create-mcp-server-spec",
                    "payload": {
                        "path_params": {"key": key} if key else None,
                        "query_params": None,
                        "body_params_serialized": json.dumps(dto),
                    },
                },
            )
            if not response.is_success:
                return f"Registrierung fehlgeschlagen (HTTP {response.status_code}). Berechtigungen prüfen."
            return "MCP-Eintrag in Ariadne aktualisiert." if key else "MCP-Eintrag in Ariadne angelegt."
    except (httpx.HTTPError, ValueError):
        return "Die Engine ist nicht erreichbar oder liefert eine ungültige Antwort."
