from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_email_server.app import (
    add_email_account,
    delete_emails,
    download_attachment,
    get_allowed_recipients,
    get_emails_content,
    get_full_email_body,
    list_available_accounts,
    list_emails_metadata,
    list_folders,
    mark_email,
    move_email,
    send_email,
    send_email_to_allowed_recipients,
)
from mcp_email_server.config import AiSendsEmailToolSettings, EmailServer, EmailSettings, ProviderSettings
from mcp_email_server.emails.models import (
    AttachmentDownloadResponse,
    EmailBodyResponse,
    EmailContentBatchResponse,
    EmailMetadata,
    EmailMetadataPageResponse,
)


class TestMcpTools:
    @pytest.mark.asyncio
    async def test_list_available_accounts(self):
        """Test list_available_accounts MCP tool."""
        # Create test accounts
        email_settings = EmailSettings(
            account_name="test_email",
            full_name="Test User",
            email_address="test@example.com",
            incoming=EmailServer(
                user_name="test_user",
                password="test_password",
                host="imap.example.com",
                port=993,
                use_ssl=True,
            ),
            outgoing=EmailServer(
                user_name="test_user",
                password="test_password",
                host="smtp.example.com",
                port=465,
                use_ssl=True,
            ),
        )

        provider_settings = ProviderSettings(
            account_name="test_provider",
            provider_name="test",
            api_key="test_key",
        )

        # Mock the get_settings function
        mock_settings = MagicMock()
        mock_settings.get_accounts.return_value = [email_settings, provider_settings]

        with patch("mcp_email_server.app.get_settings", return_value=mock_settings):
            # Call the function
            result = await list_available_accounts()

            # Verify the result
            assert len(result) == 2
            assert result[0].account_name == "test_email"
            assert result[1].account_name == "test_provider"

            # Verify get_accounts was called correctly
            mock_settings.get_accounts.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_email_account(self):
        """Test add_email_account MCP tool."""
        # Create test email settings
        email_settings = EmailSettings(
            account_name="test_account",
            full_name="Test User",
            email_address="test@example.com",
            incoming=EmailServer(
                user_name="test_user",
                password="test_password",
                host="imap.example.com",
                port=993,
                use_ssl=True,
            ),
            outgoing=EmailServer(
                user_name="test_user",
                password="test_password",
                host="smtp.example.com",
                port=465,
                use_ssl=True,
            ),
        )

        # Mock the get_settings function
        mock_settings = MagicMock()

        with patch("mcp_email_server.app.get_settings", return_value=mock_settings):
            # Call the function
            result = await add_email_account(email_settings)

            # Verify the return value
            assert result == "Successfully added email account 'test_account'"

            # Verify add_email and store were called correctly
            mock_settings.add_email.assert_called_once_with(email_settings)
            mock_settings.store.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_emails_metadata(self):
        """Test list_emails_metadata MCP tool."""
        # Create test data
        now = datetime.now(timezone.utc)
        email_metadata = EmailMetadata(
            email_id="12345",
            subject="Test Subject",
            sender="sender@example.com",
            recipients=["recipient@example.com"],
            date=now,
            attachments=[],
        )

        email_metadata_page = EmailMetadataPageResponse(
            page=1,
            page_size=10,
            before=now,
            since=None,
            subject="Test",
            emails=[email_metadata],
            total=1,
        )

        # Mock the dispatch_handler function
        mock_handler = AsyncMock()
        mock_handler.get_emails_metadata.return_value = email_metadata_page

        with patch("mcp_email_server.app.dispatch_handler", return_value=mock_handler):
            # Call the function
            result = await list_emails_metadata(
                account_name="test_account",
                page=1,
                page_size=10,
                before=now,
                since=None,
                subject="Test",
                from_address="sender@example.com",
                to_address=None,
            )

            # Verify the result
            assert result == email_metadata_page
            assert result.page == 1
            assert result.page_size == 10
            assert result.before == now
            assert result.subject == "Test"
            assert len(result.emails) == 1
            assert result.emails[0].subject == "Test Subject"

            # Verify dispatch_handler and get_emails_metadata were called correctly
            mock_handler.get_emails_metadata.assert_called_once_with(
                page=1,
                page_size=10,
                before=now,
                since=None,
                subject="Test",
                from_address="sender@example.com",
                to_address=None,
                order="desc",
                mailbox="INBOX",
            )

    @pytest.mark.asyncio
    async def test_list_emails_metadata_with_mailbox(self):
        """Test list_emails_metadata MCP tool with custom mailbox."""
        now = datetime.now(timezone.utc)
        email_metadata = EmailMetadata(
            email_id="12345",
            subject="Sent Subject",
            sender="me@example.com",
            recipients=["recipient@example.com"],
            date=now,
            attachments=[],
        )

        email_metadata_page = EmailMetadataPageResponse(
            page=1,
            page_size=10,
            before=None,
            since=None,
            subject=None,
            emails=[email_metadata],
            total=1,
        )

        mock_handler = AsyncMock()
        mock_handler.get_emails_metadata.return_value = email_metadata_page

        with patch("mcp_email_server.app.dispatch_handler", return_value=mock_handler):
            result = await list_emails_metadata(
                account_name="test_account",
                mailbox="Sent",
            )

            assert result == email_metadata_page
            mock_handler.get_emails_metadata.assert_called_once_with(
                page=1,
                page_size=10,
                before=None,
                since=None,
                subject=None,
                from_address=None,
                to_address=None,
                order="desc",
                mailbox="Sent",
            )

    @pytest.mark.asyncio
    async def test_get_emails_content_single(self):
        """Test get_emails_content MCP tool with single email."""
        # Create test data
        now = datetime.now(timezone.utc)
        email_body = EmailBodyResponse(
            email_id="12345",
            subject="Test Subject",
            sender="sender@example.com",
            recipients=["recipient@example.com"],
            date=now,
            body="This is the test email body content.",
            attachments=["attachment1.pdf"],
        )

        batch_response = EmailContentBatchResponse(
            emails=[email_body],
            requested_count=1,
            retrieved_count=1,
            failed_ids=[],
        )

        # Mock the dispatch_handler function
        mock_handler = AsyncMock()
        mock_handler.get_emails_content.return_value = batch_response

        with patch("mcp_email_server.app.dispatch_handler", return_value=mock_handler):
            # Call the function
            result = await get_emails_content(
                account_name="test_account",
                email_ids=["12345"],
            )

            # Verify the result
            assert result == batch_response
            assert result.requested_count == 1
            assert result.retrieved_count == 1
            assert len(result.failed_ids) == 0
            assert len(result.emails) == 1
            assert result.emails[0].email_id == "12345"
            assert result.emails[0].subject == "Test Subject"

            # Verify dispatch_handler and get_emails_content were called correctly
            mock_handler.get_emails_content.assert_called_once_with(["12345"], "INBOX")

    @pytest.mark.asyncio
    async def test_get_emails_content_batch(self):
        """Test get_emails_content MCP tool with multiple emails."""
        # Create test data
        now = datetime.now(timezone.utc)
        email1 = EmailBodyResponse(
            email_id="12345",
            subject="Test Subject 1",
            sender="sender1@example.com",
            recipients=["recipient@example.com"],
            date=now,
            body="This is the first test email body content.",
            attachments=[],
        )

        email2 = EmailBodyResponse(
            email_id="12346",
            subject="Test Subject 2",
            sender="sender2@example.com",
            recipients=["recipient@example.com"],
            date=now,
            body="This is the second test email body content.",
            attachments=["attachment1.pdf"],
        )

        batch_response = EmailContentBatchResponse(
            emails=[email1, email2],
            requested_count=3,
            retrieved_count=2,
            failed_ids=["12347"],
        )

        # Mock the dispatch_handler function
        mock_handler = AsyncMock()
        mock_handler.get_emails_content.return_value = batch_response

        with patch("mcp_email_server.app.dispatch_handler", return_value=mock_handler):
            # Call the function
            result = await get_emails_content(
                account_name="test_account",
                email_ids=["12345", "12346", "12347"],
            )

            # Verify the result
            assert result == batch_response
            assert result.requested_count == 3
            assert result.retrieved_count == 2
            assert len(result.failed_ids) == 1
            assert result.failed_ids[0] == "12347"
            assert len(result.emails) == 2
            assert result.emails[0].email_id == "12345"
            assert result.emails[1].email_id == "12346"

            # Verify dispatch_handler and get_emails_content were called correctly
            mock_handler.get_emails_content.assert_called_once_with(["12345", "12346", "12347"], "INBOX")

    @pytest.mark.asyncio
    async def test_get_emails_content_with_mailbox(self):
        """Test get_emails_content MCP tool with custom mailbox."""
        now = datetime.now(timezone.utc)
        email_body = EmailBodyResponse(
            email_id="12345",
            subject="Sent Subject",
            sender="me@example.com",
            recipients=["recipient@example.com"],
            date=now,
            body="This is a sent email.",
            attachments=[],
        )

        batch_response = EmailContentBatchResponse(
            emails=[email_body],
            requested_count=1,
            retrieved_count=1,
            failed_ids=[],
        )

        mock_handler = AsyncMock()
        mock_handler.get_emails_content.return_value = batch_response

        with patch("mcp_email_server.app.dispatch_handler", return_value=mock_handler):
            result = await get_emails_content(
                account_name="test_account",
                email_ids=["12345"],
                mailbox="Sent",
            )

            assert result == batch_response
            mock_handler.get_emails_content.assert_called_once_with(["12345"], "Sent")

    @pytest.mark.asyncio
    async def test_send_email(self):
        """Test send_email MCP tool."""
        # Mock the dispatch_handler function
        mock_handler = AsyncMock()

        # Enable email sending for the test
        with (
            patch("mcp_email_server.app.dispatch_handler", return_value=mock_handler),
            patch.dict("os.environ", {"MCP_EMAIL_SERVER_ENABLE_SENDING": "1"}),
        ):
            # Call the function
            result = await send_email(
                account_name="test_account",
                recipients=["recipient@example.com"],
                subject="Test Subject",
                body="Test Body",
                cc=["cc@example.com"],
                bcc=["bcc@example.com"],
            )

            # Verify the return value
            assert result == "Email sent successfully to recipient@example.com"

            # Verify send_email was called correctly
            mock_handler.send_email.assert_called_once_with(
                ["recipient@example.com"],
                "Test Subject",
                "Test Body",
                ["cc@example.com"],
                ["bcc@example.com"],
                False,
                None,
                None,
                None,
            )

    @pytest.mark.asyncio
    async def test_get_allowed_recipients_empty(self):
        mock_settings = MagicMock()
        mock_settings.ai_sends_email_tool = AiSendsEmailToolSettings(allowed_account_name="work", allowed_recipients=[])

        with patch("mcp_email_server.app.get_settings", return_value=mock_settings):
            result = await get_allowed_recipients()

            assert result == {"allowed_recipients": [], "error": "No allowed recipients configured."}

    @pytest.mark.asyncio
    async def test_get_allowed_recipients_success(self):
        mock_settings = MagicMock()
        mock_settings.ai_sends_email_tool = AiSendsEmailToolSettings(
            allowed_account_name="work",
            allowed_recipients=["allowed@example.com", "second@example.com"],
        )

        with patch("mcp_email_server.app.get_settings", return_value=mock_settings):
            result = await get_allowed_recipients()

            assert result == {
                "allowed_recipients": ["allowed@example.com", "second@example.com"],
                "error": None,
            }

    @pytest.mark.asyncio
    async def test_send_email_to_allowed_recipients_no_account(self):
        mock_settings = MagicMock()
        mock_settings.ai_sends_email_tool = AiSendsEmailToolSettings(allowed_account_name=None, allowed_recipients=[])

        with patch("mcp_email_server.app.get_settings", return_value=mock_settings):
            result = await send_email_to_allowed_recipients(
                to=["allowed@example.com"],
                subject="Test",
                body="Body",
            )

            assert result == {"success": False, "error": "No email account configured for this tool."}

    @pytest.mark.asyncio
    async def test_send_email_to_allowed_recipients_no_recipients(self):
        mock_settings = MagicMock()
        mock_settings.ai_sends_email_tool = AiSendsEmailToolSettings(
            allowed_account_name="work",
            allowed_recipients=["allowed@example.com"],
        )

        with patch("mcp_email_server.app.get_settings", return_value=mock_settings):
            result = await send_email_to_allowed_recipients(
                to=[],
                subject="Test",
                body="Body",
            )

            assert result == {"success": False, "error": "No recipients provided."}

    @pytest.mark.asyncio
    async def test_send_email_to_allowed_recipients_invalid_and_disallowed(self):
        mock_settings = MagicMock()
        mock_settings.ai_sends_email_tool = AiSendsEmailToolSettings(
            allowed_account_name="work",
            allowed_recipients=["allowed@example.com"],
        )

        with patch("mcp_email_server.app.get_settings", return_value=mock_settings):
            result = await send_email_to_allowed_recipients(
                to=["invalid-email", "not-allowed@example.com"],
                subject="Test",
                body="Body",
            )

            assert result["success"] is False
            assert "Invalid email address format." in result["error"]
            assert "Recipient(s) not in allowed list." in result["error"]

    @pytest.mark.asyncio
    async def test_send_email_to_allowed_recipients_success(self):
        mock_settings = MagicMock()
        mock_settings.ai_sends_email_tool = AiSendsEmailToolSettings(
            allowed_account_name="work",
            allowed_recipients=["allowed@example.com"],
        )
        configured_account = EmailSettings(
            account_name="work",
            full_name="Test User",
            email_address="test@example.com",
            incoming=EmailServer(
                user_name="test_user",
                password="test_password",
                host="imap.example.com",
                port=993,
                use_ssl=True,
            ),
            outgoing=EmailServer(
                user_name="test_user",
                password="test_password",
                host="smtp.example.com",
                port=465,
                use_ssl=True,
            ),
        )
        mock_settings.get_account.return_value = configured_account
        mock_handler = AsyncMock()

        with patch("mcp_email_server.app.get_settings", return_value=mock_settings):
            with patch("mcp_email_server.app.dispatch_handler", return_value=mock_handler):
                result = await send_email_to_allowed_recipients(
                    to=["ALLOWED@example.com", "allowed@example.com"],
                    subject="Test",
                    body="Body",
                )

                assert result == {
                    "success": True,
                    "message": "Email sent successfully",
                    "sent_to": ["allowed@example.com"],
                }
                mock_handler.send_email.assert_called_once_with(
                    ["allowed@example.com"],
                    "Test",
                    "Body",
                    None,
                    None,
                    False,
                    None,
                    None,
                    None,
                )

    @pytest.mark.asyncio
    async def test_send_email_to_allowed_recipients_missing_configured_account_auto_clears(self):
        mock_settings = MagicMock()
        mock_settings.ai_sends_email_tool = AiSendsEmailToolSettings(
            allowed_account_name="missing",
            allowed_recipients=["allowed@example.com"],
        )
        mock_settings.get_account.return_value = None

        with patch("mcp_email_server.app.get_settings", return_value=mock_settings):
            result = await send_email_to_allowed_recipients(
                to=["allowed@example.com"],
                subject="Test",
                body="Body",
            )

            assert result == {"success": False, "error": "No email account configured for this tool."}
            assert mock_settings.ai_sends_email_tool.allowed_account_name is None
            assert mock_settings.ai_sends_email_tool.allowed_recipients == []
            mock_settings.store.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_folders(self):
        """Test list_folders MCP tool."""
        # Mock the dispatch_handler function
        mock_handler = AsyncMock()
        mock_handler.list_folders.return_value = ["INBOX", "SENT", "DRAFT", "ARCHIVE"]

        with patch("mcp_email_server.app.dispatch_handler", return_value=mock_handler):
            # Call the function
            result = await list_folders(account_name="test_account")

            # Verify the result
            assert result == ["INBOX", "SENT", "DRAFT", "ARCHIVE"]

            # Verify list_folders was called correctly
            mock_handler.list_folders.assert_called_once()

    @pytest.mark.asyncio
    async def test_move_email(self):
        """Test move_email MCP tool."""
        # Mock the dispatch_handler function
        mock_handler = AsyncMock()
        mock_handler.move_email.return_value = (True, "67890", None)

        with patch("mcp_email_server.app.dispatch_handler", return_value=mock_handler):
            # Call the function
            result = await move_email(
                account_name="test_account",
                email_id="12345",
                source_folder="INBOX",
                destination_folder="ARCHIVE",
            )

            # Verify the result
            assert result["success"] is True
            assert result["new_email_id"] == "67890"
            assert result["previous_email_id"] == "12345"
            assert result["destination_folder"] == "ARCHIVE"

            # Verify move_email was called correctly
            mock_handler.move_email.assert_called_once_with(
                "12345",
                "INBOX",
                "ARCHIVE",
            )

    @pytest.mark.asyncio
    async def test_delete_email(self):
        """Test delete_email MCP tool."""
        # Mock the dispatch_handler function
        mock_handler = AsyncMock()
        mock_handler.delete_emails.return_value = (["12345"], [])

        with patch("mcp_email_server.app.dispatch_handler", return_value=mock_handler):
            # Call the function
            result = await delete_emails(
                account_name="test_account",
                email_ids=["12345"],
                mailbox="INBOX",
            )

            # Verify the result
            assert "Successfully deleted 1 email(s)" in result

            # Verify delete_emails was called correctly
            mock_handler.delete_emails.assert_called_once_with(
                ["12345"],
                "INBOX",
            )

    @pytest.mark.asyncio
    async def test_get_full_email_body(self):
        """Test get_full_email_body MCP tool."""
        # Mock the dispatch_handler function
        mock_handler = AsyncMock()
        mock_handler.get_full_email_body.return_value = "This is the full email body content."

        with patch("mcp_email_server.app.dispatch_handler", return_value=mock_handler):
            # Call the function
            result = await get_full_email_body(
                account_name="test_account",
                email_id="12345",
                folder="INBOX",
            )

            # Verify the result
            assert result == "This is the full email body content."

            # Verify get_full_email_body was called correctly
            mock_handler.get_full_email_body.assert_called_once_with(
                "12345",
                "INBOX",
            )

    @pytest.mark.asyncio
    async def test_mark_email(self):
        """Test mark_email MCP tool."""
        # Mock the dispatch_handler function
        mock_handler = AsyncMock()
        mock_handler.mark_email.return_value = True

        with patch("mcp_email_server.app.dispatch_handler", return_value=mock_handler):
            # Call the function
            result = await mark_email(
                account_name="test_account",
                email_id="12345",
                folder="INBOX",
                mark="read",
            )

            # Verify the result
            assert result is True

            # Verify mark_email was called correctly
            mock_handler.mark_email.assert_called_once_with(
                "12345",
                "INBOX",
                "read",
            )

    @pytest.mark.asyncio
    async def test_delete_emails(self):
        """Test delete_emails MCP tool."""
        mock_handler = AsyncMock()
        mock_handler.delete_emails.return_value = (["12345", "12346"], [])

        with patch("mcp_email_server.app.dispatch_handler", return_value=mock_handler):
            result = await delete_emails(
                account_name="test_account",
                email_ids=["12345", "12346"],
            )

            assert result == "Successfully deleted 2 email(s)"
            mock_handler.delete_emails.assert_called_once_with(["12345", "12346"], "INBOX")

    @pytest.mark.asyncio
    async def test_delete_emails_with_failures(self):
        """Test delete_emails MCP tool with some failures."""
        mock_handler = AsyncMock()
        mock_handler.delete_emails.return_value = (["12345"], ["12346", "12347"])

        with patch("mcp_email_server.app.dispatch_handler", return_value=mock_handler):
            result = await delete_emails(
                account_name="test_account",
                email_ids=["12345", "12346", "12347"],
            )

            assert result == "Successfully deleted 1 email(s), failed to delete 2 email(s): 12346, 12347"
            mock_handler.delete_emails.assert_called_once_with(["12345", "12346", "12347"], "INBOX")

    @pytest.mark.asyncio
    async def test_delete_emails_with_mailbox(self):
        """Test delete_emails MCP tool with custom mailbox."""
        mock_handler = AsyncMock()
        mock_handler.delete_emails.return_value = (["12345"], [])

        with patch("mcp_email_server.app.dispatch_handler", return_value=mock_handler):
            result = await delete_emails(
                account_name="test_account",
                email_ids=["12345"],
                mailbox="Trash",
            )

            assert result == "Successfully deleted 1 email(s)"
            mock_handler.delete_emails.assert_called_once_with(["12345"], "Trash")

    @pytest.mark.asyncio
    async def test_download_attachment_disabled(self):
        """Test download_attachment MCP tool when feature is disabled."""
        mock_settings = MagicMock()
        mock_settings.enable_attachment_download = False

        with patch("mcp_email_server.app.get_settings", return_value=mock_settings):
            with pytest.raises(PermissionError) as exc_info:
                await download_attachment(
                    account_name="test_account",
                    email_id="12345",
                    attachment_name="document.pdf",
                    save_path="/var/downloads/document.pdf",
                )

            assert "Attachment download is disabled" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_download_attachment_enabled(self):
        """Test download_attachment MCP tool when feature is enabled."""
        attachment_response = AttachmentDownloadResponse(
            email_id="12345",
            attachment_name="document.pdf",
            mime_type="application/pdf",
            size=1024,
            saved_path="/var/downloads/document.pdf",
        )

        mock_settings = MagicMock()
        mock_settings.enable_attachment_download = True

        mock_handler = AsyncMock()
        mock_handler.download_attachment.return_value = attachment_response

        with patch("mcp_email_server.app.get_settings", return_value=mock_settings):
            with patch("mcp_email_server.app.dispatch_handler", return_value=mock_handler):
                result = await download_attachment(
                    account_name="test_account",
                    email_id="12345",
                    attachment_name="document.pdf",
                    save_path="/var/downloads/document.pdf",
                )

                assert result == attachment_response
                assert result.email_id == "12345"
                assert result.attachment_name == "document.pdf"
                assert result.mime_type == "application/pdf"
                assert result.size == 1024

                mock_handler.download_attachment.assert_called_once_with(
                    "12345", "document.pdf", "/var/downloads/document.pdf"
                )

    @pytest.mark.asyncio
    async def test_send_email_with_reply_headers(self):
        """Test send_email MCP tool with reply headers."""
        mock_handler = AsyncMock()
        mock_handler.send_email = AsyncMock()

        with (
            patch("mcp_email_server.app.dispatch_handler", return_value=mock_handler),
            patch.dict("os.environ", {"MCP_EMAIL_SERVER_ENABLE_SENDING": "1"}),
        ):
            result = await send_email(
                account_name="test",
                recipients=["recipient@example.com"],
                subject="Re: Test",
                body="Reply body",
                in_reply_to="<original@example.com>",
                references="<original@example.com>",
            )

            mock_handler.send_email.assert_called_once()
            call_args = mock_handler.send_email.call_args
            # Verify in_reply_to and references were passed (positions 7 and 8 after cc, bcc, html, attachments)
            assert "<original@example.com>" in str(call_args)
            assert "recipient@example.com" in result

    @pytest.mark.asyncio
    async def test_get_emails_content_includes_message_id(self):
        """Test that get_emails_content returns message_id."""
        from datetime import datetime, timezone

        mock_handler = AsyncMock()
        mock_handler.get_emails_content = AsyncMock(
            return_value=EmailContentBatchResponse(
                emails=[
                    EmailBodyResponse(
                        email_id="123",
                        message_id="<test@example.com>",
                        subject="Test",
                        sender="sender@example.com",
                        recipients=["recipient@example.com"],
                        date=datetime.now(timezone.utc),
                        body="Test body",
                        attachments=[],
                    )
                ],
                requested_count=1,
                retrieved_count=1,
                failed_ids=[],
            )
        )

        with patch("mcp_email_server.app.dispatch_handler", return_value=mock_handler):
            result = await get_emails_content(
                account_name="test",
                email_ids=["123"],
            )

            assert result.emails[0].message_id == "<test@example.com>"

    @pytest.mark.asyncio
    async def test_get_full_email_body_rejects_rfc_message_id_header(self):
        """Reject RFC Message-ID values where an IMAP email_id (UID) is required."""
        with pytest.raises(ValueError, match="Expected IMAP UID `email_id`"):
            await get_full_email_body(
                account_name="test_account",
                email_id="<abc123@example.com>",
                folder="INBOX",
            )
