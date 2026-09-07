# E-Mail-MCP einrichten

## Starten ohne Python

Entpacken Sie das Archiv für Ihr Betriebssystem. Starten Sie unter Windows `mcp-email-server.exe`.
Unter Linux starten Sie `./mcp-email-server`; gegebenenfalls vorher `chmod +x mcp-email-server` ausführen.
Die Oberfläche öffnet sich im Browser auf diesem Rechner. Das Programm muss während der Einrichtung laufen.

Die Release-Binaries sind für Windows und Linux x86-64 vorgesehen. Linux benötigt glibc 2.35 oder neuer
(beispielsweise Ubuntu 22.04). OAuth benötigt zusätzlich den System-Schlüsselbund. Windows nutzt den
Anmeldeinformationsspeicher; unter Linux werden eine D-Bus-Benutzersitzung und ein entsperrter
Secret-Service-Schlüsselbund benötigt. Eine Python-Installation ist nicht erforderlich.

Falls der Port belegt ist: `mcp-email-server ui --port 8766`. Für einen Start ohne automatisch geöffneten
Browser: `mcp-email-server ui --no-open-browser`. Die Oberfläche lauscht ausschließlich auf `127.0.0.1`.

## Postfach verbinden

Unter **Postfächer** wählen Sie die Anmeldemethode:

- **IMAP / SMTP:** E-Mail-Adresse, Passwort oder App-Passwort und beide Servernamen eintragen.
  Abweichende Anmeldenamen, Ports, Verschlüsselung und Gesendet-Ordner finden Sie in den erweiterten Einstellungen.
- **Google / Gmail:** Die eingeblendete Anleitung führt durch Google Cloud, Zielgruppe, Mail-Berechtigung
  und Desktop-OAuth-Client. Hinterlegen Sie die App-Daten einmalig und melden Sie sich anschließend beim Anbieter an.
- **Microsoft 365 / Outlook:** Die Anleitung führt durch die eigene Entra-App, passende Kontotypen,
  Desktop-Weiterleitung und delegierte Exchange-Berechtigungen. Eventuell ist Unterstützung Ihrer Administration nötig.

Jeder Kunde richtet seine eigene Anbieter-App ein. Die Anwendung enthält keine zentrale Herausgeber-App.
Sie fragt Ihre Freigabe im Anbieter-Browserfenster ab und speichert die OAuth-Tokens im System-Schlüsselbund.
Ein Login ist nach drei Minuten abgelaufen und kann neu gestartet oder abgebrochen werden.

Der Verbindungstest prüft IMAP und SMTP getrennt, ohne eine E-Mail zu senden oder Nachrichten zu verändern.
Nach OAuth-Anmeldung wird das Postfach erst gespeichert, wenn beide Verbindungen funktionieren.
Bei einem vorhandenen Postfach können Sie den Absendernamen und Serverdaten bearbeiten; leere Passwortfelder
behalten die gespeicherten Passwörter bei. Der interne Kontoname bleibt stabil.

## Freigaben festlegen

Unter **Freigaben** wählen Sie das Konto und die erlaubten Empfänger für den eingeschränkten KI-Versand.
Ohne diese Angaben bleibt er gesperrt. Anhänge herunterladen ist standardmäßig ausgeschaltet.
Lesen, Verschieben und Markieren bleiben verfügbar. Allgemeiner Versand und Löschen werden weiterhin nicht als
MCP-Werkzeuge veröffentlicht. Die OAuth-Berechtigung beim Anbieter ersetzt diese lokalen Versandfreigaben nicht.

## Mit einem KI-Client verbinden

Unter **Mit KI verbinden** finden Sie den Programmpfad, das Argument `stdio` und einen kopierbaren MCP-Eintrag.
Der Eintrag enthält den Konfigurationspfad, aber keine Passwörter oder Tokens. Den Eintrag in die vorhandene
Client-Konfiguration integrieren, ohne andere Server zu überschreiben. Der KI-Client startet das Binary selbst;
die Setup-Oberfläche muss dafür nicht geöffnet bleiben.

Die Ariadne-Registrierung bleibt verfügbar. Bei einer Engine auf einem anderen Rechner müssen das Programm,
die Konfiguration und die Anmeldung auf diesem Rechner eingerichtet werden. Ein System-Schlüsselbund ist
an Benutzer und Betriebssystem gebunden; die TOML-Datei allein überträgt keine OAuth-Anmeldung.

## Speicherorte und bestehende Installation

- Windows: `%APPDATA%\zerolib\mcp_email_server\config.toml`
- Linux: `$XDG_CONFIG_HOME/zerolib/mcp_email_server/config.toml`, standardmäßig `~/.config/zerolib/mcp_email_server/config.toml`
- Eigener Pfad: `MCP_EMAIL_SERVER_CONFIG_PATH`. `mcp-email-server config-path` zeigt den tatsächlich verwendeten Pfad.

Beim Start der Oberfläche oder des Stdio-Servers wird eine alte `mcp_email_server/config.toml` aus dem Arbeitsverzeichnis
beziehungsweise neben dem Binary übernommen, wenn am neuen Standardpfad noch keine Konfiguration liegt.
Die Quelldatei bleibt erhalten. Bei einem expliziten Konfigurationspfad findet keine automatische Migration statt.

Klassische Passwörter verbleiben in der lokalen TOML-Datei. Neue Dateien haben unter Linux Modus `0600`;
unter Windows gelten die Rechte des Benutzerprofils. OAuth-App-Daten liegen daneben in `oauth-clients.json`;
Benutzer-Tokens werden ausschließlich im System-Schlüsselbund gespeichert.

Umgebungsvariablen überschreiben weiterhin einzelne Konten. Diese Konten sind in der UI als verwaltet gekennzeichnet.
Ihre Umgebungs-Passwörter werden beim Speichern anderer Einstellungen nicht in die Datei geschrieben.
Laufende MCP-Prozesse übernehmen Dateiänderungen beim nächsten Werkzeugaufruf.

## Fehlerhilfe

**Google verweigert den Zugriff:** Client-Typ Desktop-App, Testnutzer, Zielgruppe und Workspace-Richtlinien prüfen.
Für externe produktive Anwendungen mit Mail-Zugriff kann eine Google-Verifizierung erforderlich sein.

**Microsoft meldet eine falsche Weiterleitung:** In der Desktop-Plattform muss `http://localhost/` registriert sein.
Eine Web- oder SPA-App hat andere Anforderungen und passt nicht zu diesem Login.

**Microsoft-Login funktioniert, IMAP/SMTP nicht:** Postfachzugriff beziehungsweise SMTP AUTH können durch
Organisationsrichtlinien gesperrt sein. Die Administration muss die jeweilige Freigabe prüfen.

**Schlüsselbund gesperrt/nicht vorhanden:** Unter Linux einen Secret-Service-Schlüsselbund für denselben Benutzer
wie den MCP-Prozess einrichten und entsperren. Es gibt keinen stillen Klartext-Fallback für OAuth-Tokens.

**Erneute Anmeldung nötig:** Anbieterfreigaben können widerrufen werden oder ablaufen. Das Konto bearbeiten und
erneut beim Anbieter anmelden. Die Anwendung erneuert gültige Refresh-Tokens automatisch.

Offizielle Referenzen: [Google Desktop-OAuth](https://developers.google.com/identity/protocols/oauth2/native-app),
[Google Mail-OAuth](https://developers.google.com/workspace/gmail/imap/xoauth2-protocol),
[Microsoft Mail-OAuth](https://learn.microsoft.com/en-us/exchange/client-developer/legacy-protocols/how-to-authenticate-an-imap-pop-smtp-application-by-using-oauth),
[Microsoft Weiterleitungen](https://learn.microsoft.com/en-us/entra/identity-platform/reply-url).
