"""
read_email.py — Lightweight IMAP email reader for Brain 2 Engine.
Fetches a single email by UID from a configured IMAP mailbox and returns its content as clean markdown.

Usage:
    python tools/read_email.py <UID>
    python tools/read_email.py <UID> -o Vault/Inbox/email_note.md
    python tools/read_email.py --list-recent 10
"""

import os
import sys
import argparse
from dotenv import load_dotenv

# Add project root to sys.path for engine imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# Import the core logic from engine
from engine.tools.email_tool import fetch_email_by_uid, list_recent_emails

# Load environment variables
load_dotenv()

# ── Credential Paths ──────────────────────────────────────────────────────────
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
SECRETS_DIR = os.path.join(TOOLS_DIR, ".secrets")

# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Lightweight IMAP email reader for Brain 2 Engine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python tools/read_email.py 4821\n"
            "  python tools/read_email.py 4821 -o Vault/Inbox/job_lead.md\n"
            "  python tools/read_email.py --list-recent 5\n"
        ),
    )
    parser.add_argument("uid", nargs="?", help="IMAP UID of the email to fetch")
    parser.add_argument("-o", "--output", help="Path to save the markdown output (optional)")
    parser.add_argument(
        "--list-recent", metavar="N", type=int, help="List the N most recent emails",
    )
    args = parser.parse_args()

    # ── List mode ──────────────────────────────────────────────────────────
    if args.list_recent:
        emails = list_recent_emails(args.list_recent, SECRETS_DIR)
        if not emails:
            print("No emails found or connection failed.", file=sys.stderr)
            sys.exit(1)
        col_w = 60
        print(f"{'UID':<8} {'Date':<32} {'From':<35} Subject")
        print("-" * 140)
        for e in emails:
            subj = e["subject"][:col_w] + ("…" if len(e["subject"]) > col_w else "")
            print(f"{e['uid']:<8} {e['date']:<32} {e['sender'][:35]:<35} {subj}")
        return

    # ── Fetch mode ─────────────────────────────────────────────────────────
    if not args.uid:
        parser.print_help()
        sys.exit(1)
    content = fetch_email_by_uid(args.uid, SECRETS_DIR)
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
        sys.exit(1)

if __name__ == "__main__":
    main()
