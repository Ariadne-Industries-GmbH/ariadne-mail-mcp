from datetime import datetime
from typing import Any

from pydantic import BaseModel

class EmailData(BaseModel):
    subject: str
    sender: str
    body: str
    date: datetime
    attachments: list[str]

    @classmethod
    def from_email(cls, email: dict[str, Any]):
        return cls(
            subject=email["subject"],
            sender=email["from"],
            body=email["body"],
            date=email["date"],
            attachments=email["attachments"],
        )

    def to_preview(self):
        max_length = 200
        truncated_body = self.body[:max_length] + "..." if len(self.body) > max_length else self.body
        return EmailData(
            subject=self.subject,
            sender=self.sender,
            body=truncated_body,
            date=self.date,
            attachments=self.attachments,
        )

class EmailPageResponse(BaseModel):
    page: int
    page_size: int
    before: datetime | None
    since: datetime | None
    subject: str | None
    body: str | None
    text: str | None
    emails: list[EmailData]
    total: int
