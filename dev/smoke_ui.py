"""Browser regression check with isolated demo settings. Run via uv run --with playwright."""

# ruff: noqa: S101, S105 - isolated demo credentials and regression assertions

import os
import shutil
import socket
import tempfile
from pathlib import Path

import gradio as gr
from playwright.sync_api import expect, sync_playwright


def main() -> None:
    screenshots = Path(__file__).resolve().parents[1] / "docs" / "assets"
    screenshots.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="email-ui-smoke-") as directory:
        os.environ["MCP_EMAIL_SERVER_CONFIG_PATH"] = str(Path(directory) / "config.toml")
        from mcp_email_server.ui import CSS, create_ui

        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        app = create_ui()
        app.launch(
            server_name="127.0.0.1",
            server_port=port,
            prevent_thread_lock=True,
            inbrowser=False,
            share=False,
            quiet=True,
            footer_links=[],
            css=CSS,
            theme=gr.themes.Soft(primary_hue="teal", neutral_hue="slate"),
        )
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=shutil.which("google-chrome"))
                page = browser.new_page(viewport={"width": 1280, "height": 1000})
                page.on("pageerror", lambda error: print("Browser error:", error))
                page.goto(f"http://127.0.0.1:{port}")
                expect(page.get_by_text("Welcome.", exact=True)).to_be_visible()
                page.screenshot(path=str(screenshots / "setup-mailboxes.png"), full_page=True)
                page.get_by_label("Email address", exact=True).fill("demo@example.com")
                page.get_by_label("Sender name", exact=True).fill("Demo Customer")
                page.get_by_label("Account name (optional)", exact=True).fill("Work")
                page.get_by_label("Password / app password", exact=True).fill("demo-password")
                page.get_by_label("Incoming server (IMAP)", exact=True).fill("imap.example.com")
                page.get_by_label("Outgoing server (SMTP)", exact=True).fill("smtp.example.com")
                page.get_by_role("button", name="Save mailbox", exact=True).click()
                expect(page.get_by_text("✓ Mailbox saved.", exact=True)).to_be_visible()
                expect(page.get_by_label("Password / app password", exact=True)).to_have_value("")
                page.get_by_label("Sender name", exact=True).fill("Updated Name")
                page.get_by_role("button", name="Save mailbox", exact=True).click()
                expect(page.get_by_text("✓ Mailbox saved.", exact=True)).to_be_visible()
                page.get_by_role("button", name="+ Add mailbox", exact=True).click()
                expect(page.get_by_label("Email address", exact=True)).to_have_value("")
                page.get_by_label("Google / Gmail", exact=True).check()
                page.get_by_text("Connect Google / Microsoft with OAuth", exact=True).click()
                expect(page.get_by_text("Set up your Google app once", exact=True)).to_be_visible(timeout=15000)
                expect(page.get_by_label("Incoming server (IMAP)", exact=True)).to_be_visible()
                page.screenshot(path=str(screenshots / "setup-google.png"), full_page=True)
                page.get_by_role("button", name="Sign in with provider", exact=True).click()
                expect(page.get_by_text("Enter the email address first.", exact=True)).to_be_visible()
                page.get_by_label("Microsoft 365 / Outlook", exact=True).check()
                expect(page.get_by_text("Set up your Microsoft app once", exact=True)).to_be_visible()
                page.screenshot(path=str(screenshots / "setup-microsoft.png"), full_page=True)
                page.get_by_role("tab", name="Permissions", exact=True).click()
                expect(page.get_by_text("Allow restricted sending", exact=True)).to_be_visible()
                page.get_by_role("tab", name="Connect to Ariadne", exact=True).click()
                expect(page.get_by_text("Ariadne Engine MCP setup", exact=True)).to_be_visible()
                browser.close()
                from mcp_email_server.config import get_settings

                account = get_settings(reload=True).emails[0]
                assert account.incoming.password == "demo-password"
                assert account.full_name == "Updated Name"
                print("Browser OK: add/edit, secret retention, provider guides, permissions and integration tabs.")
        finally:
            app.close()


if __name__ == "__main__":
    main()
