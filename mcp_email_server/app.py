import os
import re
from datetime import datetime
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from mcp_email_server.config import (
    AccountAttributes,
    EmailSettings,
    ProviderSettings,
    get_settings,
)
from mcp_email_server.emails.dispatcher import dispatch_handler
from mcp_email_server.emails.models import (
    AttachmentDownloadResponse,
    EmailContentBatchResponse,
    EmailMetadataPageResponse,
)

mcp = FastMCP("email")
EMAIL_ADDRESS_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _looks_like_rfc_message_id(value: str) -> bool:
    value = value.strip()
    return value.startswith("<") and value.endswith(">") and "@" in value


def _validate_imap_uid(email_id: str) -> str:
    email_id = email_id.strip()
    if _looks_like_rfc_message_id(email_id):
        raise ValueError(
            "Expected IMAP UID `email_id` from `list_emails_metadata`, but got an RFC Message-ID header. "
            "Use `message_id` only for email threading (`send_email` -> `in_reply_to` / `references`)."
        )
    if not email_id.isdigit():
        raise ValueError(
            f"Expected IMAP UID `email_id` as numeric string from `list_emails_metadata`, got {email_id!r}."
        )
    return email_id


def _validate_imap_uids(email_ids: list[str]) -> list[str]:
    return [_validate_imap_uid(email_id) for email_id in email_ids]


def _normalize_email_address(address: str) -> str:
    return address.strip().lower()


def _is_valid_email_address(address: str) -> bool:
    return bool(EMAIL_ADDRESS_REGEX.fullmatch(address))


def _validate_and_normalize_recipients(recipients: list[str]) -> tuple[list[str], list[str]]:
    normalized_recipients: list[str] = []
    seen: set[str] = set()
    invalid_inputs: list[str] = []

    for recipient in recipients:
        normalized = _normalize_email_address(recipient)
        if not normalized or not _is_valid_email_address(normalized):
            invalid_inputs.append(recipient)
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        normalized_recipients.append(normalized)

    return normalized_recipients, invalid_inputs

@mcp.resource("email://{account_name}")
async def get_account(account_name: str) -> EmailSettings | ProviderSettings | None:
    settings = get_settings()
    return settings.get_account(account_name, masked=True)


@mcp.tool(description="List all configured email accounts with masked credentials.")
async def list_available_accounts() -> list[AccountAttributes]:
    settings = get_settings()
    return [account.masked() for account in settings.get_accounts()]


@mcp.tool(description="Add a new email account configuration to the settings.")
async def add_email_account(email: EmailSettings) -> str:
    settings = get_settings()
    settings.add_email(email)
    settings.store()
    return f"Successfully added email account '{email.account_name}'"


@mcp.tool(description="Retrieve the pre-approved recipient emails for the restricted email sending tool.")
async def get_allowed_recipients() -> dict[str, Any]:
    settings = get_settings()
    recipients = settings.ai_sends_email_tool.allowed_recipients
    if not recipients:
        return {"allowed_recipients": [], "error": "No allowed recipients configured."}
    return {"allowed_recipients": recipients, "error": None}


@mcp.tool(
    description=(
        "Send an email only to pre-approved recipients using the fixed configured account. "
        "Before using this tool, call `get_allowed_recipients` to retrieve the list of approved addresses."
    )
)
async def send_email_to_allowed_recipients(
    to: Annotated[list[str], Field(description="List of recipient email addresses. Can be a subset of the allowed recipients.")],
    subject: Annotated[str, Field(description="Email subject.")],
    body: Annotated[str, Field(description="Email body.")],
) -> dict[str, Any]:
    settings = get_settings()
    tool_settings = settings.ai_sends_email_tool

    if not tool_settings.allowed_account_name:
        return {"success": False, "error": "No email account configured for this tool."}

    if not to:
        return {"success": False, "error": "No recipients provided."}

    normalized_to, invalid_inputs = _validate_and_normalize_recipients(to)
    allowed_set = set(tool_settings.allowed_recipients)
    disallowed_recipients = [recipient for recipient in normalized_to if recipient not in allowed_set]

    if invalid_inputs or disallowed_recipients:
        errors: list[str] = []
        if invalid_inputs:
            errors.append("Invalid email address format.")
        if disallowed_recipients:
            errors.append("Recipient(s) not in allowed list.")
        return {"success": False, "error": " ".join(errors)}

    configured_account = settings.get_account(tool_settings.allowed_account_name)
    if not isinstance(configured_account, EmailSettings):
        tool_settings.allowed_account_name = None
        tool_settings.allowed_recipients = []
        settings.store()
        return {"success": False, "error": "No email account configured for this tool."}

    handler = dispatch_handler(tool_settings.allowed_account_name)
    await handler.send_email(normalized_to, subject, body, None, None, False, None, None, None)
    return {
        "success": True,
        "message": "Email sent successfully",
        "sent_to": normalized_to,
    }

@mcp.tool(
    description="List email metadata (email_id, subject, sender, recipients, date) without body content. Returns email_id for use with get_emails_content."
)
async def list_emails_metadata(
    account_name: Annotated[str, Field(description="The name of the email account.")],
    page: Annotated[
        int,
        Field(default=1, description="The page number to retrieve (starting from 1)."),
    ] = 1,
    page_size: Annotated[int, Field(default=10, description="The number of emails to retrieve per page.")] = 10,
    before: Annotated[
        datetime | None,
        Field(default=None, description="Retrieve emails before this datetime (UTC)."),
    ] = None,
    since: Annotated[
        datetime | None,
        Field(default=None, description="Retrieve emails since this datetime (UTC)."),
    ] = None,
    subject: Annotated[str | None, Field(default=None, description="Filter emails by subject.")] = None,
    from_address: Annotated[str | None, Field(default=None, description="Filter emails by sender address.")] = None,
    to_address: Annotated[
        str | None,
        Field(default=None, description="Filter emails by recipient address."),
    ] = None,
    order: Annotated[
        Literal["asc", "desc"],
        Field(default=None, description="Order emails by field. `asc` or `desc`."),
    ] = "desc",
    mailbox: Annotated[str, Field(default="INBOX", description="The mailbox to retrieve emails from.")] = "INBOX",
) -> EmailMetadataPageResponse:
    handler = dispatch_handler(account_name)

    return await handler.get_emails_metadata(
        page=page,
        page_size=page_size,
        before=before,
        since=since,
        subject=subject,
        from_address=from_address,
        to_address=to_address,
        order=order,
        mailbox=mailbox,
    )

@mcp.tool(
    description="Get the full content (including body) of one or more emails by their email_id. Use list_emails_metadata first to get the email_id."
)
async def get_emails_content(
    account_name: Annotated[str, Field(description="The name of the email account.")],
    email_ids: Annotated[
        list[str],
        Field(
            description="List of email_id to retrieve (obtained from list_emails_metadata). Can be a single email_id or multiple email_ids."
        ),
    ],
    mailbox: Annotated[str, Field(default="INBOX", description="The mailbox to retrieve emails from.")] = "INBOX",
) -> EmailContentBatchResponse:
    email_ids = _validate_imap_uids(email_ids)
    handler = dispatch_handler(account_name)
    return await handler.get_emails_content(email_ids, mailbox)


# @mcp.tool(
#     description="Send an email using the specified account. Supports replying to emails with proper threading when in_reply_to is provided.",
# )
async def send_email(
    account_name: Annotated[str, Field(description="The name of the email account to send from.")],
    recipients: Annotated[list[str], Field(description="A list of recipient email addresses.")],
    subject: Annotated[str, Field(description="The subject of the email.")],
    body: Annotated[str, Field(description="The body of the email.")],
    cc: Annotated[
        list[str] | None,
        Field(default=None, description="A list of CC email addresses."),
    ] = None,
    bcc: Annotated[
        list[str] | None,
        Field(default=None, description="A list of BCC email addresses."),
    ] = None,
    html: Annotated[
        bool,
        Field(default=False, description="Whether to send the email as HTML (True) or plain text (False)."),
    ] = False,
    attachments: Annotated[
        list[str] | None,
        Field(
            default=None,
            description="A list of absolute file paths to attach to the email. Supports common file types (documents, images, archives, etc.).",
        ),
    ] = None,
    in_reply_to: Annotated[
        str | None,
        Field(
            default=None,
            description="Message-ID of the email being replied to. Enables proper threading in email clients.",
        ),
    ] = None,
    references: Annotated[
        str | None,
        Field(
            default=None,
            description="Space-separated Message-IDs for the thread chain. Usually includes in_reply_to plus ancestors.",
        ),
    ] = None,
) -> str:
    enabled = os.getenv("MCP_EMAIL_SERVER_ENABLE_SENDING", "false").lower() in {"1", "true", "yes", "on"}
    if not enabled:
        raise PermissionError(
            "Email sending is disabled by configuration. Set MCP_EMAIL_SERVER_ENABLE_SENDING=1 to enable."
        )
    handler = dispatch_handler(account_name)
    await handler.send_email(
            recipients,
            subject,
            body,
            cc,
            bcc,
            html,
            attachments,
            in_reply_to,
            references,
        )
    recipient_str = ", ".join(recipients)
    attachment_info = f" with {len(attachments)} attachment(s)" if attachments else ""
    return f"Email sent successfully to {recipient_str}{attachment_info}"


# @mcp.tool(
#     description="Delete one or more emails by their email_id. Use list_emails_metadata first to get the email_id."
# )
async def delete_emails(
    account_name: Annotated[str, Field(description="The name of the email account.")],
    email_ids: Annotated[
        list[str],
        Field(description="List of email_id to delete (obtained from list_emails_metadata)."),
    ],
    mailbox: Annotated[str, Field(default="INBOX", description="The mailbox to delete emails from.")] = "INBOX",
) -> str:
    email_ids = _validate_imap_uids(email_ids)
    handler = dispatch_handler(account_name)
    deleted_ids, failed_ids = await handler.delete_emails(email_ids, mailbox)

    result = f"Successfully deleted {len(deleted_ids)} email(s)"
    if failed_ids:
        result += f", failed to delete {len(failed_ids)} email(s): {', '.join(failed_ids)}"
    return result


@mcp.tool(
    description="Download an email attachment and save it to the specified path. This feature must be explicitly enabled in settings (enable_attachment_download=true) due to security considerations.",
)
async def download_attachment(
    account_name: Annotated[str, Field(description="The name of the email account.")],
    email_id: Annotated[
        str, Field(description="The email ID (obtained from list_emails_metadata or get_emails_content).")
    ],
    attachment_name: Annotated[
        str, Field(description="The name of the attachment to download (as shown in the attachments list).")
    ],
    save_path: Annotated[str, Field(description="The absolute path where the attachment should be saved.")],
) -> AttachmentDownloadResponse:
    settings = get_settings()
    if not settings.enable_attachment_download:
        msg = (
            "Attachment download is disabled. Set 'enable_attachment_download=true' in settings to enable this feature."
        )
        raise PermissionError(msg)

    email_id = _validate_imap_uid(email_id)
    handler = dispatch_handler(account_name)
    return await handler.download_attachment(email_id, attachment_name, save_path)

@mcp.tool(description="List all folders in the specified email account.")
async def list_folders(account_name: Annotated[str, Field(description="The name of the email account.")]) -> list[str]:
    handler = dispatch_handler(account_name)
    return await handler.list_folders()

@mcp.tool(description="Move an email (by IMAP UID / email_id) from one folder to another.")
async def move_email(
    account_name: Annotated[str, Field(description="The name of the email account.")],
    email_id: Annotated[str, Field(description="The IMAP UID (email_id) of the email to move.")],
    source_folder: Annotated[str, Field(description="The source folder of the email.")],
    destination_folder: Annotated[str, Field(description="The destination folder of the email.")],
) -> str:
    email_id = _validate_imap_uid(email_id)
    handler = dispatch_handler(account_name)
    success = await handler.move_email(email_id, source_folder, destination_folder)
    return "Email moved successfully!" if success else "Failed to move email"


@mcp.tool(
    description=(
        "Convenient shortcut: get only the body of a single email by IMAP UID (email_id from "
        "list_emails_metadata). Prefer get_emails_content when you also need metadata/attachments."
    )
)
async def get_full_email_body(
    account_name: Annotated[str, Field(description="The name of the email account.")],
    email_id: Annotated[
        str,
        Field(description="The IMAP UID (email_id from list_emails_metadata) of the email to retrieve."),
    ],
    folder: Annotated[str, Field(default="INBOX", description="The folder containing the email.")] = "INBOX",
) -> str:
    email_id = _validate_imap_uid(email_id)
    handler = dispatch_handler(account_name)
    return await handler.get_full_email_body(email_id, folder)

@mcp.tool(
    description="Mark an email (read/unread/flagged/unflagged/answered/draft) in the specified folder.",
)
async def mark_email(
    account_name: Annotated[str, Field(description="The name of the email account.")],
    email_id: Annotated[str, Field(description="The IMAP UID (email_id) of the email to mark.")],
    folder: Annotated[str, Field(default="INBOX", description="The folder containing the email.")] = "INBOX",
    mark: Annotated[
        Literal["read", "unread", "flagged", "unflagged", "answered", "draft"],
        Field(description="Mark to apply: read/unread/flagged/unflagged/answered/draft."),
    ] = "read",
) -> bool:
    email_id = _validate_imap_uid(email_id)
    handler = dispatch_handler(account_name)
    return await handler.mark_email(email_id, folder, mark)
