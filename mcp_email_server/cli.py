import os
import sys

import typer

from mcp_email_server.app import mcp
from mcp_email_server.config import delete_settings
from mcp_email_server.paths import get_config_path, migrate_legacy_config

app = typer.Typer()


@app.command()
def stdio():
    migrate_legacy_config()
    mcp.run(transport="stdio")


@app.command()
def sse(
    host: str = "localhost",
    port: int = 9557,
):
    mcp.settings.host = host
    mcp.settings.port = port
    mcp.run(transport="sse")


@app.command()
def streamable_http(
    host: str = os.environ.get("MCP_HOST", "localhost"),
    port: int = os.environ.get("MCP_PORT", 9557),
):
    mcp.settings.host = host
    mcp.settings.port = port
    mcp.run(transport="streamable-http")


@app.command()
def ui(port: int = 8765, open_browser: bool = True):
    from mcp_email_server.ui import main as ui_main

    ui_main(port=port, open_browser=open_browser)


@app.command("config-path")
def config_path():
    """Print the configuration location without exposing credentials."""
    typer.echo(str(get_config_path()))


@app.command()
def reset(yes: bool = typer.Option(False, "--yes", help="Skip confirmation.")):
    if not yes:
        typer.confirm("Alle lokalen Kontoeinstellungen entfernen?", abort=True)
    delete_settings()
    typer.echo("✅ Config reset")


def main():
    # Wenn NUR das Script ausgeführt wird (ohne weitere Argumente)
    if len(sys.argv) == 1:
        from mcp_email_server.ui import main as ui_main

        ui_main()
    else:
        app()


if __name__ == "__main__":
    main()
