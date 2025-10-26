import abc
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp_email_server.emails.models import EmailContentBatchResponse, EmailMetadataPageResponse

class EmailHandler(abc.ABC):
    @abc.abstractmethod
    async def get_emails_metadata(
        self,
        page: int = 1,
        page_size: int = 10,
        before: datetime | None = None,
        since: datetime | None = None,
        subject: str | None = None,
        from_address: str | None = None,
        to_address: str | None = None,
        order: str = "desc",
    ) -> "EmailMetadataPageResponse":
        """
        Get email metadata only (without body content) for better performance
        """

    @abc.abstractmethod
    async def get_emails_content(self, email_ids: list[str]) -> "EmailContentBatchResponse":
        """
        Get full content (including body) of multiple emails by their email IDs (IMAP UIDs)
        """

    @abc.abstractmethod
    async def send_email(
        self,
        recipients: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        html: bool = False,
    ) -> None:
        """
        Send email
        """

    @abc.abstractmethod
    async def list_folders(self) -> list[str]:
        """List all folders in the mail account."""

    @abc.abstractmethod
    async def move_email(self, message_id: str, source_folder: str, destination_folder: str) -> bool:
        """Move an email from one folder to another."""

    @abc.abstractmethod
    async def delete_email(self, message_id: str, folder: str = "INBOX") -> bool:
        """Move an email to the trash (delete an email)."""

    @abc.abstractmethod
    async def get_full_email_body(self, message_id: str, folder: str = "INBOX") -> str:
        """Fetch the full body of an email."""

    @abc.abstractmethod
    async def mark_email(self, message_id: str, folder: str = "INBOX", mark: str = "read") -> bool:
        """Mark an email (read/unread/flagged/unflagged/answered/draft)."""
