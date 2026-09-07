### Google-App einmalig einrichten

Die App gehört Ihnen beziehungsweise Ihrer Organisation.

1. Öffnen Sie die [Google Cloud Console](https://console.cloud.google.com/) und wählen oder erstellen Sie ein Projekt.
2. Öffnen Sie [Google Auth Platform](https://console.cloud.google.com/auth/overview). Richten Sie Branding und Zielgruppe ein. Verwenden Sie „Intern“ nur innerhalb Ihrer eigenen Workspace-Organisation, ansonsten „Extern“. Tragen Sie im Testbetrieb Ihre E-Mail-Adresse als Testnutzer ein.
3. Fügen Sie unter **Datenzugriff** den Bereich `https://mail.google.com/` hinzu. Er erlaubt IMAP/SMTP für Lesen, Ordner und Versand. Die Versandfreigaben dieser Anwendung legen Sie zusätzlich unter „Freigaben“ fest.
4. Erstellen Sie unter **Clients** einen OAuth-Client vom Typ **Desktop-App**.
5. Kopieren Sie **Client-ID** und **Client-Secret** in die folgenden Felder und speichern Sie. Das Desktop-Client-Secret ist ein App-Konfigurationswert, kein E-Mail-Passwort.
6. Klicken Sie auf „Beim Anbieter anmelden“, öffnen Sie den Link und wählen Sie dasselbe Konto wie die eingegebene E-Mail-Adresse. Erlauben Sie die Zugriffe.

**Freigabe blockiert?** Prüfen Sie Testnutzer und Workspace-Richtlinien. Für externe produktive Apps kann Google eine Verifizierung verlangen. Im Testmodus kann eine erneute Anmeldung nötig werden.

[Google: Desktop-Anmeldung](https://developers.google.com/identity/protocols/oauth2/native-app) · [Google: Mail-Zugriff über OAuth](https://developers.google.com/workspace/gmail/imap/xoauth2-protocol)
