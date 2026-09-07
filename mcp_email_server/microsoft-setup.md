### Microsoft-App einmalig einrichten

Sie benötigen Zugriff auf einen Entra-Mandanten; bei Organisationsbeschränkungen unterstützt Sie Ihre Administration.

1. Öffnen Sie [Microsoft Entra](https://entra.microsoft.com/), dann **Identität → Anwendungen → App-Registrierungen → Neue Registrierung**.
2. Wählen Sie einen Namen und den Kontotyp: eigene Organisation oder – für persönliche Outlook-Adressen – Organisationsverzeichnisse **und persönliche Microsoft-Konten**.
3. Richten Sie unter **Authentifizierung** eine **Desktop-/Mobil-Plattform** mit `http://localhost/` ein. Der Login verwendet einen freien lokalen Port, den Microsoft bei dieser Loopback-Adresse beim Abgleich ignoriert. Kein Web-/SPA-Client oder Client-Secret.
4. Ergänzen Sie unter **API-Berechtigungen → Office 365 Exchange Online → Delegierte Berechtigungen**: `IMAP.AccessAsUser.All` und `SMTP.Send`. Die Anmeldung fordert auch `offline_access` an. Lassen Sie gegebenenfalls Administratorzustimmung erteilen.
5. Kopieren Sie die **Anwendungs-ID (Client)** unten. Bei einer App für einen Mandanten tragen Sie dessen **Verzeichnis-ID** ein; sonst kann bei passendem Kontotyp `common` stehen bleiben. Speichern Sie.
6. Klicken Sie auf „Beim Anbieter anmelden“, öffnen Sie den Link und erlauben Sie den Zugriff mit Ihrem Postfachkonto.

**Verbindung fehlgeschlagen?** IMAP und SMTP AUTH müssen für das Postfach erlaubt sein. Organisationsrichtlinien können sie sperren. Der Verbindungstest zeigt beide Ergebnisse getrennt.

[Microsoft: OAuth für IMAP/SMTP](https://learn.microsoft.com/en-us/exchange/client-developer/legacy-protocols/how-to-authenticate-an-imap-pop-smtp-application-by-using-oauth) · [Loopback-Adressen](https://learn.microsoft.com/en-us/entra/identity-platform/reply-url)
