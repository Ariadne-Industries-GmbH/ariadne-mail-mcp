import asyncio
import base64
import email.utils
import mimetypes
import re
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from typing import Any

import aioimaplib
import aiosmtplib

from mcp_email_server.config import EmailServer, EmailSettings, OAuthAccount
from mcp_email_server.emails import EmailHandler
from mcp_email_server.emails.models import (
    AttachmentDownloadResponse,
    EmailBodyResponse,
    EmailContentBatchResponse,
    EmailMetadata,
    EmailMetadataPageResponse,
)
from mcp_email_server.log import logger


def imap_encode(name: str) -> str:
    """Encode a mailbox name to IMAP modified UTF-7 (RFC 3501 §5.1.3)."""
    import base64

    out: list[str] = []
    buf: list[str] = []

    def flush_buf() -> None:
        if not buf:
            return
        raw = "".join(buf).encode("utf-16-be")
        b64 = base64.b64encode(raw).decode("ascii").rstrip("=").replace("/", ",")
        out.append("&" + b64 + "-")
        buf.clear()

    for c in name:
        code = ord(c)
        if c == "&":
            flush_buf()
            out.append("&-")
        elif 0x20 <= code <= 0x7E:
            flush_buf()
            out.append(c)
        else:
            buf.append(c)
    flush_buf()
    return "".join(out)


def _quote_mailbox(name: str) -> str:
    """Encode + quote a mailbox name so it survives IMAP's space-delimited args.

    aioimaplib does not quote arguments itself, so mailbox names containing
    spaces or special characters MUST be quoted by us, or the server will
    interpret the trailing word(s) as separate command arguments. That silent
    failure is the root cause behind move/select going wrong on folders like
    "INBOX.Newsletter.sonstige Newsletter".
    """
    encoded = imap_encode(name)
    escaped = encoded.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _is_ok(result: Any) -> bool:
    """aioimaplib Response.result is a string like 'OK'/'NO'/'BAD'."""
    if result is None:
        return False
    if hasattr(result, "result"):
        return str(result.result).upper() == "OK"
    if isinstance(result, tuple):
        return str(result[0]).upper() == "OK"
    return str(result).upper() == "OK"


def imap_decode(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "&":
            j = s.find("-", i)
            if j == -1:
                # Invalid sequence: keep the raw '&'.
                out.append("&")
                i += 1
                continue
            if j == i + 1:
                # "&-" represents a single '&'.
                out.append("&")
                i = j + 1
                continue
            b64 = s[i + 1 : j]
            # IMAP nutzt eine modifizierte Base64-Variante: ',' statt '/'
            b64 = b64.replace(",", "/")
            # Pad Base64
            pad = "=" * ((4 - (len(b64) % 4)) % 4)
            try:
                import base64

                raw = base64.b64decode(b64 + pad)
                # Big-endian UTF-16
                out.append(raw.decode("utf-16-be"))
            except Exception:
                # Fallback: roher Text
                out.append(s[i : j + 1])
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


_LIST_RE = re.compile(
    r'^\* +LIST +\((?P<flags>[^)]*)\)\s+(?P<delim>NIL|".*?"|[^ ]+)\s+(?P<name>.*)$',
    re.IGNORECASE,
)


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] == '"':
        s = s[1:-1]
        s = s.replace(r"\"", '"')
    return s


class EmailClient:
    def __init__(self, email_server: EmailServer, sender: str | None = None, oauth: OAuthAccount | None = None):
        self.email_server = email_server
        self.oauth = oauth
        self.sender = sender or email_server.user_name

        self.imap_class = aioimaplib.IMAP4_SSL if self.email_server.use_ssl else aioimaplib.IMAP4

        self.smtp_use_tls = self.email_server.use_ssl
        self.smtp_start_tls = self.email_server.start_ssl

    async def login_imap(self, imap: Any, server: EmailServer | None = None) -> None:
        server = server or self.email_server
        if self.oauth:
            from mcp_email_server.oauth import access_token

            if not server.use_ssl:
                raise PermissionError("OAuth requires an encrypted IMAP connection.")
            response = await imap.xoauth2(server.user_name, await access_token(self.oauth))
            if not _is_ok(response):
                raise PermissionError("IMAP sign-in failed. Check the account and IMAP access permission.")
        else:
            response = await imap.login(server.user_name, server.password)
            if not _is_ok(response):
                raise PermissionError("IMAP sign-in failed. Check the credentials.")

    async def login_smtp(self, smtp: Any) -> None:
        if not self.oauth:
            await smtp.login(self.email_server.user_name, self.email_server.password)
            return
        from mcp_email_server.oauth import access_token

        if not (self.smtp_use_tls or self.smtp_start_tls):
            raise PermissionError("OAuth requires an encrypted SMTP connection.")
        await smtp.ehlo()
        token = await access_token(self.oauth)
        encoded = base64.b64encode(f"user={self.email_server.user_name}\x01auth=Bearer {token}\x01\x01".encode())
        response = await smtp.execute_command(b"AUTH", b"XOAUTH2", encoded)
        if response.code == 334:
            await smtp.execute_command(b"")
        if response.code != 235:
            raise PermissionError("SMTP sign-in failed. Check the account and SMTP AUTH permission.")

    async def test_connection(self, protocol: str) -> None:
        """Authenticate only: do not send, mark, move, or fetch any messages."""
        if protocol == "SMTP":
            async with aiosmtplib.SMTP(
                hostname=self.email_server.host,
                port=self.email_server.port,
                use_tls=self.smtp_use_tls,
                start_tls=self.smtp_start_tls,
                timeout=15,
            ) as smtp:
                await self.login_smtp(smtp)
            return
        imap = self.imap_class(host=self.email_server.host, port=self.email_server.port, timeout=15)
        try:
            await imap.wait_hello_from_server()
            await self.login_imap(imap)
        finally:
            try:
                await asyncio.wait_for(imap.logout(), timeout=3)
            except Exception:
                transport = getattr(getattr(imap, "protocol", None), "transport", None)
                if transport:
                    transport.close()

    def _parse_email_data(self, raw_email: bytes, email_id: str | None = None) -> dict[str, Any]:  # noqa: C901
        """Parse raw email data into a structured dictionary."""
        parser = BytesParser(policy=default)
        email_message = parser.parsebytes(raw_email)

        # Extract email parts
        subject = email_message.get("Subject", "")
        sender = email_message.get("From", "")
        date_str = email_message.get("Date", "")

        # Extract Message-ID for reply threading
        message_id = email_message.get("Message-ID")

        # Extract recipients
        to_addresses = []
        to_header = email_message.get("To", "")
        if to_header:
            # Simple parsing - split by comma and strip whitespace
            to_addresses = [addr.strip() for addr in to_header.split(",")]

        # Also check CC recipients
        cc_header = email_message.get("Cc", "")
        if cc_header:
            to_addresses.extend([addr.strip() for addr in cc_header.split(",")])

        # Parse date
        try:
            date_tuple = email.utils.parsedate_tz(date_str)
            date = (
                datetime.fromtimestamp(email.utils.mktime_tz(date_tuple), tz=timezone.utc)
                if date_tuple
                else datetime.now(timezone.utc)
            )
        except Exception:
            date = datetime.now(timezone.utc)

        # Get body content
        body = ""
        attachments = []

        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                # Handle attachments
                if "attachment" in content_disposition:
                    filename = part.get_filename()
                    if filename:
                        attachments.append(filename)
                # Handle text parts
                elif content_type == "text/plain":
                    body_part = part.get_payload(decode=True)
                    if body_part:
                        charset = part.get_content_charset("utf-8")
                        try:
                            body += body_part.decode(charset)
                        except UnicodeDecodeError:
                            body += body_part.decode("utf-8", errors="replace")
        else:
            # Handle plain text emails
            payload = email_message.get_payload(decode=True)
            if payload:
                charset = email_message.get_content_charset("utf-8")
                try:
                    body = payload.decode(charset)
                except UnicodeDecodeError:
                    body = payload.decode("utf-8", errors="replace")
        # TODO: Allow retrieving full email body
        if body and len(body) > 20000:
            body = body[:20000] + "...[TRUNCATED]"
        return {
            "email_id": email_id or "",
            "message_id": message_id,
            "subject": subject,
            "from": sender,
            "to": to_addresses,
            "body": body,
            "date": date,
            "attachments": attachments,
        }

    @staticmethod
    def _build_search_criteria(
        before: datetime | None = None,
        since: datetime | None = None,
        subject: str | None = None,
        body: str | None = None,
        text: str | None = None,
        from_address: str | None = None,
        to_address: str | None = None,
    ):
        search_criteria = []
        if before:
            search_criteria.extend(["BEFORE", before.strftime("%d-%b-%Y").upper()])
        if since:
            search_criteria.extend(["SINCE", since.strftime("%d-%b-%Y").upper()])
        if subject:
            search_criteria.extend(["SUBJECT", subject])
        if body:
            search_criteria.extend(["BODY", body])
        if text:
            search_criteria.extend(["TEXT", text])
        if from_address:
            search_criteria.extend(["FROM", from_address])
        if to_address:
            search_criteria.extend(["TO", to_address])

        # If no specific criteria, search for ALL
        if not search_criteria:
            search_criteria = ["ALL"]

        return search_criteria

    async def get_email_count(
        self,
        before: datetime | None = None,
        since: datetime | None = None,
        subject: str | None = None,
        from_address: str | None = None,
        to_address: str | None = None,
        mailbox: str = "INBOX",
    ) -> int:
        imap = self.imap_class(self.email_server.host, self.email_server.port)
        try:
            # Wait for the connection to be established
            await imap._client_task
            await imap.wait_hello_from_server()

            # Login and select inbox
            await self.login_imap(imap)
            select_result = await imap.select(_quote_mailbox(mailbox))
            if not _is_ok(select_result):
                raise ValueError(f"Cannot select mailbox {mailbox!r}: {select_result}")
            search_criteria = self._build_search_criteria(
                before, since, subject, from_address=from_address, to_address=to_address
            )
            logger.info(f"Count: Search criteria: {search_criteria}")
            # Search for messages and count them - use UID SEARCH for consistency
            _, messages = await imap.uid_search(*search_criteria)
            return len(messages[0].split())
        finally:
            # Ensure we logout properly
            try:
                await imap.logout()
            except Exception as e:
                logger.info(f"Error during logout: {e}")

    async def get_emails_metadata_stream(  # noqa: C901
        self,
        page: int = 1,
        page_size: int = 10,
        before: datetime | None = None,
        since: datetime | None = None,
        subject: str | None = None,
        from_address: str | None = None,
        to_address: str | None = None,
        order: str = "desc",
        mailbox: str = "INBOX",
    ) -> AsyncGenerator[dict[str, Any], None]:
        imap = self.imap_class(self.email_server.host, self.email_server.port)
        try:
            # Wait for the connection to be established
            await imap._client_task
            await imap.wait_hello_from_server()

            # Login and select inbox
            await self.login_imap(imap)
            try:
                await imap.id(name="ariadne-mail-mcp", version="1.0.0")
            except Exception as e:
                logger.warning(f"IMAP ID command failed: {e!s}")
            select_result = await imap.select(_quote_mailbox(mailbox))
            if not _is_ok(select_result):
                raise ValueError(f"Cannot select mailbox {mailbox!r}: {select_result}")

            search_criteria = self._build_search_criteria(
                before, since, subject, from_address=from_address, to_address=to_address
            )
            logger.info(f"Get metadata: Search criteria: {search_criteria}")

            # Search for messages - use UID SEARCH for better compatibility
            _, messages = await imap.uid_search(*search_criteria)

            # Handle empty or None responses
            if not messages or not messages[0]:
                logger.warning("No messages returned from search")
                email_ids = []
            else:
                email_ids = messages[0].split()
                logger.info(f"Found {len(email_ids)} email IDs")
            start = (page - 1) * page_size
            end = start + page_size

            if order == "desc":
                email_ids.reverse()

            # Fetch each message's metadata only
            for _, email_id in enumerate(email_ids[start:end]):
                try:
                    # Convert email_id from bytes to string
                    email_id_str = email_id.decode("utf-8")

                    # Fetch only headers to get metadata without body
                    _, data = await imap.uid("fetch", email_id_str, "BODY.PEEK[HEADER]")

                    if not data:
                        logger.error(f"Failed to fetch headers for UID {email_id_str}")
                        continue

                    # Find the email headers in the response
                    raw_headers = None
                    if len(data) > 1 and isinstance(data[1], bytearray):
                        raw_headers = bytes(data[1])
                    else:
                        # Search through all items for header content
                        for item in data:
                            if isinstance(item, bytes | bytearray) and len(item) > 10:
                                # Skip IMAP protocol responses
                                if isinstance(item, bytes) and b"FETCH" in item:
                                    continue
                                # This is likely the header content
                                raw_headers = bytes(item) if isinstance(item, bytearray) else item
                                break

                    if raw_headers:
                        try:
                            # Parse headers only
                            parser = BytesParser(policy=default)
                            email_message = parser.parsebytes(raw_headers)

                            # Extract metadata
                            subject = email_message.get("Subject", "")
                            sender = email_message.get("From", "")
                            date_str = email_message.get("Date", "")
                            message_id = email_message.get("Message-ID")

                            # Extract recipients
                            to_addresses = []
                            to_header = email_message.get("To", "")
                            if to_header:
                                to_addresses = [addr.strip() for addr in to_header.split(",")]

                            cc_header = email_message.get("Cc", "")
                            if cc_header:
                                to_addresses.extend([addr.strip() for addr in cc_header.split(",")])

                            # Parse date
                            try:
                                date_tuple = email.utils.parsedate_tz(date_str)
                                date = (
                                    datetime.fromtimestamp(email.utils.mktime_tz(date_tuple), tz=timezone.utc)
                                    if date_tuple
                                    else datetime.now(timezone.utc)
                                )
                            except Exception:
                                date = datetime.now(timezone.utc)

                            # For metadata, we don't fetch attachments to save bandwidth
                            # We'll mark it as unknown for now
                            metadata = {
                                "email_id": email_id_str,
                                "message_id": message_id,
                                "subject": subject,
                                "from": sender,
                                "to": to_addresses,
                                "date": date,
                                "attachments": [],  # We don't fetch attachment info for metadata
                            }
                            yield metadata
                        except Exception as e:
                            # Log error but continue with other emails
                            logger.error(f"Error parsing email metadata: {e!s}")
                    else:
                        logger.error(f"Could not find header data in response for email ID: {email_id_str}")
                except Exception as e:
                    logger.error(f"Error fetching email metadata {email_id}: {e!s}")
        finally:
            # Ensure we logout properly
            try:
                await imap.logout()
            except Exception as e:
                logger.info(f"Error during logout: {e}")

    _FETCH_MARKER_RE = re.compile(rb"^\d+\s+FETCH\s*\(", re.IGNORECASE)

    def _has_fetch_marker(self, data: list) -> bool:
        """True if the server actually returned a `<seq> FETCH (...)` response.

        When a UID does not exist in the selected folder, aioimaplib still
        returns the tagged status text (`Completed (0.000 sec)`) as the last
        line. Without this check we would mistake that status line for the
        email body — that's how messages came back with `subject=""`,
        `sender=""`, `body="Completed (0.000 sec)"` after a move.
        """
        return any(isinstance(item, (bytes, bytearray)) and self._FETCH_MARKER_RE.match(bytes(item)) for item in data)

    def _check_email_content(self, data: list) -> bool:
        """Check if the fetched data contains actual email content."""
        if not self._has_fetch_marker(data):
            return False
        return any(isinstance(item, bytearray) and len(item) > 0 for item in data)

    def _extract_raw_email(self, data: list) -> bytes | None:
        """Extract raw email bytes from IMAP response data.

        Only returns payload that *follows* a `<seq> FETCH (...)` marker; the
        trailing tagged status line is never returned as email content.
        """
        seen_fetch = False
        for item in data:
            if isinstance(item, (bytes, bytearray)) and self._FETCH_MARKER_RE.match(bytes(item)):
                seen_fetch = True
                continue
            if not seen_fetch:
                continue
            if isinstance(item, bytearray) and len(item) > 0:
                return bytes(item)
            if isinstance(item, bytes) and len(item) > 0:
                if item == b")" or b"FETCH" in item:
                    continue
                return item
        return None

    async def _fetch_email_with_formats(self, imap, email_id: str) -> list | None:
        """Try different fetch formats to get email data."""
        fetch_formats = ["RFC822", "BODY[]", "BODY.PEEK[]", "(BODY.PEEK[])"]

        for fetch_format in fetch_formats:
            try:
                _, data = await imap.uid("fetch", email_id, fetch_format)

                if data and len(data) > 0 and self._check_email_content(data):
                    return data

            except Exception as e:
                logger.debug(f"Fetch format {fetch_format} failed: {e}")

        return None

    async def get_email_body_by_id(self, email_id: str, mailbox: str = "INBOX") -> dict[str, Any] | None:
        imap = self.imap_class(self.email_server.host, self.email_server.port)
        try:
            # Wait for the connection to be established
            await imap._client_task
            await imap.wait_hello_from_server()

            # Login and select inbox
            await self.login_imap(imap)
            try:
                await imap.id(name="ariadne-mail-mcp", version="1.0.0")
            except Exception as e:
                logger.warning(f"IMAP ID command failed: {e!s}")
            select_result = await imap.select(_quote_mailbox(mailbox))
            if not _is_ok(select_result):
                logger.error(f"Cannot select mailbox {mailbox!r}: {select_result}")
                return None

            # Fetch the specific email by UID
            data = await self._fetch_email_with_formats(imap, email_id)
            if not data:
                logger.error(f"Failed to fetch UID {email_id} with any format")
                return None

            # Extract raw email data
            raw_email = self._extract_raw_email(data)
            if not raw_email:
                logger.error(f"Could not find email data in response for email ID: {email_id}")
                return None

            # Parse the email
            try:
                return self._parse_email_data(raw_email, email_id)
            except Exception as e:
                logger.error(f"Error parsing email: {e!s}")
                return None

        finally:
            # Ensure we logout properly
            try:
                await imap.logout()
            except Exception as e:
                logger.info(f"Error during logout: {e}")

    async def download_attachment(  # noqa: C901
        self,
        email_id: str,
        attachment_name: str,
        save_path: str,
    ) -> dict[str, Any]:
        """Download a specific attachment from an email and save it to disk."""
        imap = self.imap_class(self.email_server.host, self.email_server.port)
        try:
            await imap._client_task
            await imap.wait_hello_from_server()

            await self.login_imap(imap)
            try:
                await imap.id(name="ariadne-mail-mcp", version="1.0.0")
            except Exception as e:
                logger.warning(f"IMAP ID command failed: {e!s}")
            select_result = await imap.select(_quote_mailbox("INBOX"))
            if not _is_ok(select_result):
                raise ValueError(f"Cannot select INBOX: {select_result}")

            data = await self._fetch_email_with_formats(imap, email_id)
            if not data:
                msg = f"Failed to fetch email with UID {email_id}"
                logger.error(msg)
                raise ValueError(msg)

            raw_email = self._extract_raw_email(data)
            if not raw_email:
                msg = f"Could not find email data for email ID: {email_id}"
                logger.error(msg)
                raise ValueError(msg)

            parser = BytesParser(policy=default)
            email_message = parser.parsebytes(raw_email)

            # Find the attachment
            attachment_data = None
            mime_type = None

            if email_message.is_multipart():
                for part in email_message.walk():
                    content_disposition = str(part.get("Content-Disposition", ""))
                    if "attachment" in content_disposition:
                        filename = part.get_filename()
                        if filename == attachment_name:
                            attachment_data = part.get_payload(decode=True)
                            mime_type = part.get_content_type()
                            break

            if attachment_data is None:
                msg = f"Attachment '{attachment_name}' not found in email {email_id}"
                logger.error(msg)
                raise ValueError(msg)

            # Save to disk
            save_file = Path(save_path)
            save_file.parent.mkdir(parents=True, exist_ok=True)
            save_file.write_bytes(attachment_data)

            logger.info(f"Attachment '{attachment_name}' saved to {save_path}")

            return {
                "email_id": email_id,
                "attachment_name": attachment_name,
                "mime_type": mime_type or "application/octet-stream",
                "size": len(attachment_data),
                "saved_path": str(save_file.resolve()),
            }

        finally:
            try:
                await imap.logout()
            except Exception as e:
                logger.info(f"Error during logout: {e}")

    def _validate_attachment(self, file_path: str) -> Path:
        """Validate attachment file path."""
        path = Path(file_path)
        if not path.exists():
            msg = f"Attachment file not found: {file_path}"
            logger.error(msg)
            raise FileNotFoundError(msg)

        if not path.is_file():
            msg = f"Attachment path is not a file: {file_path}"
            logger.error(msg)
            raise ValueError(msg)

        return path

    def _create_attachment_part(self, path: Path) -> MIMEApplication:
        """Create MIME attachment part from file."""
        with open(path, "rb") as f:
            file_data = f.read()

        mime_type, _ = mimetypes.guess_type(str(path))
        if mime_type is None:
            mime_type = "application/octet-stream"

        attachment_part = MIMEApplication(file_data, _subtype=mime_type.split("/")[1])
        attachment_part.add_header(
            "Content-Disposition",
            "attachment",
            filename=path.name,
        )
        logger.info(f"Attached file: {path.name} ({mime_type})")
        return attachment_part

    def _create_message_with_attachments(self, body: str, html: bool, attachments: list[str]) -> MIMEMultipart:
        """Create multipart message with attachments."""
        msg = MIMEMultipart()
        content_type = "html" if html else "plain"
        text_part = MIMEText(body, content_type, "utf-8")
        msg.attach(text_part)

        for file_path in attachments:
            try:
                path = self._validate_attachment(file_path)
                attachment_part = self._create_attachment_part(path)
                msg.attach(attachment_part)
            except Exception as e:
                logger.error(f"Failed to attach file {file_path}: {e}")
                raise

        return msg

    async def send_email(
        self,
        recipients: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        html: bool = False,
        attachments: list[str] | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
    ):
        # Create message with or without attachments
        if attachments:
            msg = self._create_message_with_attachments(body, html, attachments)
        else:
            content_type = "html" if html else "plain"
            msg = MIMEText(body, content_type, "utf-8")

        # Handle subject with special characters
        if any(ord(c) > 127 for c in subject):
            msg["Subject"] = Header(subject, "utf-8")
        else:
            msg["Subject"] = subject

        # Handle sender name with special characters
        if any(ord(c) > 127 for c in self.sender):
            msg["From"] = Header(self.sender, "utf-8")
        else:
            msg["From"] = self.sender

        msg["To"] = ", ".join(recipients)

        # Add CC header if provided (visible to recipients)
        if cc:
            msg["Cc"] = ", ".join(cc)

        # Set threading headers for replies
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references

        # Note: BCC recipients are not added to headers (they remain hidden)
        # but will be included in the actual recipients for SMTP delivery

        async with aiosmtplib.SMTP(
            hostname=self.email_server.host,
            port=self.email_server.port,
            start_tls=self.smtp_start_tls,
            use_tls=self.smtp_use_tls,
        ) as smtp:
            await self.login_smtp(smtp)

            # Create a combined list of all recipients for delivery
            all_recipients = recipients.copy()
            if cc:
                all_recipients.extend(cc)
            if bcc:
                all_recipients.extend(bcc)

            await smtp.send_message(msg, recipients=all_recipients)

        # Return the message for potential saving to Sent folder
        return msg

    async def append_to_sent(
        self,
        msg: MIMEText | MIMEMultipart,
        incoming_server: EmailServer,
        sent_folder_name: str | None = None,
    ) -> bool:
        """Append a sent message to the IMAP Sent folder.

        Args:
            msg: The email message that was sent
            incoming_server: IMAP server configuration for accessing Sent folder
            sent_folder_name: Override folder name, or None for auto-detection

        Returns:
            True if successfully saved, False otherwise
        """
        imap_class = aioimaplib.IMAP4_SSL if incoming_server.use_ssl else aioimaplib.IMAP4
        imap = imap_class(incoming_server.host, incoming_server.port)

        # Common Sent folder names across different providers
        sent_folder_candidates = [
            sent_folder_name,  # User-specified override (if provided)
            "Sent",
            "INBOX.Sent",
            "Sent Items",
            "Sent Mail",
            "[Gmail]/Sent Mail",
            "INBOX/Sent",
        ]
        # Filter out None values
        sent_folder_candidates = [f for f in sent_folder_candidates if f]

        try:
            await imap._client_task
            await imap.wait_hello_from_server()
            await self.login_imap(imap, incoming_server)

            # Try to find and use the Sent folder
            for folder in sent_folder_candidates:
                try:
                    logger.debug(f"Trying Sent folder: '{folder}'")
                    quoted_folder = _quote_mailbox(folder)
                    # Try to select the folder to verify it exists
                    result = await imap.select(quoted_folder)
                    logger.debug(f"Select result for '{folder}': {result}")

                    if _is_ok(result):
                        # Folder exists, append the message
                        msg_bytes = msg.as_bytes()
                        logger.debug(f"Appending message to '{folder}'")
                        # aioimaplib.append signature: (message_bytes, mailbox, flags, date)
                        append_result = await imap.append(
                            msg_bytes,
                            mailbox=quoted_folder,
                            flags=r"(\Seen)",
                        )
                        logger.debug(f"Append result: {append_result}")
                        if _is_ok(append_result):
                            logger.info(f"Saved sent email to '{folder}'")
                            return True
                        else:
                            logger.warning(f"Failed to append to '{folder}': {append_result}")
                    else:
                        logger.debug(f"Folder '{folder}' select returned: {result}")
                except Exception as e:
                    logger.debug(f"Folder '{folder}' not available: {e}")
                    continue

            logger.warning("Could not find a valid Sent folder to save the message")
            return False

        except Exception as e:
            logger.error(f"Error saving to Sent folder: {e}")
            return False
        finally:
            try:
                await imap.logout()
            except Exception as e:
                logger.debug(f"Error during logout: {e}")

    async def delete_emails(self, email_ids: list[str], mailbox: str = "INBOX") -> tuple[list[str], list[str]]:
        """Delete emails by their UIDs. Returns (deleted_ids, failed_ids)."""
        imap = self.imap_class(self.email_server.host, self.email_server.port)
        deleted_ids = []
        failed_ids = []

        try:
            await imap._client_task
            await imap.wait_hello_from_server()
            await self.login_imap(imap)
            select_result = await imap.select(_quote_mailbox(mailbox))
            if not _is_ok(select_result):
                # Fail every requested deletion rather than silently no-op on
                # the wrong mailbox.
                return [], list(email_ids)

            for email_id in email_ids:
                try:
                    await imap.uid("store", email_id, "+FLAGS", r"(\Deleted)")
                    deleted_ids.append(email_id)
                except Exception as e:
                    logger.error(f"Failed to delete email {email_id}: {e}")
                    failed_ids.append(email_id)

            await imap.expunge()
        finally:
            try:
                await imap.logout()
            except Exception as e:
                logger.info(f"Error during logout: {e}")

        return deleted_ids, failed_ids

    async def list_folders(self, include_noselect: bool = True) -> list[str]:
        """Listet alle Ordner-Namen robust (Literals, Quoted, Atom, IMAP-UTF7)."""
        imap = self.imap_class(self.email_server.host, self.email_server.port)
        try:
            await imap._client_task
            await imap.wait_hello_from_server()
            await self.login_imap(imap)

            # Optional: request special-use flags (RFC 6154), depending on the server.
            # Manche Server verstehen: await imap.list("", "*", "RETURN", "(SPECIAL-USE)")
            # Sonst fallback:
            status, data = await imap.list('""', '"*"')
            if status != "OK" or not data:
                return []
            lines = data

            folders: list[str] = []
            i = 0
            while i < len(lines):
                line = lines[i]
                txt = line.decode("utf-8", "replace") if isinstance(line, (bytes, bytearray)) else str(line)

                # Use the final field as the mailbox name.
                # Format ist typischerweise: (<flags>) "<delim>" <name>
                parts = txt.strip().split(" ", 2)
                if len(parts) < 3:
                    # Skip additional status lines.
                    i += 1
                    continue

                name_field = parts[2].strip()

                # Literal {N}: the mailbox name is on the next line.
                lit = re.fullmatch(r"\{(\d+)\}\r?$", name_field)
                if lit:
                    n = int(lit.group(1))
                    next_line = lines[i + 1] if i + 1 < len(lines) else b""
                    if isinstance(next_line, str):
                        next_line = next_line.encode("utf-8", "replace")
                    raw = (next_line or b"")[:n].decode("utf-8", "replace")
                    name = imap_decode(raw)
                    i += 2
                else:
                    # quoted-string oder atom
                    name = imap_decode(_unquote(name_field))
                    i += 1

                # Filter out NOSELECT folders if requested
                if not include_noselect and r"\NOSELECT" in txt:
                    continue

                folders.append(name)

            return folders

        finally:
            try:
                await imap.logout()
            except Exception as e:
                logger.info(f"Error during logout: {e}")

    async def move_email(
        self, email_id: str, source_folder: str, destination_folder: str
    ) -> tuple[bool, str | None, str | None]:
        """Move an email from one folder to another using UID commands.

        Returns (success, new_uid, error_message). The destination UID is
        extracted from the server's COPYUID response (UIDPLUS, RFC 4315) when
        available — needed because the email gets a fresh UID in the
        destination and the source UID becomes meaningless there.

        IMPORTANT: only proceeds to STORE+EXPUNGE if both SELECT and COPY
        report OK. Earlier versions silently deleted the source even when
        COPY failed (e.g. destination folder did not exist, or its name
        contained spaces), causing real data loss.
        """
        imap = self.imap_class(self.email_server.host, self.email_server.port)
        try:
            await imap._client_task
            await imap.wait_hello_from_server()
            await self.login_imap(imap)

            select_result = await imap.select(_quote_mailbox(source_folder))
            if not _is_ok(select_result):
                msg = f"Source folder {source_folder!r} could not be selected: {select_result}"
                logger.error(msg)
                return False, None, msg

            copy_result = await imap.uid("COPY", email_id, _quote_mailbox(destination_folder))
            if not _is_ok(copy_result):
                msg = f"COPY to {destination_folder!r} failed: {copy_result}. Source email left intact."
                logger.error(msg)
                return False, None, msg

            new_uid = self._extract_copyuid(copy_result, email_id)

            # Only now is it safe to delete the source copy.
            store_result = await imap.uid("STORE", email_id, "+FLAGS", "(\\Deleted)")
            if not _is_ok(store_result):
                msg = (
                    f"STORE \\Deleted on source UID {email_id} failed: {store_result}. "
                    f"A copy now exists in {destination_folder!r} (UID {new_uid or 'unknown'}) "
                    "but the source was not removed."
                )
                logger.error(msg)
                return False, new_uid, msg

            await imap.expunge()
            return True, new_uid, None
        except Exception as e:
            logger.error(f"Error moving email: {e!s}")
            return False, None, str(e)
        finally:
            try:
                await imap.logout()
            except Exception as e:
                logger.info(f"Error during logout: {e}")

    @staticmethod
    def _extract_copyuid(copy_result: Any, source_uid: str) -> str | None:
        """Pull the new destination UID out of a COPYUID response (UIDPLUS).

        Server replies look like:
          A123 OK [COPYUID <uidvalidity> <src-uid-set> <dst-uid-set>] Completed
        We only ever copy a single UID, so the destination set is a single UID.
        Returns None if the server does not support UIDPLUS or the response
        cannot be parsed.
        """
        candidates: list[bytes | str] = []
        lines = getattr(copy_result, "lines", None)
        if lines:
            candidates.extend(lines)
        if isinstance(copy_result, tuple) and len(copy_result) > 1:
            payload = copy_result[1]
            if isinstance(payload, (list, tuple)):
                candidates.extend(payload)
            else:
                candidates.append(payload)

        for line in candidates:
            text = line.decode("utf-8", "replace") if isinstance(line, (bytes, bytearray)) else str(line)
            match = re.search(r"COPYUID\s+\d+\s+(\S+)\s+(\S+)", text, re.IGNORECASE)
            if match:
                dst_set = match.group(2).rstrip("]")
                # Single-UID copy → just take the first token of the set.
                first = dst_set.split(",", 1)[0].split(":", 1)[0]
                if first.isdigit():
                    return first
        return None

    async def set_flag(self, email_id: str, folder: str, flag: str, add: bool) -> bool:
        """Add or remove an IMAP flag on a message using UID commands."""
        imap = self.imap_class(self.email_server.host, self.email_server.port)
        try:
            await imap._client_task
            await imap.wait_hello_from_server()
            await self.login_imap(imap)
            select_result = await imap.select(_quote_mailbox(folder))
            if not _is_ok(select_result):
                logger.error(f"Cannot select folder {folder!r}: {select_result}")
                return False
            try:
                await imap.uid("STORE", email_id, "+FLAGS" if add else "-FLAGS", flag)
                return True
            except Exception as e:
                logger.error(f"Error setting flag {flag} (add={add}) on {email_id}: {e!s}")
                return False
        finally:
            try:
                await imap.logout()
            except Exception as e:
                logger.info(f"Error during logout: {e}")


class ClassicEmailHandler(EmailHandler):
    def __init__(self, email_settings: EmailSettings):
        self.email_settings = email_settings
        self.incoming_client = EmailClient(email_settings.incoming, oauth=email_settings.oauth)
        self.outgoing_client = EmailClient(
            email_settings.outgoing,
            sender=f"{email_settings.full_name} <{email_settings.email_address}>",
            oauth=email_settings.oauth,
        )
        self.save_to_sent = email_settings.save_to_sent
        self.sent_folder_name = email_settings.sent_folder_name

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
        mailbox: str = "INBOX",
    ) -> EmailMetadataPageResponse:
        emails = []
        async for email_data in self.incoming_client.get_emails_metadata_stream(
            page, page_size, before, since, subject, from_address, to_address, order, mailbox
        ):
            emails.append(EmailMetadata.from_email(email_data))
        total = await self.incoming_client.get_email_count(
            before, since, subject, from_address=from_address, to_address=to_address, mailbox=mailbox
        )
        return EmailMetadataPageResponse(
            page=page,
            page_size=page_size,
            before=before,
            since=since,
            subject=subject,
            emails=emails,
            total=total,
        )

    async def get_emails_content(self, email_ids: list[str], mailbox: str = "INBOX") -> EmailContentBatchResponse:
        """Batch retrieve email body content"""
        emails = []
        failed_ids = []

        for email_id in email_ids:
            try:
                email_data = await self.incoming_client.get_email_body_by_id(email_id, mailbox)
                if email_data:
                    emails.append(
                        EmailBodyResponse(
                            email_id=email_data["email_id"],
                            message_id=email_data.get("message_id"),
                            subject=email_data["subject"],
                            sender=email_data["from"],
                            recipients=email_data["to"],
                            date=email_data["date"],
                            body=email_data["body"],
                            attachments=email_data["attachments"],
                        )
                    )
                else:
                    failed_ids.append(email_id)
            except Exception as e:
                logger.error(f"Failed to retrieve email {email_id}: {e}")
                failed_ids.append(email_id)

        return EmailContentBatchResponse(
            emails=emails,
            requested_count=len(email_ids),
            retrieved_count=len(emails),
            failed_ids=failed_ids,
        )

    async def list_folders(self) -> list[str]:
        """List all folders in the mail account."""
        return await self.incoming_client.list_folders()

    async def move_email(
        self, email_id: str, source_folder: str, destination_folder: str
    ) -> tuple[bool, str | None, str | None]:
        """Move an email from one folder to another.

        Returns (success, new_uid_in_destination, error_message).
        """
        return await self.incoming_client.move_email(email_id, source_folder, destination_folder)

    async def get_full_email_body(self, email_id: str, folder: str = "INBOX") -> str:
        """Convenience wrapper to fetch only the body by IMAP UID (email_id)."""
        try:
            email_data = await self.incoming_client.get_email_body_by_id(email_id, folder)
            if not email_data:
                logger.error(f"Could not fetch email body for UID: {email_id}")
                return ""
            return email_data.get("body", "")
        except Exception as e:
            logger.error(f"Error fetching full email body for UID {email_id}: {e!s}")
            return ""

    async def mark_email(self, email_id: str, folder: str = "INBOX", mark: str = "read") -> bool:
        r"""Mark an email with common IMAP flags.

        mark options:
        - read/unread -> \Seen add/remove
        - flagged/unflagged -> \Flagged add/remove
        - answered -> \Answered add
        - draft -> \Draft add
        """
        mapping = {
            "read": ("\\Seen", True),
            "unread": ("\\Seen", False),
            "flagged": ("\\Flagged", True),
            "unflagged": ("\\Flagged", False),
            "answered": ("\\Answered", True),
            "unanswered": ("\\Answered", False),
            "draft": ("\\Draft", True),
        }
        flag, add = mapping.get(mark, ("\\Seen", True))
        return await self.incoming_client.set_flag(email_id, folder, f"({flag})", add)

    async def delete_emails(self, email_ids: list[str], mailbox: str = "INBOX") -> tuple[list[str], list[str]]:
        """Delete emails by their IDs. Returns (deleted_ids, failed_ids)."""
        return await self.incoming_client.delete_emails(email_ids, mailbox)

    async def send_email(
        self,
        recipients: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        html: bool = False,
        attachments: list[str] | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> None:
        """Send an email."""
        msg = await self.outgoing_client.send_email(
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

        # Save to Sent folder if enabled
        if self.save_to_sent and msg:
            await self.outgoing_client.append_to_sent(
                msg,
                self.email_settings.incoming,
                self.sent_folder_name,
            )

    async def download_attachment(
        self,
        email_id: str,
        attachment_name: str,
        save_path: str,
    ) -> "AttachmentDownloadResponse":
        """Download an email attachment and save it to the specified path."""
        result = await self.incoming_client.download_attachment(
            email_id,
            attachment_name,
            save_path,
        )
        return AttachmentDownloadResponse(**result)
