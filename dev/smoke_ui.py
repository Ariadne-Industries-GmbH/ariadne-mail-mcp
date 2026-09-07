"""Browser regression check with isolated demo settings. Run via uv run --with playwright."""

# ruff: noqa: S101, S105 - isolated demo credentials and regression assertions

import os
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
        for function in app.fns.values():
            if function.fn.__name__ == "choose_provider":
                original_function = function.fn

                def traced_provider(value):
                    result = original_function(value)
                    print("Provider callback:", value, "guide length:", len(result[2]))
                    return result

                function.fn = traced_provider
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
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={"width": 1280, "height": 1000})
                page.on("pageerror", lambda error: print("Browser error:", error))
                page.goto(f"http://127.0.0.1:{port}")
                expect(page.get_by_text("Willkommen.", exact=True)).to_be_visible()
                page.screenshot(path=str(screenshots / "setup-postfaecher.png"), full_page=True)
                page.get_by_label("E-Mail-Adresse", exact=True).fill("demo@example.com")
                page.get_by_label("Absendername", exact=True).fill("Demo Kunde")
                page.get_by_label("Kontoname (optional)", exact=True).fill("Arbeit")
                page.get_by_label("Passwort / App-Passwort", exact=True).fill("demo-password")
                page.get_by_label("Posteingangsserver (IMAP)", exact=True).fill("imap.example.com")
                page.get_by_label("Postausgangsserver (SMTP)", exact=True).fill("smtp.example.com")
                page.get_by_role("button", name="Postfach speichern", exact=True).click()
                expect(page.get_by_text("✓ Postfach gespeichert.", exact=True)).to_be_visible()
                expect(page.get_by_label("Passwort / App-Passwort", exact=True)).to_have_value("")
                page.get_by_label("Absendername", exact=True).fill("Geänderter Name")
                page.get_by_role("button", name="Postfach speichern", exact=True).click()
                expect(page.get_by_text("✓ Postfach gespeichert.", exact=True)).to_be_visible()
                page.get_by_role("button", name="+ Postfach hinzufügen", exact=True).click()
                expect(page.get_by_label("E-Mail-Adresse", exact=True)).to_have_value("")
                page.get_by_label("Google / Gmail", exact=True).check()
                expect(page.get_by_text("Google-App einmalig einrichten", exact=True)).to_be_visible(timeout=15000)
                expect(page.get_by_label("Posteingangsserver (IMAP)", exact=True)).not_to_be_visible()
                page.screenshot(path=str(screenshots / "setup-google.png"), full_page=True)
                page.get_by_role("button", name="Beim Anbieter anmelden", exact=True).click()
                expect(page.get_by_text("Bitte zuerst die E-Mail-Adresse eingeben.", exact=True)).to_be_visible()
                page.get_by_label("Microsoft 365 / Outlook", exact=True).check()
                expect(page.get_by_text("Microsoft-App einmalig einrichten", exact=True)).to_be_visible()
                page.screenshot(path=str(screenshots / "setup-microsoft.png"), full_page=True)
                page.get_by_role("tab", name="Freigaben", exact=True).click()
                expect(page.get_by_text("Versand gezielt erlauben", exact=True)).to_be_visible()
                page.get_by_role("tab", name="Mit KI verbinden", exact=True).click()
                expect(page.get_by_text("MCP-Client einrichten", exact=True)).to_be_visible()
                browser.close()
                from mcp_email_server.config import get_settings

                account = get_settings(reload=True).emails[0]
                assert account.incoming.password == "demo-password"
                assert account.full_name == "Geänderter Name"
                print("Browser OK: add/edit, secret retention, provider guides, permissions and integration tabs.")
        finally:
            app.close()


if __name__ == "__main__":
    main()
