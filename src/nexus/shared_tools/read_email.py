"""
read_email.py — Lightweight IMAP email reader for Nexus Engine.
Fetches a single email by UID or lists/searches emails from a configured IMAP mailbox,
returning structured clean markdown or tabular metadata.

Usage:
    python tools/read_email.py <UID>
    python tools/read_email.py <UID> -o Vault/Inbox/email_note.md
    python tools/read_email.py --list-recent 10
    python tools/read_email.py --search "palantir"
"""

import json
import os
import sys
import argparse
from dotenv import load_dotenv

# Import core tool logic from the email agent package
from nexus.agents.email.tools import fetch_email_by_uid, list_recent_emails, search_emails

# Load environment variables
load_dotenv()


def _print_email_table(emails: list[dict]):
    """Format and print email metadata in a clean fixed-width terminal table."""
    if not emails:
        print("No emails found.", file=sys.stderr)
        return

    col_subj_w = 60
    col_sender_w = 32
    print(f"{'UID':<8} {'Date':<32} {'From':<{col_sender_w}} Subject")
    print("-" * 135)
    for e in emails:
        if not isinstance(e, dict) or "uid" not in e:
            continue
        sender = e.get("sender", "(Unknown)")
        sender_str = sender[:col_sender_w] + ("…" if len(sender) > col_sender_w else "")
        subject = e.get("subject", "(No Subject)")
        subj_str = subject[:col_subj_w] + ("…" if len(subject) > col_subj_w else "")
        print(f"{e.get('uid', ''):<8} {e.get('date', ''):<32} {sender_str:<{col_sender_w}} {subj_str}")


def main():
    parser = argparse.ArgumentParser(
        description="Lightweight IMAP email reader for Nexus Engine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python src/nexus/shared_tools/read_email.py 45760\n"
            "  python src/nexus/shared_tools/read_email.py 45760 -o Vault/Inbox/job_lead.md\n"
            "  python src/nexus/shared_tools/read_email.py --list-recent 5\n"
            "  python src/nexus/shared_tools/read_email.py --search 'palantir'\n"
        ),
    )
    parser.add_argument("uid", nargs="?", help="IMAP UID of the email to fetch")
    parser.add_argument("-o", "--output", help="Path to save the markdown output (optional)")
    parser.add_argument(
        "--list-recent", metavar="N", type=int, help="List the N most recent emails",
    )
    parser.add_argument(
        "--search", metavar="QUERY", type=str, help="Search emails by freeform query or IMAP syntax (e.g. 'palantir', FROM 'google')",
    )
    args = parser.parse_args()

    # ── Search mode ────────────────────────────────────────────────────────
    if args.search:
        raw_res = search_emails.invoke({"query": args.search, "count": 10})
        try:
            results = json.loads(raw_res) if isinstance(raw_res, str) else raw_res
        except Exception:
            results = []
        if isinstance(results, list) and results and "error" in results[0]:
            print(f"Search failed: {results[0]['error']}", file=sys.stderr)
            sys.exit(1)
        _print_email_table(results)
        return

    # ── List recent mode ───────────────────────────────────────────────────
    if args.list_recent:
        raw_res = list_recent_emails.invoke({"count": args.list_recent})
        try:
            results = json.loads(raw_res) if isinstance(raw_res, str) else raw_res
        except Exception:
            results = []
        if isinstance(results, list) and results and "error" in results[0]:
            print(f"Listing failed: {results[0]['error']}", file=sys.stderr)
            sys.exit(1)
        _print_email_table(results)
        return

    # ── Fetch mode ─────────────────────────────────────────────────────────
    if not args.uid:
        parser.print_help()
        sys.exit(1)

    content = fetch_email_by_uid.invoke({"uid": args.uid})
    if content:
        if args.output:
            os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Saved email UID {args.uid} → {args.output}")
        else:
            if sys.stdout.encoding != "utf-8":
                sys.stdout.reconfigure(encoding="utf-8")
            print(content)
    else:
        print(f"Failed to fetch email UID {args.uid}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

