"""Local customer setup: accounts, provider guidance, permissions and integrations."""

import asyncio
import html
import os
import re
from contextlib import suppress
from pathlib import Path
from typing import Any

import gradio as gr

from mcp_email_server.config import EMAIL_ADDRESS_REGEX, AiSendsEmailToolSettings, EmailSettings, get_settings
from mcp_email_server.integrations import client_config, command_path, register_ariadne
from mcp_email_server.oauth import LoginError, PendingLogin, load_clients, remove_tokens, save_clients
from mcp_email_server.paths import get_config_path, migrate_legacy_config
from mcp_email_server.setup import (
    DEFAULTS,
    FIELDS,
    PLAIN,
    PROVIDERS,
    STARTTLS,
    TLS,
    SetupError,
    build_account,
    check_account,
    env_managed,
    load_form,
    save_account,
)

CSS = """
.gradio-container { max-width: 1080px !important; margin: auto; }
#intro { padding: 22px 0 12px; }
#intro h1 { letter-spacing: -.035em; font-size: 2.2rem; }
.account-summary { padding: 16px; border: 1px solid var(--border-color-primary); border-radius: 12px; }
footer { display: none !important; }
"""


def _parse_allowed_recipients_input(raw_text: str) -> list[str]:
    return [entry.strip() for entry in re.split(r"[,\n;]", raw_text or "") if entry.strip()]


def _message(error: Exception) -> str:
    if isinstance(error, (SetupError, LoginError)):
        return html.escape(str(error))
    if isinstance(error, OSError):
        return "Die Einstellungen konnten nicht gespeichert werden. Speicherort und Schreibrechte prüfen."
    return "Bitte die Eingaben prüfen. Die Einstellungen wurden nicht übernommen."


def _connection_report(results: list[tuple[str, bool, str]]) -> str:
    return "\n\n".join(
        f"{'✓' if success else '✗'} **{protocol}:** {html.escape(message)}" for protocol, success, message in results
    )


def create_ui() -> gr.Blocks:  # noqa: C901
    pending_logins: dict[str, PendingLogin] = {}
    with gr.Blocks(title="E-Mail verbinden", analytics_enabled=False) as app:
        gr.Markdown(
            "# Ihre E-Mails. Mit Ihrer KI.\nPostfächer verbinden, Zugriffe festlegen und den MCP einrichten.",
            elem_id="intro",
        )
        summary = gr.Markdown("Konten werden geladen …", elem_classes="account-summary")
        original = gr.State(None)
        with gr.Tabs():
            with gr.Tab("Postfächer"):
                with gr.Row():
                    selected = gr.Dropdown(label="Postfach auswählen", choices=[], interactive=True, scale=3)
                    new_button = gr.Button("+ Postfach hinzufügen", scale=1)
                    refresh_button = gr.Button("Aktualisieren", scale=1)
                edit_button = gr.Button("Ausgewähltes Postfach bearbeiten")
                with gr.Group():
                    form_title = gr.Markdown("### Postfach hinzufügen")
                    provider = gr.Radio(PROVIDERS, value="manual", label="Wie möchten Sie sich verbinden?")
                    with gr.Row():
                        address = gr.Textbox(label="E-Mail-Adresse", placeholder="name@firma.de")
                        full_name = gr.Textbox(label="Absendername", placeholder="Vorname Nachname")
                    account_name = gr.Textbox(
                        label="Kontoname (optional)", placeholder="z. B. Arbeit; sonst die E-Mail-Adresse"
                    )
                    with gr.Column(elem_id="manual-settings"):
                        password = gr.Textbox(
                            label="Passwort / App-Passwort",
                            type="password",
                            placeholder="Beim Bearbeiten leer lassen, um es beizubehalten",
                        )
                        with gr.Row():
                            imap_host = gr.Textbox(label="Posteingangsserver (IMAP)", placeholder="imap.firma.de")
                            smtp_host = gr.Textbox(label="Postausgangsserver (SMTP)", placeholder="smtp.firma.de")
                        with gr.Accordion("Erweiterte Servereinstellungen", open=False):
                            user_name = gr.Textbox(label="Anmeldename", placeholder="Standard: E-Mail-Adresse")
                            with gr.Row():
                                imap_port = gr.Number(label="IMAP-Port", value=993, precision=0)
                                imap_security = gr.Dropdown([TLS, PLAIN], value=TLS, label="IMAP-Verschlüsselung")
                                smtp_port = gr.Number(label="SMTP-Port", value=465, precision=0)
                                smtp_security = gr.Dropdown(
                                    [TLS, STARTTLS, PLAIN], value=TLS, label="SMTP-Verschlüsselung"
                                )
                            gr.Markdown(
                                "SMTP: üblicherweise 465 mit SSL/TLS oder 587 mit STARTTLS. Unverschlüsselte Verbindungen übertragen Zugangsdaten ohne Transportschutz."
                            )
                            with gr.Row():
                                imap_user = gr.Textbox(label="Abweichender IMAP-Anmeldename")
                                imap_password = gr.Textbox(label="Abweichendes IMAP-Passwort", type="password")
                            with gr.Row():
                                smtp_user = gr.Textbox(label="Abweichender SMTP-Anmeldename")
                                smtp_password = gr.Textbox(label="Abweichendes SMTP-Passwort", type="password")
                            save_sent = gr.Checkbox(
                                value=True, label="Gesendete E-Mails zusätzlich im IMAP-Ordner ablegen"
                            )
                            sent_folder = gr.Textbox(label="Gesendet-Ordner", placeholder="Automatisch erkennen")
                    with gr.Accordion("Google / Microsoft mit OAuth verbinden", open=False):
                        gr.Markdown(
                            "Wählen Sie oben **Google / Gmail** oder **Microsoft 365 / Outlook**. "
                            "Die Server- und Passwortfelder werden bei OAuth nicht verwendet. "
                            "Die folgenden Schritte richten eine eigene App Ihrer Organisation für dieses Gerät ein."
                        )
                        gr.Markdown(
                            Path(__file__).with_name("google-setup.md").read_text(encoding="utf-8")
                            + "\n\n---\n\n"
                            + Path(__file__).with_name("microsoft-setup.md").read_text(encoding="utf-8")
                        )
                        with gr.Accordion("App-Daten für dieses Gerät", open=True):
                            client_id = gr.Textbox(label="Client-ID / Anwendungs-ID des gewählten Anbieters")
                            client_secret = gr.Textbox(
                                label="Google Desktop-Client-Secret (nur Google)", type="password"
                            )
                            tenant = gr.Textbox(label="Microsoft-Mandant (nur Microsoft)", value="common")
                            with gr.Row():
                                app_load = gr.Button("Gespeicherte App-Daten laden")
                                app_save = gr.Button("App-Einrichtung speichern")
                            app_status = gr.Markdown("")
                        gr.Markdown(
                            "Tokens bleiben im System-Schlüsselbund. Unter Linux muss dieser eingerichtet und entsperrt sein."
                        )
                        with gr.Row():
                            login_button = gr.Button("Beim Anbieter anmelden", variant="primary")
                            cancel_login = gr.Button("Anmeldung abbrechen")
                        login_status = gr.Markdown("")
                    status = gr.Markdown("")
                    with gr.Row():
                        test_button = gr.Button("Verbindung testen")
                        save_button = gr.Button("Postfach speichern", variant="primary")
                    gr.Markdown(
                        "Der Verbindungstest meldet sich nur an. Er versendet keine E-Mails und verändert keine Nachrichten."
                    )
                with gr.Accordion("Postfach entfernen", open=False):
                    confirm_delete = gr.Checkbox(
                        label="Ich möchte das ausgewählte Postfach aus dieser Anwendung entfernen."
                    )
                    delete_button = gr.Button("Ausgewähltes Postfach entfernen", variant="stop")
                    delete_status = gr.Markdown("")
                    gr.Markdown(
                        "E-Mails beim Anbieter bleiben erhalten. Eine Versandfreigabe für dieses Konto wird entfernt."
                    )
            with gr.Tab("Freigaben"):
                gr.Markdown(
                    "### Versand gezielt erlauben\nDie KI kann nur über das hier gewählte Konto an freigegebene Adressen senden. Ohne Konto und Empfänger bleibt dieser Versand gesperrt."
                )
                allowed_account = gr.Dropdown(label="Konto für eingeschränkten Versand", choices=[], interactive=True)
                recipients = gr.Textbox(label="Freigegebene Empfänger", lines=4, placeholder="Eine Adresse pro Zeile")
                download = gr.Checkbox(label="Herunterladen von Anhängen auf diesen Rechner erlauben", value=False)
                gr.Markdown(
                    "Lesen, Verschieben und Markieren bleiben verfügbar. Allgemeiner Versand und Löschen sind weiterhin nicht als MCP-Werkzeuge freigeschaltet."
                )
                with gr.Row():
                    permission_save = gr.Button("Freigaben speichern", variant="primary")
                    permission_clear = gr.Button("Versandfreigabe entfernen")
                permission_status = gr.Markdown("")
            with gr.Tab("Mit KI verbinden"):
                gr.Markdown(
                    "### MCP-Client einrichten\nWählen Sie in Ihrem KI-Client einen lokalen MCP-Server. Verwenden Sie das Programm mit dem Argument `stdio`. Der Client startet den MCP bei Bedarf selbst."
                )
                executable = gr.Textbox(label="Pfad zum Programm", value=command_path())
                config_preview = gr.Code(
                    label="MCP-Konfiguration kopieren",
                    language="json",
                    value=client_config(command_path()),
                    interactive=False,
                )
                gr.Markdown(
                    "Für Clients mit `mcpServers`-Konfiguration, beispielsweise Claude Desktop. Andere Clients können dieselben Werte über eigene Eingabefelder übernehmen. Bestehende Servereinträge beibehalten. Auf einem anderen Rechner dessen Programm- und Konfigurationspfade verwenden."
                )
                with gr.Accordion("Mit Ariadne Engine verbinden", open=False):
                    gr.Markdown(
                        "Ariadne startet das Programm auf dem Engine-Rechner. Der Pfad und die Kontokonfiguration müssen dort verfügbar sein."
                    )
                    endpoint = gr.Textbox(label="Engine-Endpunkt", placeholder="https://ihre-engine.example/…")
                    api_key = gr.Textbox(label="Engine-API-Schlüssel", type="password")
                    spec_name = gr.Textbox(label="Name in Ariadne", value="mcp-email-server")
                    engine_command = gr.Textbox(label="Programmpfad auf dem Engine-Rechner", value=command_path())
                    tags = gr.Textbox(label="Tags (optional, durch Kommas getrennt)")
                    description = gr.Textbox(label="Beschreibung (optional)")
                    register = gr.Button("In Ariadne registrieren / aktualisieren")
                    engine_status = gr.Textbox(label="Ergebnis", interactive=False)
            with gr.Tab("Speicher & Hilfe"):
                gr.Markdown(
                    "### Ihre Konfiguration\nSpeicherort: `" + str(get_config_path()) + "`\n\n"
                    "IMAP-/SMTP-Passwörter liegen in dieser lokalen Datei. Unter Linux sind neue Dateien nur für Ihren Benutzer zugänglich; unter Windows gelten die Rechte Ihres Benutzerprofils. OAuth-Tokens liegen im System-Schlüsselbund.\n\n"
                    "**Umgebungsvariablen:** Vorgaben einer verwalteten Installation haben Vorrang. Solche Konten werden gekennzeichnet und lassen sich hier nicht überschreiben.\n\n"
                    "**Verbindungsprobleme:** Server, Passwort, Verschlüsselung und Anbieter-Freigaben prüfen. Die Anleitungen für Google und Microsoft finden Sie bei der Anbieterauswahl.\n\n"
                    "**Linux-Schlüsselbund:** Für OAuth benötigen Sie einen Secret-Service-Dienst (etwa GNOME-Schlüsselbund oder entsprechend eingerichtetes KWallet), eine D-Bus-Benutzersitzung und einen entsperrten Schlüsselbund.\n\n"
                    "**Änderungen:** Laufende MCP-Prozesse laden geänderte Kontoeinstellungen beim nächsten Werkzeugaufruf. Nach Änderungen an der Client-Konfiguration den MCP im KI-Client neu starten."
                )
        fields = [
            account_name,
            full_name,
            address,
            provider,
            user_name,
            password,
            imap_host,
            imap_port,
            imap_security,
            imap_user,
            imap_password,
            smtp_host,
            smtp_port,
            smtp_security,
            smtp_user,
            smtp_password,
            save_sent,
            sent_folder,
        ]

        def refresh() -> tuple[Any, ...]:
            settings = get_settings(reload=True)
            names = [e.account_name for e in settings.emails]
            managed = [name for name in names if env_managed(name)]
            text = (
                f"**{len(names)} Postfach/Postfächer eingerichtet.**"
                if names
                else "**Willkommen.** Verbinden Sie Ihr erstes Postfach, um loszulegen."
            )
            if managed:
                text += " Verwaltet über Umgebungsvariablen: " + html.escape(", ".join(managed))
            return (
                text,
                gr.update(choices=names, value=None),
                gr.update(choices=names, value=settings.ai_sends_email_tool.allowed_account_name),
                "\n".join(settings.ai_sends_email_tool.allowed_recipients),
                gr.update(
                    value=settings.enable_attachment_download,
                    interactive=os.getenv("MCP_EMAIL_SERVER_ENABLE_ATTACHMENT_DOWNLOAD") is None,
                ),
            )

        refresh_outputs = [summary, selected, allowed_account, recipients, download]
        app.load(refresh, outputs=refresh_outputs, api_name=False)
        refresh_button.click(refresh, outputs=refresh_outputs, api_name=False)

        def edit(name: str | None) -> tuple[Any, ...]:
            if not name:
                return (None, "### Postfach hinzufügen", "", *DEFAULTS)
            return (
                name,
                "### Postfach bearbeiten",
                "Passwortfelder leer lassen, um gespeicherte Passwörter beizubehalten.",
                *load_form(name),
            )

        edit_button.click(edit, selected, [original, form_title, status, *fields], api_name=False)
        new_button.click(lambda: edit(None), outputs=[original, form_title, status, *fields], api_name=False)

        def save(original_name: str | None, *raw: Any) -> tuple[Any, ...]:
            try:
                account = build_account(dict(zip(FIELDS, raw, strict=True)), original_name)
                save_account(account, original_name)
                return "✓ Postfach gespeichert.", account.account_name, "", "", ""
            except Exception as error:
                return _message(error), original_name, gr.skip(), gr.skip(), gr.skip()

        save_button.click(
            save, [original, *fields], [status, original, password, imap_password, smtp_password], api_name=False
        ).then(refresh, outputs=refresh_outputs, api_name=False)

        async def test(original_name: str | None, *raw: Any) -> str:
            try:
                account = build_account(dict(zip(FIELDS, raw, strict=True)), original_name)
                return _connection_report(await check_account(account))
            except Exception as error:
                return _message(error)

        test_button.click(test, [original, *fields], status, api_name=False)

        def load_app(value: str) -> tuple[str, Any, Any, Any]:
            if value not in {"google", "microsoft"}:
                return "Bitte zuerst Google oder Microsoft als Anbieter wählen.", gr.skip(), gr.skip(), gr.skip()
            client = load_clients()[value]
            if not client.get("client_id"):
                return "Für diesen Anbieter sind noch keine App-Daten gespeichert.", "", "", "common"
            return (
                "Gespeicherte App-Daten geladen. Das Client-Secret wird aus Sicherheitsgründen nicht angezeigt.",
                client["client_id"],
                "",
                client.get("tenant", "common"),
            )

        app_load.click(
            load_app,
            provider,
            [app_status, client_id, client_secret, tenant],
            api_name=False,
        )

        def save_app(value: str, identifier: str, secret: str, directory: str) -> str:
            try:
                if value not in {"google", "microsoft"}:
                    return "Bitte zuerst Google oder Microsoft als Anbieter wählen."
                clients = load_clients()
                google, microsoft = clients["google"], clients["microsoft"]
                if value == "google":
                    google = {"client_id": identifier, "client_secret": secret or google.get("client_secret", "")}
                elif value == "microsoft":
                    microsoft = {"client_id": identifier, "tenant": directory}
                if not identifier.strip():
                    return "Bitte die Client-ID aus dem Anbieterportal eingeben."
                save_clients(
                    google.get("client_id", ""),
                    google.get("client_secret", ""),
                    microsoft.get("client_id", ""),
                    microsoft.get("tenant", "common"),
                )
                return "✓ App-Daten gespeichert. Sie können sich jetzt beim Anbieter anmelden."
            except Exception as error:
                return _message(error)

        app_save.click(save_app, [provider, client_id, client_secret, tenant], app_status, api_name=False)

        async def login(request: gr.Request, original_name: str | None, *raw: Any):
            session = request.session_hash
            pending = None
            account_auth = None
            try:
                values = dict(zip(FIELDS, raw, strict=True))
                if not EMAIL_ADDRESS_REGEX.fullmatch(values["email_address"].strip()):
                    yield "Bitte zuerst die E-Mail-Adresse eingeben.", gr.skip()
                    return
                if session in pending_logins:
                    pending_logins[session].cancel()
                pending = PendingLogin(values["provider"], values["email_address"].strip())
                pending_logins[session] = pending
                yield (
                    f"[Anmeldung beim Anbieter öffnen]({pending.url})\n\nNach der Anmeldung wird das Postfach geprüft und gespeichert.",
                    gr.skip(),
                )
                while not pending.done.is_set():
                    await asyncio.sleep(0.5)
                account_auth = await asyncio.to_thread(pending.finish)
                account = build_account(values, original_name, account_auth)
                results = await check_account(account)
                if not all(success for _, success, _ in results):
                    yield (
                        _connection_report(results)
                        + "\n\nPostfach nicht gespeichert. Bitte Anbieter-Freigaben prüfen und erneut anmelden.",
                        gr.skip(),
                    )
                    return
                save_account(account, original_name)
                account_auth = None
                yield "✓ Anmeldung und Verbindung erfolgreich. Postfach gespeichert.", account.account_name
            except Exception as error:
                yield _message(error), gr.skip()
            finally:
                if pending:
                    pending.cancel()
                    if pending_logins.get(session) is pending:
                        pending_logins.pop(session, None)
                if account_auth:
                    with suppress(LoginError):
                        remove_tokens(account_auth.credential_id)

        login_button.click(
            login, [original, *fields], [login_status, original], api_name=False, concurrency_limit=4
        ).then(refresh, outputs=refresh_outputs, api_name=False)

        def cancel(request: gr.Request) -> str:
            pending = pending_logins.get(request.session_hash)
            if pending:
                pending.cancel()
            return "Anmeldung abgebrochen."

        cancel_login.click(cancel, outputs=login_status, api_name=False, queue=False)

        def delete(name: str | None, confirmed: bool) -> tuple[str, bool]:
            if not name or not confirmed:
                return "Bitte ein Postfach auswählen und das Entfernen bestätigen.", False
            try:
                if env_managed(name):
                    return "Dieses Konto wird über Umgebungsvariablen verwaltet.", False
                settings = get_settings(reload=True)
                account = settings.get_account(name)
                if isinstance(account, EmailSettings) and account.oauth:
                    remove_tokens(account.oauth.credential_id)
                settings.delete_email(name)
                settings.store()
                return "Postfach entfernt. E-Mails beim Anbieter bleiben erhalten.", False
            except Exception as error:
                return _message(error), False

        delete_button.click(delete, [selected, confirm_delete], [delete_status, confirm_delete], api_name=False).then(
            refresh, outputs=refresh_outputs, api_name=False
        )

        def permissions(name: str | None, addresses: str, allow_download: bool) -> str:
            try:
                settings = get_settings(reload=True)
                if name and not isinstance(settings.get_account(name), EmailSettings):
                    return "Bitte ein vorhandenes Postfach auswählen."
                allowed = _parse_allowed_recipients_input(addresses)
                if allowed and not name:
                    return "Bitte das Konto für die Empfängerfreigabe auswählen."
                settings.ai_sends_email_tool = AiSendsEmailToolSettings(
                    allowed_account_name=name, allowed_recipients=allowed
                )
                settings.enable_attachment_download = allow_download
                settings.store()
                return "✓ Freigaben gespeichert."
            except Exception as error:
                return _message(error)

        permission_save.click(
            permissions, [allowed_account, recipients, download], permission_status, api_name=False
        ).then(refresh, outputs=refresh_outputs, api_name=False)
        permission_clear.click(
            lambda value: permissions(None, "", value), download, permission_status, api_name=False
        ).then(refresh, outputs=refresh_outputs, api_name=False)
        executable.change(client_config, executable, config_preview, api_name=False)
        register.click(
            register_ariadne,
            [api_key, endpoint, spec_name, engine_command, tags, description],
            engine_status,
            api_name=False,
        )
    return app


def main(port: int = 8765, open_browser: bool = True) -> None:
    migrate_legacy_config()
    app = create_ui()
    app.launch(
        server_name="127.0.0.1",
        server_port=port,
        inbrowser=open_browser,
        share=False,
        show_error=False,
        footer_links=[],
        css=CSS,
        theme=gr.themes.Soft(primary_hue="teal", neutral_hue="slate"),
    )


if __name__ == "__main__":
    main()
