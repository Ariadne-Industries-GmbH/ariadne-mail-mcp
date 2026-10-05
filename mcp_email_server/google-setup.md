### Set up your Google app once

The app belongs to you or your organization.

1. Open [Google Cloud Console](https://console.cloud.google.com/) and select or create a project.
2. Open [Google Auth Platform](https://console.cloud.google.com/auth/overview). Configure branding and the audience. Use **Internal** only within your own Workspace organization; otherwise use **External**. Add your email address as a test user while the app is in testing.
3. Under **Data access**, add the `https://mail.google.com/` scope. IMAP/SMTP requires this broad scope for reading, folders, and sending. Set this application's local sending permission separately under **Permissions**.
4. Under **Clients**, create an OAuth client of type **Desktop app**.
5. Copy its **Client ID** and **Client secret** into the fields below and save them. A desktop client secret is app configuration, not an email password.
6. Select **Sign in with provider**, open the link, and choose the same account as the email address entered above. Grant the requested access.

**Access blocked?** Check test users and Workspace policies. Google may require verification for production external apps. A test-mode app may require another sign-in later.

[Google desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app) · [Google IMAP/SMTP OAuth](https://developers.google.com/workspace/gmail/imap/xoauth2-protocol)
