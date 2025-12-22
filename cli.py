#!/usr/bin/env python3
"""
CLI tool for interacting with the EmailClient for debugging and productive use.

This script provides command-line access to the EmailClient class in mcp_email_server/emails/classic.py
to allow for testing, debugging, and productive use of email functionality.
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from typing import Optional

from mcp_email_server.config import EmailServer, EmailSettings
from mcp_email_server.emails.classic import EmailClient


async def list_emails(
    client: EmailClient,
    page: int = 1,
    page_size: int = 10,
    before: Optional[datetime] = None,
    since: Optional[datetime] = None,
    subject: Optional[str] = None,
    from_address: Optional[str] = None,
    to_address: Optional[str] = None,
    order: str = "desc",
) -> None:
    """List emails with metadata."""
    print(f"\nListing emails (page {page}, {page_size} per page)...")
    
    emails = []
    async for email_data in client.get_emails_metadata_stream(
        page=page,
        page_size=page_size,
        before=before,
        since=since,
        subject=subject,
        from_address=from_address,
        to_address=to_address,
        order=order,
    ):
        emails.append(email_data)
    
    total = await client.get_email_count(before, since, subject, from_address, to_address)
    
    print(f"\nFound {len(emails)} emails (total: {total})")
    print("-" * 80)
    
    for i, email in enumerate(emails, start=1):
        print(f"\nEmail {i} of {len(emails)}:")
        print(f"  ID: {email['email_id']}")
        print(f"  Subject: {email['subject']}")
        print(f"  From: {email['from']}")
        print(f"  To: {', '.join(email['to'])}")
        print(f"  Date: {email['date']}")
        print(f"  Attachments: {len(email['attachments'])}")


async def get_email_body(client: EmailClient, email_id: str) -> None:
    """Get the full body of a specific email."""
    print(f"\nFetching email body for ID: {email_id}...")
    
    email_data = await client.get_email_body_by_id(email_id)
    
    if email_data:
        print(f"\nSubject: {email_data['subject']}")
        print(f"From: {email_data['from']}")
        print(f"To: {', '.join(email_data['to'])}")
        print(f"Date: {email_data['date']}")
        print(f"\nBody ({len(email_data['body'])} characters):")
        print("-" * 80)
        print(email_data['body'])
        print("-" * 80)
        
        if email_data['attachments']:
            print(f"\nAttachments: {', '.join(email_data['attachments'])}")
    else:
        print(f"Error: Could not retrieve email with ID {email_id}")


async def send_email(
    client: EmailClient,
    recipients: list[str],
    subject: str,
    body: str,
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
    html: bool = False,
) -> None:
    """Send an email."""
    print(f"\nSending email to: {', '.join(recipients)}")
    print(f"Subject: {subject}")
    print(f"Body length: {len(body)} characters")
    
    if cc:
        print(f"CC: {', '.join(cc)}")
    if bcc:
        print(f"BCC: {len(bcc)} recipients (hidden)")
    
    try:
        await client.send_email(recipients, subject, body, cc, bcc, html)
        print("\nEmail sent successfully!")
    except Exception as e:
        print(f"\nError sending email: {e}")
        sys.exit(1)


async def list_folders(client: EmailClient, include_noselect: bool = True) -> None:
    """List all folders in the mail account."""
    print(f"\nListing folders (include_noselect={include_noselect})...")
    
    folders = await client.list_folders(include_noselect)
    
    print(f"\nFound {len(folders)} folders:")
    print("-" * 80)
    for folder in folders:
        print(f"  {folder}")


async def get_email_count(
    client: EmailClient,
    before: Optional[datetime] = None,
    since: Optional[datetime] = None,
    subject: Optional[str] = None,
    from_address: Optional[str] = None,
    to_address: Optional[str] = None,
) -> None:
    """Get the count of emails matching criteria."""
    print(f"\nCounting emails...")
    
    count = await client.get_email_count(before, since, subject, from_address, to_address)
    
    print(f"\nTotal emails matching criteria: {count}")


async def move_email(
    client: EmailClient,
    message_id: str,
    source_folder: str,
    destination_folder: str,
) -> None:
    """Move an email from one folder to another."""
    print(f"\nMoving email {message_id} from {source_folder} to {destination_folder}...")
    
    success = await client.move_email(message_id, source_folder, destination_folder)
    
    if success:
        print("Email moved successfully!")
    else:
        print("Error: Failed to move email")
        sys.exit(1)


async def delete_email(client: EmailClient, message_id: str, folder: str = "INBOX") -> None:
    """Delete an email."""
    print(f"\nDeleting email {message_id} from {folder}...")
    
    success = await client.delete_email(message_id, folder)
    
    if success:
        print("Email deleted successfully!")
    else:
        print("Error: Failed to delete email")
        sys.exit(1)


async def mark_email(
    client: EmailClient,
    message_id: str,
    folder: str = "INBOX",
    mark: str = "read",
) -> None:
    """Mark an email with a flag."""
    print(f"\nMarking email {message_id} as {mark} in {folder}...")
    
    success = await client.set_flag(message_id, folder, mark, True)
    
    if success:
        print(f"Email marked as {mark} successfully!")
    else:
        print(f"Error: Failed to mark email as {mark}")
        sys.exit(1)


async def export_emails(
    client: EmailClient,
    output_file: str,
    page_size: int = 100,
    max_pages: int = 10,
) -> None:
    """Export emails to a JSON file."""
    print(f"\nExporting emails to {output_file}...")
    
    all_emails = []
    
    for page in range(1, max_pages + 1):
        print(f"  Processing page {page}...")
        
        emails = []
        async for email_data in client.get_emails_metadata_stream(page=page, page_size=page_size):
            emails.append(email_data)
        
        if not emails:
            print(f"  No more emails found after page {page}")
            break
        
        all_emails.extend(emails)
    
    print(f"\nExported {len(all_emails)} emails")
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_emails, f, indent=2, default=str)
    
    print(f"\nExported to {output_file}")


async def main():
    """Main CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Email Client CLI Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List last 5 emails
  email-cli list --page 1 --page-size 5

  # Get body of a specific email
  email-cli get-body --email-id "12345"

  # Send an email
  email-cli send --to user@example.com --subject "Test" --body "Hello World"

  # List all folders
  email-cli list-folders

  # Export emails to JSON
  email-cli export --output emails.json
        """,
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # List command
    list_parser = subparsers.add_parser("list", help="List emails")
    list_parser.add_argument("--page", type=int, default=1, help="Page number")
    list_parser.add_argument("--page-size", type=int, default=10, help="Emails per page")
    list_parser.add_argument("--before", type=str, help="Filter by date before (YYYY-MM-DD)")
    list_parser.add_argument("--since", type=str, help="Filter by date since (YYYY-MM-DD)")
    list_parser.add_argument("--subject", type=str, help="Filter by subject")
    list_parser.add_argument("--from", "--from-address", type=str, help="Filter by sender")
    list_parser.add_argument("--to", "--to-address", type=str, help="Filter by recipient")
    list_parser.add_argument("--order", type=str, default="desc", help="Order: asc or desc")
    list_parser.set_defaults(func=list_emails)
    
    # Get body command
    get_body_parser = subparsers.add_parser("get-body", help="Get email body")
    get_body_parser.add_argument("--email-id", required=True, help="Email ID/UID")
    get_body_parser.set_defaults(func=get_email_body)
    
    # Send command
    send_parser = subparsers.add_parser("send", help="Send an email")
    send_parser.add_argument("--to", required=True, nargs="+", help="Recipient email(s)")
    send_parser.add_argument("--subject", required=True, help="Email subject")
    send_parser.add_argument("--body", required=True, help="Email body")
    send_parser.add_argument("--cc", nargs="*", help="CC recipients")
    send_parser.add_argument("--bcc", nargs="*", help="BCC recipients")
    send_parser.add_argument("--html", action="store_true", help="Send as HTML")
    send_parser.set_defaults(func=send_email)
    
    # List folders command
    folders_parser = subparsers.add_parser("list-folders", help="List folders")
    folders_parser.add_argument(
        "--no-noselect",
        action="store_false",
        dest="include_noselect",
        help="Exclude folders marked as NOSELECT",
    )
    folders_parser.set_defaults(func=list_folders)
    
    # Count command
    count_parser = subparsers.add_parser("count", help="Count emails")
    count_parser.add_argument("--before", type=str, help="Filter by date before (YYYY-MM-DD)")
    count_parser.add_argument("--since", type=str, help="Filter by date since (YYYY-MM-DD)")
    count_parser.add_argument("--subject", type=str, help="Filter by subject")
    count_parser.add_argument("--from", "--from-address", type=str, help="Filter by sender")
    count_parser.add_argument("--to", "--to-address", type=str, help="Filter by recipient")
    count_parser.set_defaults(func=get_email_count)
    
    # Move command
    move_parser = subparsers.add_parser("move", help="Move email")
    move_parser.add_argument("--email-id", required=True, help="Email ID/UID")
    move_parser.add_argument("--source", required=True, help="Source folder")
    move_parser.add_argument("--destination", required=True, help="Destination folder")
    move_parser.set_defaults(func=move_email)
    
    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete email")
    delete_parser.add_argument("--email-id", required=True, help="Email ID/UID")
    delete_parser.add_argument("--folder", default="INBOX", help="Folder containing email")
    delete_parser.set_defaults(func=delete_email)
    
    # Mark command
    mark_parser = subparsers.add_parser("mark", help="Mark email")
    mark_parser.add_argument("--email-id", required=True, help="Email ID/UID")
    mark_parser.add_argument("--folder", default="INBOX", help="Folder containing email")
    mark_parser.add_argument(
        "--mark",
        required=True,
        choices=["read", "unread", "flagged", "unflagged", "answered", "draft"],
        help="Mark type",
    )
    mark_parser.set_defaults(func=mark_email)
    
    # Export command
    export_parser = subparsers.add_parser("export", help="Export emails to JSON")
    export_parser.add_argument("--output", required=True, help="Output file path")
    export_parser.add_argument("--page-size", type=int, default=100, help="Emails per page")
    export_parser.add_argument("--max-pages", type=int, default=10, help="Maximum pages to export")
    export_parser.set_defaults(func=export_emails)
    
    args = parser.parse_args()
    
    # Parse date arguments
    if hasattr(args, "before") and args.before:
        args.before = datetime.strptime(args.before, "%Y-%m-%d")
    if hasattr(args, "since") and args.since:
        args.since = datetime.strptime(args.since, "%Y-%m-%d")
    
    # Create email client
    from mcp_email_server.config import get_settings
    
    config = get_settings()
    
    # Use incoming server for most operations
    email_server = EmailServer(
        host=config.emails[0].incoming.host,
        port=config.emails[0].incoming.port,
        user_name=config.emails[0].incoming.user_name,
        password=config.emails[0].incoming.password,
        use_ssl=config.emails[0].incoming.use_ssl,
        start_ssl=config.emails[0].incoming.start_ssl,
    )
    
    client = EmailClient(email_server)
    
    # Call the appropriate function
    # Filter out 'command' and 'func' from args as they're not needed by the functions
    filtered_args = {k: v for k, v in vars(args).items() if k not in ('command', 'func')}
    await args.func(client, **filtered_args)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
