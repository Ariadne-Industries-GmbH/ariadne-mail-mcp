### Set up your Microsoft app once

You need access to a Microsoft Entra tenant. Your administrator may need to help with organization restrictions.

1. Open [Microsoft Entra](https://entra.microsoft.com/) and go to **Identity → Applications → App registrations → New registration**.
2. Choose a name and supported account types. For personal Outlook addresses, include **personal Microsoft accounts**.
3. Under **Authentication**, add a **Mobile and desktop applications** platform with `http://localhost/`. Sign-in uses an available local port; Microsoft ignores the port when matching this loopback redirect. Do not use a Web/SPA client or client secret.
4. Under **API permissions → Office 365 Exchange Online → Delegated permissions**, add `IMAP.AccessAsUser.All` and `SMTP.Send`. Sign-in also requests `offline_access`. Obtain administrator consent if required.
5. Copy the **Application (client) ID** below. For a single-tenant app, enter its **Directory (tenant) ID**; otherwise `common` may be used when supported by the selected account types. Save the settings.
6. Select **Sign in with provider**, open the link, and grant access using your mailbox account.

**Connection failed?** IMAP and SMTP AUTH must be allowed for the mailbox. Organization policies can disable them. The connection test reports IMAP and SMTP separately.

[Microsoft IMAP/SMTP OAuth](https://learn.microsoft.com/en-us/exchange/client-developer/legacy-protocols/how-to-authenticate-an-imap-pop-smtp-application-by-using-oauth) · [Loopback redirect URIs](https://learn.microsoft.com/en-us/entra/identity-platform/reply-url)
