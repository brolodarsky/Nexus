---
type: minor
---
### Added
- Non-plain-text content and attachment awareness across `gmail_engine.py` and `fetch_emails` (`shared.py`): structured attachment/inline-media metadata (`filename`, `mime_type`, `size_bytes`, `size`, `disposition`, `content_id`), unnamed non-text MIME part discovery (e.g., `text/calendar` invites, `message/rfc822`), inline `cid:`/external/embedded HTML image & media placeholders with 1x1/hidden tracking-pixel filtering, and explicit `non_text_notice` summaries in `get_message()`, `message_to_markdown()`, `fetch_emails` JSON output, and `cache://email/<id>` captures.
- Gmail "Send mail as" alias discovery (`list_send_as_aliases()`, `--list-send-as`) and verified `From:` selection (`create_draft(..., send_as=...)`, CLI `--send-as` / `--from`), including automatic owning-mailbox resolution when paired with `--account all`.
