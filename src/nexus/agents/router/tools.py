"""
tools.py — Tools for the Router Agent.
"""
import json

from langchain_core.tools import tool

# Cap each email body so a long newsletter can't blow the Router's context window
_BODY_CHAR_LIMIT = 4000


@tool
def fetch_emails(query: str, count: int = 5) -> str:
    """If the user explicitly asks to check their email, read a recent email, or mentions an email, use this tool to retrieve the email data. Do not use this tool for local notes or files.

    Args:
        query: Gmail search syntax, e.g. 'in:inbox', 'from:recruiter@openai.com', 'subject:interview newer_than:14d'.
        count: Max emails to return (default 5).
    """
    # Lazy import: keeps googleapiclient off the Router's import path until email is actually needed
    from nexus.shared_tools import gmail_engine

    try:
        service = gmail_engine.get_gmail_service()  # Build once, reuse for every message fetch below
        summaries = gmail_engine.list_messages(query=query, max_results=count, service=service)
        emails = []
        for s in summaries:
            msg = gmail_engine.get_message(s["id"], service=service)
            emails.append({
                "id": msg["id"],
                "thread_id": msg["thread_id"],
                "subject": msg["subject"],
                "sender": msg["sender"],
                "date": msg["date"],
                "body": msg["body"][:_BODY_CHAR_LIMIT],  # Slice notation: first N characters only
            })
        return json.dumps(emails, ensure_ascii=False)
    except Exception as exc:
        # Return an empty-but-explained payload so the Router can still classify instead of crashing
        return json.dumps([{"error": f"fetch_emails failed: {exc}"}])
