import sys

import typer

from mcp_email_server.app import mcp
from mcp_email_server.config import delete_settings
from mcp_email_server.oauth import LoginError
from mcp_email_server.paths import get_config_path, migrate_legacy_config

app = typer.Typer()


@app.command()
def stdio():
    migrate_legacy_config()
    mcp.run(transport="stdio")


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
        typer.confirm(
            "Remove local account settings, OAuth app data, stored tokens, and known legacy copies?", abort=True
        )
    try:
        removed = delete_settings()
    except (LoginError, OSError, ValueError) as error:
        typer.echo(f"Reset failed: {error}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo("Local account settings and stored OAuth credentials removed.")
    if removed:
        typer.echo("Removed files from these config locations:")
        for path in removed:
            typer.echo(f"- {path}")


def main():
    # Open the setup UI when the script is launched without arguments.
    if len(sys.argv) == 1:
        from mcp_email_server.ui import main as ui_main

        ui_main()
    else:
        app()


if __name__ == "__main__":
    main()
