import json
import logging
import re
from datetime import datetime
from urllib.parse import urlparse

import gradio as gr
import httpx

from mcp_email_server.config import (
    DEFAULT_CONFIG_PATH,
    AiSendsEmailToolSettings,
    EmailSettings,
    get_settings,
    store_settings,
)

logger = logging.getLogger(__name__)
ALLOWED_RECIPIENT_SPLIT_REGEX = re.compile(r"[,\n;]")


def _is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def _parse_allowed_recipients_input(raw_text: str) -> list[str]:
    entries = ALLOWED_RECIPIENT_SPLIT_REGEX.split(raw_text or "")
    return [entry.strip() for entry in entries if entry.strip()]


def create_ui():  # noqa: C901
    # Create a Gradio interface
    with gr.Blocks(title="Email Settings Configuration") as app:
        gr.Markdown("# Email Settings Configuration")
        gr.Markdown(
            "> **Achtung:** Die Zugangsdaten werden im Klartext in "
            f"`{DEFAULT_CONFIG_PATH}` gespeichert. "
            "Nutze das Programm nur auf vertrauenswürdigen Rechnern."
        )

        # Function to get current accounts
        def get_current_accounts():
            settings = get_settings(reload=True)
            email_accounts = [email.account_name for email in settings.emails]
            return email_accounts

        # Function to update account list display
        def update_account_list():
            settings = get_settings(reload=True)
            email_accounts = [email.account_name for email in settings.emails]

            if email_accounts:
                # Create a detailed list of accounts with more information
                accounts_details = []
                for email in settings.emails:
                    details = [
                        f"**Account Name:** {email.account_name}",
                        f"**Full Name:** {email.full_name}",
                        f"**Email Address:** {email.email_address}",
                    ]

                    if hasattr(email, "description") and email.description:
                        details.append(f"**Description:** {email.description}")

                    # Add IMAP/SMTP provider info if available
                    if hasattr(email, "incoming") and hasattr(email.incoming, "host"):
                        details.append(f"**IMAP Provider:** {email.incoming.host}")

                    if hasattr(email, "outgoing") and hasattr(email.outgoing, "host"):
                        details.append(f"**SMTP Provider:** {email.outgoing.host}")

                    accounts_details.append("### " + email.account_name + "\n" + "\n".join(details) + "\n")

                accounts_md = "\n".join(accounts_details)
                return (
                    f"## Configured Accounts\n{accounts_md}",
                    gr.update(choices=email_accounts, value=None),
                    gr.update(visible=True),
                )
            else:
                return (
                    "No email accounts configured yet.",
                    gr.update(choices=[], value=None),
                    gr.update(visible=False),
                )

        def update_ai_send_tool_config():
            settings = get_settings(reload=True)
            email_accounts = [email.account_name for email in settings.emails]
            configured_account = settings.ai_sends_email_tool.allowed_account_name
            if configured_account not in email_accounts:
                configured_account = None
            recipients_text = "\n".join(settings.ai_sends_email_tool.allowed_recipients)
            return gr.update(choices=email_accounts, value=configured_account), recipients_text

        def save_ai_send_tool_config(allowed_account_name: str | None, allowed_recipients_raw: str):
            try:
                settings = get_settings()
                email_accounts = {email.account_name for email in settings.emails}
                if allowed_account_name and allowed_account_name not in email_accounts:
                    dropdown_update, recipients_text = update_ai_send_tool_config()
                    return "Error: Selected account does not exist.", dropdown_update, recipients_text

                recipients = _parse_allowed_recipients_input(allowed_recipients_raw)
                settings.ai_sends_email_tool = AiSendsEmailToolSettings(
                    allowed_account_name=allowed_account_name,
                    allowed_recipients=recipients,
                )
                store_settings(settings)
                dropdown_update, recipients_text = update_ai_send_tool_config()
                return "Success: AI Sends Email Tool configuration saved.", dropdown_update, recipients_text
            except Exception as e:
                dropdown_update, recipients_text = update_ai_send_tool_config()
                return f"Error: {e!s}", dropdown_update, recipients_text

        with gr.Accordion("AI Sends Email Tool", open=True):
            gr.Markdown(
                "### AI Sends Email Tool Configuration\n"
                "- Select exactly one allowed account for this tool.\n"
                "- Enter allowed recipients as one per line or comma-separated."
            )
            ai_send_allowed_account = gr.Dropdown(
                choices=[],
                label="Allowed Account Selection",
                interactive=True,
                allow_custom_value=False,
            )
            ai_send_allowed_recipients = gr.Textbox(
                label="Allowed Recipients List",
                lines=6,
                placeholder="recipient1@example.com\nrecipient2@example.com",
            )
            ai_send_status = gr.Markdown("")
            ai_send_save_btn = gr.Button("Save AI Sends Email Tool Settings")

            ai_send_save_btn.click(
                fn=save_ai_send_tool_config,
                inputs=[ai_send_allowed_account, ai_send_allowed_recipients],
                outputs=[ai_send_status, ai_send_allowed_account, ai_send_allowed_recipients],
            )

            app.load(
                fn=update_ai_send_tool_config,
                inputs=None,
                outputs=[ai_send_allowed_account, ai_send_allowed_recipients],
            )

        # Display current email accounts and allow deletion
        with gr.Accordion("Current Email Accounts", open=True):
            # Display the list of accounts
            accounts_display = gr.Markdown("")

            # Create a dropdown to select account to delete
            account_to_delete = gr.Dropdown(choices=[], label="Select Account to Delete", interactive=True)

            # Status message for deletion
            delete_status = gr.Markdown("")

            # Delete button
            delete_btn = gr.Button("Delete Selected Account")

            # Function to delete an account
            def delete_email_account(account_name):
                if not account_name:
                    return "Error: Please select an account to delete.", *update_account_list()

                try:
                    # Get current settings
                    settings = get_settings()

                    # Delete the account
                    settings.delete_email(account_name)

                    # Store settings
                    store_settings(settings)

                    # Return success message and update the UI
                    return f"Success: Email account '{account_name}' has been deleted.", *update_account_list()
                except Exception as e:
                    return f"Error: {e!s}", *update_account_list()

            # Connect the delete button to the delete function
            delete_event = delete_btn.click(
                fn=delete_email_account,
                inputs=[account_to_delete],
                outputs=[delete_status, accounts_display, account_to_delete, delete_btn],
            )
            delete_event.then(
                fn=update_ai_send_tool_config,
                inputs=None,
                outputs=[ai_send_allowed_account, ai_send_allowed_recipients],
            )

            # Initialize the account list
            app.load(
                fn=update_account_list,
                inputs=None,
                outputs=[accounts_display, account_to_delete, delete_btn],
            )

        # Form for adding a new email account
        with gr.Accordion("Add New Email Account", open=True):
            gr.Markdown("### Add New Email Account")

            # Basic account information
            account_name = gr.Textbox(label="Account Name", placeholder="e.g. work_email")
            full_name = gr.Textbox(label="Full Name", placeholder="e.g. John Doe")
            email_address = gr.Textbox(label="Email Address", placeholder="e.g. john@example.com")

            # Credentials
            user_name = gr.Textbox(label="Username", placeholder="e.g. john@example.com")
            password = gr.Textbox(label="Password", type="password")

            # IMAP settings
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### IMAP Settings")
                    imap_host = gr.Textbox(label="IMAP Host", placeholder="e.g. imap.example.com")
                    imap_port = gr.Number(label="IMAP Port", value=993)
                    imap_ssl = gr.Checkbox(label="Use SSL", value=True)
                    imap_user_name = gr.Textbox(
                        label="IMAP Username (optional)", placeholder="Leave empty to use the same as above"
                    )
                    imap_password = gr.Textbox(
                        label="IMAP Password (optional)",
                        type="password",
                        placeholder="Leave empty to use the same as above",
                    )

                # SMTP settings
                with gr.Column():
                    gr.Markdown("### SMTP Settings")
                    smtp_host = gr.Textbox(label="SMTP Host", placeholder="e.g. smtp.example.com")
                    smtp_port = gr.Number(label="SMTP Port", value=465)
                    smtp_ssl = gr.Checkbox(label="Use SSL", value=True)
                    smtp_start_ssl = gr.Checkbox(label="Start SSL", value=False)
                    smtp_user_name = gr.Textbox(
                        label="SMTP Username (optional)", placeholder="Leave empty to use the same as above"
                    )
                    smtp_password = gr.Textbox(
                        label="SMTP Password (optional)",
                        type="password",
                        placeholder="Leave empty to use the same as above",
                    )

            # Status message
            status_message = gr.Markdown("")

            # Save button
            save_btn = gr.Button("Save Email Settings")

            # Function to save settings
            def save_email_settings(
                account_name,
                full_name,
                email_address,
                user_name,
                password,
                imap_host,
                imap_port,
                imap_ssl,
                imap_user_name,
                imap_password,
                smtp_host,
                smtp_port,
                smtp_ssl,
                smtp_start_ssl,
                smtp_user_name,
                smtp_password,
            ):
                try:
                    # Validate required fields
                    if not account_name or not full_name or not email_address or not user_name or not password:
                        # Get account list update
                        account_md, account_choices, btn_visible = update_account_list()
                        return (
                            "Error: Please fill in all required fields.",
                            account_md,
                            account_choices,
                            btn_visible,
                            account_name,
                            full_name,
                            email_address,
                            user_name,
                            password,
                            imap_host,
                            imap_port,
                            imap_ssl,
                            imap_user_name,
                            imap_password,
                            smtp_host,
                            smtp_port,
                            smtp_ssl,
                            smtp_start_ssl,
                            smtp_user_name,
                            smtp_password,
                        )

                    if not imap_host or not smtp_host:
                        # Get account list update
                        account_md, account_choices, btn_visible = update_account_list()
                        return (
                            "Error: IMAP and SMTP hosts are required.",
                            account_md,
                            account_choices,
                            btn_visible,
                            account_name,
                            full_name,
                            email_address,
                            user_name,
                            password,
                            imap_host,
                            imap_port,
                            imap_ssl,
                            imap_user_name,
                            imap_password,
                            smtp_host,
                            smtp_port,
                            smtp_ssl,
                            smtp_start_ssl,
                            smtp_user_name,
                            smtp_password,
                        )

                    # Get current settings
                    settings = get_settings()

                    # Check if account name already exists
                    for email in settings.emails:
                        if email.account_name == account_name:
                            # Get account list update
                            account_md, account_choices, btn_visible = update_account_list()
                            return (
                                f"Error: Account name '{account_name}' already exists.",
                                account_md,
                                account_choices,
                                btn_visible,
                                account_name,
                                full_name,
                                email_address,
                                user_name,
                                password,
                                imap_host,
                                imap_port,
                                imap_ssl,
                                imap_user_name,
                                imap_password,
                                smtp_host,
                                smtp_port,
                                smtp_ssl,
                                smtp_start_ssl,
                                smtp_user_name,
                                smtp_password,
                            )

                    # Create new email settings
                    email_settings = EmailSettings.init(
                        account_name=account_name,
                        full_name=full_name,
                        email_address=email_address,
                        user_name=user_name,
                        password=password,
                        imap_host=imap_host,
                        smtp_host=smtp_host,
                        imap_port=int(imap_port),
                        imap_ssl=imap_ssl,
                        smtp_port=int(smtp_port),
                        smtp_ssl=smtp_ssl,
                        smtp_start_ssl=smtp_start_ssl,
                        imap_user_name=imap_user_name if imap_user_name else None,
                        imap_password=imap_password if imap_password else None,
                        smtp_user_name=smtp_user_name if smtp_user_name else None,
                        smtp_password=smtp_password if smtp_password else None,
                    )

                    # Add to settings
                    settings.add_email(email_settings)

                    # Store settings
                    store_settings(settings)

                    # Get account list update
                    account_md, account_choices, btn_visible = update_account_list()

                    # Return success message, update the UI, and clear form fields
                    return (
                        f"Success: Email account '{account_name}' has been added.",
                        account_md,
                        account_choices,
                        btn_visible,
                        "",  # Clear account_name
                        "",  # Clear full_name
                        "",  # Clear email_address
                        "",  # Clear user_name
                        "",  # Clear password
                        "",  # Clear imap_host
                        993,  # Reset imap_port
                        True,  # Reset imap_ssl
                        "",  # Clear imap_user_name
                        "",  # Clear imap_password
                        "",  # Clear smtp_host
                        465,  # Reset smtp_port
                        True,  # Reset smtp_ssl
                        False,  # Reset smtp_start_ssl
                        "",  # Clear smtp_user_name
                        "",  # Clear smtp_password
                    )
                except Exception as e:
                    # Get account list update
                    account_md, account_choices, btn_visible = update_account_list()
                    return (
                        f"Error: {e!s}",
                        account_md,
                        account_choices,
                        btn_visible,
                        account_name,
                        full_name,
                        email_address,
                        user_name,
                        password,
                        imap_host,
                        imap_port,
                        imap_ssl,
                        imap_user_name,
                        imap_password,
                        smtp_host,
                        smtp_port,
                        smtp_ssl,
                        smtp_start_ssl,
                        smtp_user_name,
                        smtp_password,
                    )

            # Connect the save button to the save function
            save_event = save_btn.click(
                fn=save_email_settings,
                inputs=[
                    account_name,
                    full_name,
                    email_address,
                    user_name,
                    password,
                    imap_host,
                    imap_port,
                    imap_ssl,
                    imap_user_name,
                    imap_password,
                    smtp_host,
                    smtp_port,
                    smtp_ssl,
                    smtp_start_ssl,
                    smtp_user_name,
                    smtp_password,
                ],
                outputs=[
                    status_message,
                    accounts_display,
                    account_to_delete,
                    delete_btn,
                    account_name,
                    full_name,
                    email_address,
                    user_name,
                    password,
                    imap_host,
                    imap_port,
                    imap_ssl,
                    imap_user_name,
                    imap_password,
                    smtp_host,
                    smtp_port,
                    smtp_ssl,
                    smtp_start_ssl,
                    smtp_user_name,
                    smtp_password,
                ],
            )
            save_event.then(
                fn=update_ai_send_tool_config,
                inputs=None,
                outputs=[ai_send_allowed_account, ai_send_allowed_recipients],
            )
        # Ariadne Engine Registration
        with gr.Accordion("Ariadne Engine Registration", open=True):
            gr.Markdown(
                "### Ariadne Engine Registration\n"
                "- Register this MCP (stdio) with your Ariadne Engine.\n"
                "- The MCP will be launched via stdio, no URL is required."
            )

            def _post_thread(endpoint_url: str, api_key_val: str, thread_name: str, payload: dict) -> httpx.Response:
                headers = {
                    "Authorization": f"Bearer {api_key_val}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                }
                body = {"thread_name": thread_name, "payload": payload}
                with httpx.Client(timeout=15.0) as client:
                    return client.post(endpoint_url, headers=headers, json=body)

            def _get_spec_by_name(endpoint_url: str, api_key_val: str, name: str) -> dict:
                try:
                    response = _post_thread(
                        endpoint_url,
                        api_key_val,
                        "get-mcp-server-spec-by-name",
                        {
                            "path_params": {"name": name},
                            "query_params": None,
                            "body_params_serialized": None,
                        },
                    )
                except Exception as exc:  # pragma: no cover - network errors
                    logger.error("Network error while checking spec name: %s", exc)
                    return {"error": f"Network error while checking name: {exc}"}

                if response.status_code == 404:
                    return {"data": None}
                if not (200 <= response.status_code < 300):
                    return {"error": f"Lookup failed ({response.status_code}): {response.text[:200]}"}
                try:
                    return {"data": response.json()}
                except Exception:
                    return {"error": f"Invalid JSON from lookup ({response.status_code})"}

            def configure_engine(
                api_key: str,
                endpoint_url: str,
                spec_name: str,
                command_path: str,
                tags_raw: str,
                description: str | None = None,
            ) -> str:
                api_key_s = (api_key or "").strip()
                endpoint_s = (endpoint_url or "").strip()
                name_s = (spec_name or "").strip()
                command_s = (command_path or "").strip()
                tags_s = (tags_raw or "").strip()
                description_s = (description or "").strip() if description is not None else ""

                if not api_key_s:
                    return "API key is required."
                if not endpoint_s or not _is_valid_url(endpoint_s):
                    return "Engine endpoint URL must be a valid URL (http/https)."
                if not name_s:
                    return "Name is required."
                if not command_s:
                    return "Command path is required."

                tags = [tag.strip() for tag in tags_s.split(",") if tag.strip()] if tags_s else []

                dto = {
                    "key": "",
                    "name": name_s,
                    "description": description_s,
                    "transport": "stdio",
                    "command": [command_s, "stdio"],
                    "url": None,
                    "bearer_token": None,
                    "env": None,
                    "tags": tags or None,
                    "is_standard": False,
                    "created_at": datetime.now().isoformat(),
                }

                lookup = _get_spec_by_name(endpoint_s, api_key_s, name_s)
                if "error" in lookup:
                    return f"Name check failed: {lookup['error']}"

                existing = lookup.get("data")

                try:
                    if existing is None:
                        response = _post_thread(
                            endpoint_s,
                            api_key_s,
                            "create-mcp-server-spec",
                            {
                                "path_params": None,
                                "query_params": None,
                                "body_params_serialized": json.dumps(dto),
                            },
                        )
                        if response.status_code != 201:
                            return f"Create failed ({response.status_code}): {response.text[:300]}"
                        try:
                            data = response.json().get("data")
                        except Exception:
                            data = None
                        key = (data or {}).get("key") if isinstance(data, dict) else None
                        return f"Created MCP Server Spec '{name_s}' (key={key or '?'})."
                    key = existing.get("key") if isinstance(existing, dict) else None
                    if not key:
                        return "Update failed: existing spec has no key."
                    response = _post_thread(
                        endpoint_s,
                        api_key_s,
                        "update-mcp-server-spec",
                        {
                            "path_params": {"key": key},
                            "query_params": None,
                            "body_params_serialized": json.dumps(dto),
                        },
                    )
                    if response.status_code != 200:
                        return f"Update failed ({response.status_code}): {response.text[:300]}"
                    return f"Updated MCP Server Spec '{name_s}' (key={key})."
                except Exception as exc:  # pragma: no cover - network errors
                    logger.error("Error contacting engine: %s", exc)
                    return f"Error contacting engine: {exc}"

            with gr.Row():
                api_key_input = gr.Textbox(label="Engine API Key (Bearer)", type="password")
                endpoint_input = gr.Textbox(
                    label="Engine Endpoint URL",
                    placeholder="https://aaa.ariadneanyerse.de",
                )

            with gr.Row():
                spec_name_input = gr.Textbox(
                    label="Spec Name (unique)",
                    placeholder="mcp-email-server",
                    value="mcp-email-server",
                )
                command_path_input = gr.Textbox(
                    label="MCP Command Path",
                    placeholder="./mcps/mcp_email_server_bin",
                    value="./mcps/mcp_email_server_bin",
                )

            tags_input = gr.Textbox(
                label="Tags (comma-separated, optional)",
                placeholder="email, stdio, prod",
            )
            description_input = gr.Textbox(label="Description (optional)", lines=3)
            engine_status = gr.Textbox(label="Engine Status", interactive=False)
            configure_button = gr.Button("Register / Update in Ariadne Engine")

            configure_button.click(
                fn=configure_engine,
                inputs=[
                    api_key_input,
                    endpoint_input,
                    spec_name_input,
                    command_path_input,
                    tags_input,
                    description_input,
                ],
                outputs=engine_status,
            )

    return app


def main():
    app = create_ui()
    app.launch(server_name="127.0.0.1", server_port=8765, inbrowser=True)


if __name__ == "__main__":
    main()
