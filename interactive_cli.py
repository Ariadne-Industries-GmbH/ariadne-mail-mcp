#!/usr/bin/env python3
"""
Interactive CLI tool for testing the EmailClient functionality.

This script provides an interactive command-line interface to test all features
exposed by the EmailClient class in mcp_email_server/emails/classic.py.
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from typing import Optional, List

from mcp_email_server.config import EmailServer, EmailSettings
from mcp_email_server.emails.classic import EmailClient


class InteractiveEmailCLI:
    """Interactive CLI for testing EmailClient functionality."""
    
    def __init__(self):
        self.client = None
        self.config = None
        self.initialized = False
    
    async def initialize(self):
        """Initialize the email client with configuration."""
        from mcp_email_server.config import get_settings
        
        self.config = get_settings()
        
        # Check if we have any email accounts configured
        if not self.config.emails:
            print("Error: No email accounts configured. Please configure your email settings.")
            print("You can set environment variables or create a config file.")
            return False
        
        # Use incoming server for most operations
        email_server = EmailServer(
            host=self.config.emails[0].incoming.host,
            port=self.config.emails[0].incoming.port,
            user_name=self.config.emails[0].incoming.user_name,
            password=self.config.emails[0].incoming.password,
            use_ssl=self.config.emails[0].incoming.use_ssl,
            start_ssl=self.config.emails[0].incoming.start_ssl,
        )
        
        self.client = EmailClient(email_server)
        self.initialized = True
        print("✓ Email client initialized successfully")
        return True
    
    async def list_emails(
        self,
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
        if not self.initialized:
            print("Error: Client not initialized")
            return
            
        print(f"\nListing emails (page {page}, {page_size} per page)...")
        
        emails = []
        async for email_data in self.client.get_emails_metadata_stream(
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
        
        total = await self.client.get_email_count(before, since, subject, from_address, to_address)
        
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
    
    async def get_email_body(self, email_id: str) -> None:
        """Get the full body of a specific email."""
        if not self.initialized:
            print("Error: Client not initialized")
            return
            
        print(f"\nFetching email body for ID: {email_id}...")
        
        email_data = await self.client.get_email_body_by_id(email_id)
        
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
        self,
        recipients: List[str],
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        html: bool = False,
    ) -> None:
        """Send an email."""
        if not self.initialized:
            print("Error: Client not initialized")
            return
            
        print(f"\nSending email to: {', '.join(recipients)}")
        print(f"Subject: {subject}")
        print(f"Body length: {len(body)} characters")
        
        if cc:
            print(f"CC: {', '.join(cc)}")
        if bcc:
            print(f"BCC: {len(bcc)} recipients (hidden)")
        
        try:
            await self.client.send_email(recipients, subject, body, cc, bcc, html)
            print("\nEmail sent successfully!")
        except Exception as e:
            print(f"\nError sending email: {e}")
    
    async def list_folders(self, include_noselect: bool = True) -> None:
        """List all folders in the mail account."""
        if not self.initialized:
            print("Error: Client not initialized")
            return
            
        print(f"\nListing folders (include_noselect={include_noselect})...")
        
        folders = await self.client.list_folders(include_noselect)
        
        print(f"\nFound {len(folders)} folders:")
        print("-" * 80)
        for folder in folders:
            print(f"  {folder}")
    
    async def get_email_count(
        self,
        before: Optional[datetime] = None,
        since: Optional[datetime] = None,
        subject: Optional[str] = None,
        from_address: Optional[str] = None,
        to_address: Optional[str] = None,
    ) -> None:
        """Get the count of emails matching criteria."""
        if not self.initialized:
            print("Error: Client not initialized")
            return
            
        print(f"\nCounting emails...")
        
        count = await self.client.get_email_count(before, since, subject, from_address, to_address)
        
        print(f"\nTotal emails matching criteria: {count}")
    
    async def move_email(
        self,
        email_id: str,
        source_folder: str,
        destination_folder: str,
    ) -> None:
        """Move an email from one folder to another."""
        if not self.initialized:
            print("Error: Client not initialized")
            return
            
        print(f"\nMoving email {email_id} from {source_folder} to {destination_folder}...")
        
        success = await self.client.move_email(email_id, source_folder, destination_folder)
        
        if success:
            print("Email moved successfully!")
        else:
            print("Error: Failed to move email")
    
    async def delete_email(self, email_id: str, folder: str = "INBOX") -> None:
        """Delete an email."""
        if not self.initialized:
            print("Error: Client not initialized")
            return
            
        print(f"\nDeleting email {email_id} from {folder}...")
        
        success = await self.client.delete_email(email_id, folder)
        
        if success:
            print("Email deleted successfully!")
        else:
            print("Error: Failed to delete email")
    
    async def mark_email(
        self,
        email_id: str,
        folder: str = "INBOX",
        mark: str = "read",
    ) -> None:
        """Mark an email with a flag."""
        if not self.initialized:
            print("Error: Client not initialized")
            return
            
        print(f"\nMarking email {email_id} as {mark} in {folder}...")
        
        success = await self.client.set_flag(email_id, folder, mark, True)
        
        if success:
            print(f"Email marked as {mark} successfully!")
        else:
            print(f"Error: Failed to mark email as {mark}")
    
    async def export_emails(
        self,
        output: str,
        page_size: int = 100,
        max_pages: int = 10,
    ) -> None:
        """Export emails to a JSON file."""
        if not self.initialized:
            print("Error: Client not initialized")
            return
            
        print(f"\nExporting emails to {output}...")
        
        all_emails = []
        
        for page in range(1, max_pages + 1):
            print(f"  Processing page {page}...")
            
            emails = []
            async for email_data in self.client.get_emails_metadata_stream(page=page, page_size=page_size):
                emails.append(email_data)
            
            if not emails:
                print(f"  No more emails found after page {page}")
                break
            
            all_emails.extend(emails)
        
        print(f"\nExported {len(all_emails)} emails")
        
        with open(output, "w", encoding="utf-8") as f:
            json.dump(all_emails, f, indent=2, default=str)
        
        print(f"\nExported to {output}")
    
    def parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse a date string in YYYY-MM-DD format."""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            print(f"Error: Invalid date format. Use YYYY-MM-DD")
            return None
    
    def get_input(self, prompt: str, default: str = "", password: bool = False) -> str:
        """Get user input with optional default value."""
        if password:
            import getpass
            return getpass.getpass(prompt)
        
        value = input(f"{prompt}[{default}]: ").strip()
        return value if value else default
    
    def get_choice(self, prompt: str, choices: List[str], default: str = "") -> str:
        """Get user choice from a list of options."""
        while True:
            value = self.get_input(f"{prompt} ", default)
            if not value and default:
                return default
            if value in choices:
                return value
            print(f"Error: Invalid choice. Please choose from: {', '.join(choices)}")
    
    def get_int_input(self, prompt: str, default: int = 0) -> int:
        """Get integer input from user."""
        while True:
            value = self.get_input(f"{prompt} ", str(default))
            try:
                return int(value)
            except ValueError:
                print("Error: Please enter a valid integer")
    
    def get_email_list(self, prompt: str) -> List[str]:
        """Get a list of email addresses from user."""
        emails = []
        while True:
            email = self.get_input(f"{prompt} ", "")
            if not email:
                break
            emails.append(email)
        return emails
    
    async def interactive_loop(self):
        """Main interactive loop."""
        print("=" * 80)
        print("Interactive Email Client CLI")
        print("=" * 80)
        
        # Initialize client
        if not await self.initialize():
            return
        
        while True:
            print("\n" + "=" * 80)
            print("Available commands:")
            print("  1. List emails")
            print("  2. Get email body")
            print("  3. Send email")
            print("  4. List folders")
            print("  5. Get email count")
            print("  6. Move email")
            print("  7. Delete email")
            print("  8. Mark email")
            print("  9. Export emails")
            print("  0. Exit")
            print("=" * 80)
            
            choice = self.get_input("\nSelect a command (0-9): ", "")
            
            if choice == "0":
                print("\nGoodbye!")
                break
            elif choice == "1":
                await self._handle_list_emails()
            elif choice == "2":
                await self._handle_get_email_body()
            elif choice == "3":
                await self._handle_send_email()
            elif choice == "4":
                await self._handle_list_folders()
            elif choice == "5":
                await self._handle_get_email_count()
            elif choice == "6":
                await self._handle_move_email()
            elif choice == "7":
                await self._handle_delete_email()
            elif choice == "8":
                await self._handle_mark_email()
            elif choice == "9":
                await self._handle_export_emails()
            else:
                print("Error: Invalid choice. Please try again.")
    
    async def _handle_list_emails(self):
        """Handle list emails command interactively."""
        page = self.get_int_input("Page number: ", 1)
        page_size = self.get_int_input("Emails per page: ", 10)
        
        before_str = self.get_input("Filter by date before (YYYY-MM-DD): ", "")
        before = self.parse_date(before_str)
        
        since_str = self.get_input("Filter by date since (YYYY-MM-DD): ", "")
        since = self.parse_date(since_str)
        
        subject = self.get_input("Filter by subject: ", "")
        from_address = self.get_input("Filter by sender: ", "")
        to_address = self.get_input("Filter by recipient: ", "")
        
        order = self.get_choice(
            "Order (asc/desc): ",
            ["asc", "desc"],
            "desc"
        )
        
        await self.list_emails(
            page=page,
            page_size=page_size,
            before=before,
            since=since,
            subject=subject,
            from_address=from_address,
            to_address=to_address,
            order=order,
        )
    
    async def _handle_get_email_body(self):
        """Handle get email body command interactively."""
        email_id = self.get_input("Email ID/UID: ", "")
        if not email_id:
            print("Error: Email ID is required")
            return
        
        await self.get_email_body(email_id)
    
    async def _handle_send_email(self):
        """Handle send email command interactively."""
        print("\nEnter recipient email(s):")
        print("(Press Enter twice to finish)")
        recipients = self.get_email_list("Recipient email: ")
        
        if not recipients:
            print("Error: At least one recipient is required")
            return
        
        subject = self.get_input("Subject: ", "")
        if not subject:
            print("Error: Subject is required")
            return
        
        body = self.get_input("Body: ", "")
        if not body:
            print("Error: Body is required")
            return
        
        print("\nEnter CC recipients (optional):")
        print("(Press Enter twice to finish)")
        cc = self.get_email_list("CC email: ")
        
        print("\nEnter BCC recipients (optional):")
        print("(Press Enter twice to finish)")
        bcc = self.get_email_list("BCC email: ")
        
        html = self.get_choice(
            "Send as HTML? (y/n): ",
            ["y", "n", ""],
            "n"
        ) == "y"
        
        await self.send_email(
            recipients=recipients,
            subject=subject,
            body=body,
            cc=cc if cc else None,
            bcc=bcc if bcc else None,
            html=html,
        )
    
    async def _handle_list_folders(self):
        """Handle list folders command interactively."""
        include_noselect = self.get_choice(
            "Include NOSELECT folders? (y/n): ",
            ["y", "n", ""],
            "y"
        ) == "y"
        
        await self.list_folders(include_noselect=include_noselect)
    
    async def _handle_get_email_count(self):
        """Handle get email count command interactively."""
        before_str = self.get_input("Filter by date before (YYYY-MM-DD): ", "")
        before = self.parse_date(before_str)
        
        since_str = self.get_input("Filter by date since (YYYY-MM-DD): ", "")
        since = self.parse_date(since_str)
        
        subject = self.get_input("Filter by subject: ", "")
        from_address = self.get_input("Filter by sender: ", "")
        to_address = self.get_input("Filter by recipient: ", "")
        
        await self.get_email_count(
            before=before,
            since=since,
            subject=subject,
            from_address=from_address,
            to_address=to_address,
        )
    
    async def _handle_move_email(self):
        """Handle move email command interactively."""
        email_id = self.get_input("Email ID/UID: ", "")
        if not email_id:
            print("Error: Email ID is required")
            return
        
        source_folder = self.get_input("Source folder: ", "")
        if not source_folder:
            print("Error: Source folder is required")
            return
        
        destination_folder = self.get_input("Destination folder: ", "")
        if not destination_folder:
            print("Error: Destination folder is required")
            return
        
        await self.move_email(
            email_id=email_id,
            source_folder=source_folder,
            destination_folder=destination_folder,
        )
    
    async def _handle_delete_email(self):
        """Handle delete email command interactively."""
        email_id = self.get_input("Email ID/UID: ", "")
        if not email_id:
            print("Error: Email ID is required")
            return
        
        folder = self.get_input("Folder (default: INBOX): ", "INBOX")
        
        confirm = self.get_choice(
            "Are you sure you want to delete this email? (y/n): ",
            ["y", "n"],
            "n"
        )
        
        if confirm == "y":
            await self.delete_email(email_id=email_id, folder=folder)
        else:
            print("Deletion cancelled")
    
    async def _handle_mark_email(self):
        """Handle mark email command interactively."""
        email_id = self.get_input("Email ID/UID: ", "")
        if not email_id:
            print("Error: Email ID is required")
            return
        
        folder = self.get_input("Folder (default: INBOX): ", "INBOX")
        
        mark = self.get_choice(
            "Mark type (read/unread/flagged/unflagged/answered/draft): ",
            ["read", "unread", "flagged", "unflagged", "answered", "draft"],
            "read"
        )
        
        await self.mark_email(
            email_id=email_id,
            folder=folder,
            mark=mark,
        )
    
    async def _handle_export_emails(self):
        """Handle export emails command interactively."""
        output = self.get_input("Output file path: ", "emails.json")
        if not output:
            print("Error: Output file path is required")
            return
        
        page_size = self.get_int_input("Emails per page: ", 100)
        max_pages = self.get_int_input("Maximum pages to export: ", 10)
        
        await self.export_emails(
            output=output,
            page_size=page_size,
            max_pages=max_pages,
        )


async def main():
    """Main entry point for the interactive CLI."""
    cli = InteractiveEmailCLI()
    await cli.interactive_loop()


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
