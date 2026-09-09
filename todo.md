# MCP Email Server – Capabilities and TODOs

## Current Capabilities (MCP)

- Resource email://{account_name}: returns masked account config. Status: untested (assumed OK).
- Tool list_available_accounts(): lists all accounts masked. Status: covered by tests; working.
- Tool add_email_account(email): adds config and persists to TOML. Status: covered by tests; working.
- Tool page_email(...): paginated fetch with filters (before/since/subject/body/text/from/to, order=desc default). Returns previewed emails. Status: covered by tests; working.
- Tool send_email(account_name, recipients, subject, body, cc?, bcc?): sends via SMTP. Status: covered by tests; working (returns success message).
- Tool list_folders(account_name): IMAP LIST. Status: implemented; not covered by tests.
- Tool move_email(account_name, message_id, source, destination): IMAP COPY + delete. Status: implemented; not covered by tests.
- Tool delete_email(account_name, message_id, folder=INBOX): marks deleted + expunge. Status: implemented; not covered by tests.
- Tool get_full_email_body(account_name, message_id, folder=INBOX): fetch RFC822 and parse body. Status: implemented; not covered by tests.

## Known Issues / Mismatches

None currently known beyond items under "Additions to Consider".

## Additions to Consider

- Provider accounts: dispatch_handler raises NotImplementedError for ProviderSettings. Currently documented as not supported yet.
- Expand tests to cover: list_folders, move_email, delete_email, get_full_email_body, and get_account resource.
- Error reporting: surface meaningful errors for IMAP/SMTP failures (timeouts, auth) from tools.
- Consistent tool returns: ensure all tools return JSON-serializable, documented shapes (e.g., success strings/objects).

## Next Steps

- [x] Fix send_email to return success message. (Done)
- [x] Correct EmailData.to_preview().sender. (Done)
- [ ] Add tests for folder ops and full-body fetch.
- [ ] Add tests for mark_email tool (flag add/remove behavior).
- [x] Decide on provider support strategy; implement or document. (Documented as not supported yet in README)
- [x] Update docs for tool inputs/outputs and examples. (Done in README)
