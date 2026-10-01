"""Local customer setup: accounts, provider guidance, permissions and integrations."""

import asyncio
import html
import os
import re
from contextlib import suppress
from pathlib import Path
from typing import Any

import gradio as gr

from mcp_email_server.config import EMAIL_ADDRESS_REGEX, AiSendsEmailToolSettings, EmailSettings, get_settings
from mcp_email_server.integrations import client_config, command_path, register_ariadne
from mcp_email_server.oauth import LoginError, PendingLogin, load_clients, remove_tokens, save_clients
from mcp_email_server.paths import get_config_path, migrate_legacy_config
from mcp_email_server.setup import (
    DEFAULTS,
    FIELDS,
    PLAIN,
    PROVIDERS,
    STARTTLS,
    TLS,
    SetupError,
    build_account,
    check_account,
    env_managed,
    load_form,
    save_account,
)

CSS = """
.gradio-container { max-width: 1080px !important; margin: auto; }
#intro { padding: 22px 0 12px; }
#intro h1 { letter-spacing: -.035em; font-size: 2.2rem; }
.account-summary { padding: 16px; border: 1px solid var(--border-color-primary); border-radius: 12px; }
footer { display: none !important; }
"""


def _parse_allowed_recipients_input(raw_text: str) -> list[str]:
    return [entry.strip() for entry in re.split(r"[,\n;]", raw_text or "") if entry.strip()]


def _message(error: Exception) -> str:
    if isinstance(error, (SetupError, LoginError)):
        return html.escape(str(error))
    if isinstance(error, OSError):
        return "Settings could not be saved. Check the location and write permissions."
    return "Check your input. Settings were not changed."


def _connection_report(results: list[tuple[str, bool, str]]) -> str:
    return "\n\n".join(
        f"{'✓' if success else '✗'} **{protocol}:** {html.escape(message)}" for protocol, success, message in results
    )


def create_ui() -> gr.Blocks:  # noqa: C901
    pending_logins: dict[str, PendingLogin] = {}
    with gr.Blocks(title="Ariadne Mail MCP", analytics_enabled=False) as app:
        gr.Markdown(
            "# Ariadne Mail MCP\nConnect your mailboxes, set permissions, and configure the local MCP server.",
            elem_id="intro",
        )
        summary = gr.Markdown("Loading accounts…", elem_classes="account-summary")
        original = gr.State(None)
        with gr.Tabs():
            with gr.Tab("Mailboxes"):
                with gr.Row():
                    selected = gr.Dropdown(label="Select mailbox", choices=[], interactive=True, scale=3)
                    new_button = gr.Button("+ Add mailbox", scale=1)
                    refresh_button = gr.Button("Refresh", scale=1)
                edit_button = gr.Button("Edit selected mailbox")
                with gr.Group():
                    form_title = gr.Markdown("### Add mailbox")
                    provider = gr.Radio(PROVIDERS, value="manual", label="How would you like to connect?")
                    with gr.Row():
                        address = gr.Textbox(label="Email address", placeholder="name@example.com")
                        full_name = gr.Textbox(label="Sender name", placeholder="First Last")
                    account_name = gr.Textbox(
                        label="Account name (optional)", placeholder="For example, Work; defaults to the email address"
                    )
                    with gr.Column(elem_id="manual-settings"):
                        password = gr.Textbox(
                            label="Password / app password",
                            type="password",
                            placeholder="Leave blank when editing to keep the saved password",
                        )
                        with gr.Row():
                            imap_host = gr.Textbox(label="Incoming server (IMAP)", placeholder="imap.example.com")
                            smtp_host = gr.Textbox(label="Outgoing server (SMTP)", placeholder="smtp.example.com")
                        with gr.Accordion("Advanced server settings", open=False):
                            user_name = gr.Textbox(label="Login name", placeholder="Defaults to email address")
                            with gr.Row():
                                imap_port = gr.Number(label="IMAP port", value=993, precision=0)
                                imap_security = gr.Dropdown([TLS, PLAIN], value=TLS, label="IMAP encryption")
                                smtp_port = gr.Number(label="SMTP port", value=465, precision=0)
                                smtp_security = gr.Dropdown([TLS, STARTTLS, PLAIN], value=TLS, label="SMTP encryption")
                            gr.Markdown(
                                "SMTP normally uses port 465 with SSL/TLS or 587 with STARTTLS. Unencrypted connections expose credentials in transit."
                            )
                            with gr.Row():
                                imap_user = gr.Textbox(label="Separate IMAP login name")
                                imap_password = gr.Textbox(label="Separate IMAP password", type="password")
                            with gr.Row():
                                smtp_user = gr.Textbox(label="Separate SMTP login name")
                                smtp_password = gr.Textbox(label="Separate SMTP password", type="password")
                            save_sent = gr.Checkbox(value=True, label="Also save sent email in an IMAP folder")
                            sent_folder = gr.Textbox(label="Sent folder", placeholder="Detect automatically")
                    with gr.Accordion("Connect Google / Microsoft with OAuth", open=False):
                        gr.Markdown(
                            "Select **Google / Gmail** or **Microsoft 365 / Outlook** above. "
                            "Server and password fields are not used for OAuth. "
                            "The steps below register your organization's own app for this device."
                        )
                        gr.Markdown(
                            Path(__file__).with_name("google-setup.md").read_text(encoding="utf-8")
                            + "\n\n---\n\n"
                            + Path(__file__).with_name("microsoft-setup.md").read_text(encoding="utf-8")
                        )
                        with gr.Accordion("App details for this device", open=True):
                            client_id = gr.Textbox(label="Client ID / application ID for the selected provider")
                            client_secret = gr.Textbox(
                                label="Google desktop client secret (Google only)", type="password"
                            )
                            tenant = gr.Textbox(label="Microsoft tenant (Microsoft only)", value="common")
                            with gr.Row():
                                app_load = gr.Button("Load saved app details")
                                app_save = gr.Button("Save app setup")
                            app_status = gr.Markdown("")
                        gr.Markdown("Tokens stay in the system keyring. On Linux, it must be configured and unlocked.")
                        with gr.Row():
                            login_button = gr.Button("Sign in with provider", variant="primary")
                            cancel_login = gr.Button("Cancel sign-in")
                        login_status = gr.Markdown("")
                    status = gr.Markdown("")
                    with gr.Row():
                        test_button = gr.Button("Test connection")
                        save_button = gr.Button("Save mailbox", variant="primary")
                    gr.Markdown("The connection test only signs in. It does not send email or change messages.")
                with gr.Accordion("Remove mailbox", open=False):
                    confirm_delete = gr.Checkbox(label="I want to remove the selected mailbox from this application.")
                    delete_button = gr.Button("Remove selected mailbox", variant="stop")
                    delete_status = gr.Markdown("")
                    gr.Markdown(
                        "Email at the provider remains unchanged. Any local sending permission for this account is removed."
                    )
            with gr.Tab("Permissions"):
                gr.Markdown(
                    "### Allow restricted sending\nThe AI can send only from the selected account to approved recipients. Sending stays disabled until an account and recipients are selected."
                )
                allowed_account = gr.Dropdown(label="Account for restricted sending", choices=[], interactive=True)
                recipients = gr.Textbox(label="Approved recipients", lines=4, placeholder="One address per line")
                download = gr.Checkbox(label="Allow downloading attachments to this computer", value=False)
                gr.Markdown(
                    "Reading, moving, and marking messages remain available. Unrestricted sending and deletion are not exposed as MCP tools."
                )
                with gr.Row():
                    permission_save = gr.Button("Save permissions", variant="primary")
                    permission_clear = gr.Button("Remove sending permission")
                permission_status = gr.Markdown("")
            with gr.Tab("Connect to Ariadne"):
                gr.Markdown(
                    "### Ariadne Engine MCP setup\nCopy this entry into Ariadne Engine's `mcp_servers.json` next to `model_config.json`. Keep existing `mcpServers` entries. Ariadne starts this program locally with `stdio` when needed."
                )
                executable = gr.Textbox(label="Program path", value=command_path())
                config_preview = gr.Code(
                    label="Copy Ariadne `mcp_servers.json` entry",
                    language="json",
                    value=client_config(command_path()),
                    interactive=False,
                )
                gr.Markdown(
                    "The output uses the Claude-compatible `mcpServers` format supported by Ariadne Engine and other MCP clients. If the Engine runs on another computer, install and configure this program there and use that computer's paths. [Ariadne Engine MCP documentation](https://github.com/Ariadne-Industries-GmbH/Ariadne-Engine/blob/main/README.md)."
                )
                with gr.Accordion("Register through the Ariadne Engine API (optional)", open=False):
                    gr.Markdown(
                        "Ariadne starts the program on the Engine computer. The program path and account configuration must be available there."
                    )
                    endpoint = gr.Textbox(label="Engine endpoint", placeholder="https://your-engine.example/…")
                    api_key = gr.Textbox(label="Engine API key", type="password")
                    spec_name = gr.Textbox(label="Name in Ariadne", value="ariadne-mail-mcp")
                    engine_command = gr.Textbox(label="Program path on the Engine computer", value=command_path())
                    tags = gr.Textbox(label="Tags (optional, comma-separated)")
                    description = gr.Textbox(label="Description (optional)")
                    register = gr.Button("Register / update in Ariadne")
                    engine_status = gr.Textbox(label="Result", interactive=False)
            with gr.Tab("Storage & help"):
                gr.Markdown(
                    "### Your configuration\nLocation: `" + str(get_config_path()) + "`\n\n"
                    "IMAP/SMTP passwords are stored in this local file. New files on Linux are accessible only to your user; on Windows, access depends on the selected folder's permissions. OAuth tokens are stored in the system keyring.\n\n"
                    "**Environment variables:** Managed settings take precedence. Managed accounts are marked and cannot be overwritten here.\n\n"
                    "**Connection issues:** Check the server, password, encryption, and provider permissions. Google and Microsoft setup guides appear when you select a provider.\n\n"
                    "**Linux keyring:** OAuth requires a Secret Service provider (such as GNOME Keyring or a configured KWallet), a user D-Bus session, and an unlocked keyring.\n\n"
                    "**Direct TOML editing:** See `docs/configuration.md` in the release archive for an example, every setting, and the sending permissions.\n\n"
                    "**Changes:** Running MCP processes load changed account settings on the next tool call. Restart the MCP in your AI client after changing its client configuration."
                )
        fields = [
            account_name,
            full_name,
            address,
            provider,
            user_name,
            password,
            imap_host,
            imap_port,
            imap_security,
            imap_user,
            imap_password,
            smtp_host,
            smtp_port,
            smtp_security,
            smtp_user,
            smtp_password,
            save_sent,
            sent_folder,
        ]

        def refresh() -> tuple[Any, ...]:
            settings = get_settings(reload=True)
            names = [e.account_name for e in settings.emails]
            managed = [name for name in names if env_managed(name)]
            text = (
                f"**{len(names)} mailbox(es) configured.**"
                if names
                else "**Welcome.** Connect your first mailbox to get started."
            )
            if managed:
                text += " Managed through environment variables: " + html.escape(", ".join(managed))
            return (
                text,
                gr.update(choices=names, value=None),
                gr.update(choices=names, value=settings.ai_sends_email_tool.allowed_account_name),
                "\n".join(settings.ai_sends_email_tool.allowed_recipients),
                gr.update(
                    value=settings.enable_attachment_download,
                    interactive=os.getenv("MCP_EMAIL_SERVER_ENABLE_ATTACHMENT_DOWNLOAD") is None,
                ),
            )

        refresh_outputs = [summary, selected, allowed_account, recipients, download]
        app.load(refresh, outputs=refresh_outputs, api_name=False)
        refresh_button.click(refresh, outputs=refresh_outputs, api_name=False)

        def edit(name: str | None) -> tuple[Any, ...]:
            if not name:
                return (None, "### Add mailbox", "", *DEFAULTS)
            return (
                name,
                "### Edit mailbox",
                "Leave password fields blank to keep stored passwords.",
                *load_form(name),
            )

        edit_button.click(edit, selected, [original, form_title, status, *fields], api_name=False)
        new_button.click(lambda: edit(None), outputs=[original, form_title, status, *fields], api_name=False)

        def save(original_name: str | None, *raw: Any) -> tuple[Any, ...]:
            try:
                account = build_account(dict(zip(FIELDS, raw, strict=True)), original_name)
                save_account(account, original_name)
                return "✓ Mailbox saved.", account.account_name, "", "", ""
            except Exception as error:
                return _message(error), original_name, gr.skip(), gr.skip(), gr.skip()

        save_button.click(
            save, [original, *fields], [status, original, password, imap_password, smtp_password], api_name=False
        ).then(refresh, outputs=refresh_outputs, api_name=False)

        async def test(original_name: str | None, *raw: Any) -> str:
            try:
                account = build_account(dict(zip(FIELDS, raw, strict=True)), original_name)
                return _connection_report(await check_account(account))
            except Exception as error:
                return _message(error)

        test_button.click(test, [original, *fields], status, api_name=False)

        def load_app(value: str) -> tuple[str, Any, Any, Any]:
            if value not in {"google", "microsoft"}:
                return "Select Google or Microsoft as the provider first.", gr.skip(), gr.skip(), gr.skip()
            client = load_clients()[value]
            if not client.get("client_id"):
                return "No app credentials are stored for this provider yet.", "", "", "common"
            return (
                "Stored app credentials loaded. The client secret is hidden for security.",
                client["client_id"],
                "",
                client.get("tenant", "common"),
            )

        app_load.click(
            load_app,
            provider,
            [app_status, client_id, client_secret, tenant],
            api_name=False,
        )

        def save_app(value: str, identifier: str, secret: str, directory: str) -> str:
            try:
                if value not in {"google", "microsoft"}:
                    return "Select Google or Microsoft as the provider first."
                clients = load_clients()
                google, microsoft = clients["google"], clients["microsoft"]
                if value == "google":
                    google = {"client_id": identifier, "client_secret": secret or google.get("client_secret", "")}
                elif value == "microsoft":
                    microsoft = {"client_id": identifier, "tenant": directory}
                if not identifier.strip():
                    return "Enter the client ID from the provider portal."
                save_clients(
                    google.get("client_id", ""),
                    google.get("client_secret", ""),
                    microsoft.get("client_id", ""),
                    microsoft.get("tenant", "common"),
                )
                return "✓ App credentials saved. You can now sign in with the provider."
            except Exception as error:
                return _message(error)

        app_save.click(save_app, [provider, client_id, client_secret, tenant], app_status, api_name=False)

        async def login(request: gr.Request, original_name: str | None, *raw: Any):
            session = request.session_hash
            pending = None
            account_auth = None
            try:
                values = dict(zip(FIELDS, raw, strict=True))
                if not EMAIL_ADDRESS_REGEX.fullmatch(values["email_address"].strip()):
                    yield "Enter the email address first.", gr.skip()
                    return
                if session in pending_logins:
                    pending_logins[session].cancel()
                pending = PendingLogin(values["provider"], values["email_address"].strip())
                pending_logins[session] = pending
                yield (
                    f"[Open provider sign-in]({pending.url})\n\nThe mailbox will be checked and saved after sign-in.",
                    gr.skip(),
                )
                while not pending.done.is_set():
                    await asyncio.sleep(0.5)
                account_auth = await asyncio.to_thread(pending.finish)
                account = build_account(values, original_name, account_auth)
                results = await check_account(account)
                if not all(success for _, success, _ in results):
                    yield (
                        _connection_report(results)
                        + "\n\nMailbox not saved. Check provider permissions and sign in again.",
                        gr.skip(),
                    )
                    return
                save_account(account, original_name)
                account_auth = None
                yield "✓ Sign-in and connection succeeded. Mailbox saved.", account.account_name
            except Exception as error:
                yield _message(error), gr.skip()
            finally:
                if pending:
                    pending.cancel()
                    if pending_logins.get(session) is pending:
                        pending_logins.pop(session, None)
                if account_auth:
                    with suppress(LoginError):
                        remove_tokens(account_auth.credential_id)

        login_button.click(
            login, [original, *fields], [login_status, original], api_name=False, concurrency_limit=4
        ).then(refresh, outputs=refresh_outputs, api_name=False)

        def cancel(request: gr.Request) -> str:
            pending = pending_logins.get(request.session_hash)
            if pending:
                pending.cancel()
            return "Sign-in cancelled."

        cancel_login.click(cancel, outputs=login_status, api_name=False, queue=False)

        def delete(name: str | None, confirmed: bool) -> tuple[str, bool]:
            if not name or not confirmed:
                return "Select a mailbox and confirm removal.", False
            try:
                if env_managed(name):
                    return "This account is managed through environment variables.", False
                settings = get_settings(reload=True)
                account = settings.get_account(name)
                if isinstance(account, EmailSettings) and account.oauth:
                    remove_tokens(account.oauth.credential_id)
                settings.delete_email(name)
                settings.store()
                return "Mailbox removed. Emails at the provider remain unchanged.", False
            except Exception as error:
                return _message(error), False

        delete_button.click(delete, [selected, confirm_delete], [delete_status, confirm_delete], api_name=False).then(
            refresh, outputs=refresh_outputs, api_name=False
        )

        def permissions(name: str | None, addresses: str, allow_download: bool) -> str:
            try:
                settings = get_settings(reload=True)
                if name and not isinstance(settings.get_account(name), EmailSettings):
                    return "Select an existing mailbox."
                allowed = _parse_allowed_recipients_input(addresses)
                if allowed and not name:
                    return "Select an account for the recipient permission."
                settings.ai_sends_email_tool = AiSendsEmailToolSettings(
                    allowed_account_name=name, allowed_recipients=allowed
                )
                settings.enable_attachment_download = allow_download
                settings.store()
                return "✓ Permissions saved."
            except Exception as error:
                return _message(error)

        permission_save.click(
            permissions, [allowed_account, recipients, download], permission_status, api_name=False
        ).then(refresh, outputs=refresh_outputs, api_name=False)
        permission_clear.click(
            lambda value: permissions(None, "", value), download, permission_status, api_name=False
        ).then(refresh, outputs=refresh_outputs, api_name=False)
        executable.change(client_config, executable, config_preview, api_name=False)
        register.click(
            register_ariadne,
            [api_key, endpoint, spec_name, engine_command, tags, description],
            engine_status,
            api_name=False,
        )
    return app


def main(port: int = 8765, open_browser: bool = True) -> None:
    migrate_legacy_config()
    app = create_ui()
    app.launch(
        server_name="127.0.0.1",
        server_port=port,
        inbrowser=open_browser,
        share=False,
        show_error=False,
        footer_links=[],
        css=CSS,
        theme=gr.themes.Soft(primary_hue="teal", neutral_hue="slate"),
    )


if __name__ == "__main__":
    main()
