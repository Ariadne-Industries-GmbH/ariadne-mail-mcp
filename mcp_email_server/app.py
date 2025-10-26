import os
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
from mcp_email_server.emails.models import EmailContentBatchResponse, EmailMetadataPageResponse

mcp = FastMCP("email")

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

@mcp.tool(description="Paginate emails, page start at 1, before and since as UTC datetime.")
async def page_email(
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
) -> EmailMetadataPageResponse:
    handler = dispatch_handler(account_name)

    response = await handler.get_emails_metadata(
        page=page,
        page_size=page_size,
        before=before,
        since=since,
        subject=subject,
        from_address=from_address,
        to_address=to_address,
        order=order,
    )
    
    return response

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
) -> EmailContentBatchResponse:
    handler = dispatch_handler(account_name)
    return await handler.get_emails_content(email_ids)


@mcp.tool(
    description="Send an email using the specified account. Recipient should be a list of email addresses.",
)
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
) -> str:
    enabled = os.getenv("MCP_EMAIL_SERVER_ENABLE_SENDING", "false").lower() in {"1", "true", "yes", "on"}
    if not enabled:
        raise PermissionError(
            "Email sending is disabled by configuration. Set MCP_EMAIL_SERVER_ENABLE_SENDING=1 to enable."
        )
    handler = dispatch_handler(account_name)
    await handler.send_email(recipients, subject, body, cc, bcc)
    # Return a simple success message for client UX/tests
    return f"Email sent successfully to {recipients[0]}"

@mcp.tool(description="List all folders in the specified email account.")
async def list_folders(account_name: Annotated[str, Field(description="The name of the email account.")]) -> list[str]:
    handler = dispatch_handler(account_name)
    return await handler.list_folders()

@mcp.tool(description="Move an email from one folder to another.")
async def move_email(
    account_name: Annotated[str, Field(description="The name of the email account.")],
    message_id: Annotated[str, Field(description="The ID of the email to move.")],
    source_folder: Annotated[str, Field(description="The source folder of the email.")],
    destination_folder: Annotated[str, Field(description="The destination folder of the email.")],
) -> bool:
    handler = dispatch_handler(account_name)
    return await handler.move_email(message_id, source_folder, destination_folder)

@mcp.tool(description="Delete an email from the specified folder.")
async def delete_email(
    account_name: Annotated[str, Field(description="The name of the email account.")],
    message_id: Annotated[str, Field(description="The ID of the email to delete.")],
    folder: Annotated[str, Field(default="INBOX", description="The folder containing the email.")] = "INBOX",
) -> bool:
    handler = dispatch_handler(account_name)
    return await handler.delete_email(message_id, folder)

@mcp.tool(description="Get the full body of an email.")
async def get_full_email_body(
    account_name: Annotated[str, Field(description="The name of the email account.")],
    message_id: Annotated[str, Field(description="The ID of the email to retrieve the full body for.")],
    folder: Annotated[str, Field(default="INBOX", description="The folder containing the email.")] = "INBOX",
) -> str:
    handler = dispatch_handler(account_name)
    return await handler.get_full_email_body(message_id, folder)

@mcp.tool(
    description="Mark an email (read/unread/flagged/unflagged/answered/draft) in the specified folder.",
)
async def mark_email(
    account_name: Annotated[str, Field(description="The name of the email account.")],
    message_id: Annotated[str, Field(description="The ID of the email to mark.")],
    folder: Annotated[str, Field(default="INBOX", description="The folder containing the email.")] = "INBOX",
    mark: Annotated[
        Literal["read", "unread", "flagged", "unflagged", "answered", "draft"],
        Field(description="Mark to apply: read/unread/flagged/unflagged/answered/draft."),
    ] = "read",
) -> bool:
    handler = dispatch_handler(account_name)
    return await handler.mark_email(message_id, folder, mark)
