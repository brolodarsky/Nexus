"""
calendar_engine.py — Core Google Calendar API integration for Nexus Engine.

Provides deterministic Python functions to list, create, update, and delete events
on Google Calendar using local OAuth credentials stored in .secrets/.

Standing Architectural Directives:
- Pure data access layer (No LangChain @tool decorators here; see shared.py).
- Uses token_calendar.json to isolate calendar OAuth tokens from email tokens.
- Handles both ISO datetime strings ('2026-09-29T15:00:00-04:00') and all-day dates ('2026-09-29').
"""

import os
import sys
import argparse
from datetime import datetime, time, timedelta
from typing import Any, Optional
from googleapiclient.discovery import build, Resource

# Reconfigure stdout/stderr to UTF-8 on Windows to safely print emoji-laden calendar events
if sys.platform == "win32" and sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Nexus absolute imports
from nexus.core.constants import PROJECT_ROOT
from nexus.core.google_auth import get_google_credentials

# Full read/write calendar permissions scope
CALENDAR_SCOPES: list[str] = ["https://www.googleapis.com/auth/calendar"]
SECRETS_DIR: str = str(PROJECT_ROOT / ".secrets")
TOKEN_FILENAME: str = "token_calendar.json"


def get_calendar_service() -> Resource:
    """
    Authenticate and build the Google Calendar Resource client.
    
    Returns:
        googleapiclient.discovery.Resource: Authorized Google Calendar API v3 service instance.
    """
    # 1. Retrieve or refresh credentials via isolated token file
    creds = get_google_credentials(
        scopes=CALENDAR_SCOPES,
        secrets_dir=SECRETS_DIR,
        token_filename=TOKEN_FILENAME,
    )
    # 2. Build the discovery service client for Calendar v3
    return build("calendar", "v3", credentials=creds)


def list_events(
    start_iso: Optional[str] = None,
    end_iso: Optional[str] = None,
    max_results: int = 50,
    calendar_id: str = "primary",
) -> list[dict[str, Any]]:
    """
    Query events from Google Calendar within a specific time boundary.

    Args:
        start_iso: RFC3339 timestamp (e.g. '2026-09-29T00:00:00-04:00'). Defaults to start of today.
        end_iso: RFC3339 timestamp (e.g. '2026-09-29T23:59:59-04:00'). Defaults to end of today.
        max_results: Maximum events to return (clamped between 1 and 250).
        calendar_id: Calendar ID target ('primary' represents the authenticated personal calendar).

    Returns:
        list[dict]: Clean list of event dictionaries containing id, summary, start, end, description.
    """
    service = get_calendar_service()
    now_local = datetime.now().astimezone()

    # Default to beginning of local day if start_iso not provided
    if not start_iso:
        today_start = datetime.combine(now_local.date(), time.min).astimezone()
        start_iso = today_start.isoformat()

    # Default to end of local day if end_iso not provided
    if not end_iso:
        today_end = datetime.combine(now_local.date(), time.max).astimezone()
        end_iso = today_end.isoformat()

    # Query Google Calendar API v3 events collection
    events_result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=start_iso,
            timeMax=end_iso,
            maxResults=max_results,
            singleEvents=True,  # Expands recurring rules into individual event instances
            orderBy="startTime",
        )
        .execute()
    )

    raw_items = events_result.get("items", [])
    parsed_events: list[dict[str, Any]] = []

    for item in raw_items:
        # Google returns 'dateTime' for timed events, or 'date' (YYYY-MM-DD) for all-day events
        start_raw = item.get("start", {})
        end_raw = item.get("end", {})
        start_val = start_raw.get("dateTime", start_raw.get("date", ""))
        end_val = end_raw.get("dateTime", end_raw.get("date", ""))

        parsed_events.append({
            "id": item.get("id"),
            "summary": item.get("summary", "(Untitled Event)"),
            "start": start_val,
            "end": end_val,
            "description": item.get("description", ""),
            "location": item.get("location", ""),
            "status": item.get("status", "confirmed"),
            "htmlLink": item.get("htmlLink", ""),
        })

    return parsed_events


def create_event(
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str = "",
    location: str = "",
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """
    Create a new event in Google Calendar.

    Args:
        summary: Event title (e.g. 'Career Offense', 'Gym: Push Day').
        start_iso: RFC3339 datetime or YYYY-MM-DD string.
        end_iso: RFC3339 datetime or YYYY-MM-DD string.
        description: Detailed notes, links, or exercise sets.
        location: Physical location or Zoom/Meet URL.
        calendar_id: Target calendar ('primary').

    Returns:
        dict: The created Google Calendar event resource.
    """
    service = get_calendar_service()

    # Determine whether input is all-day ('YYYY-MM-DD') or timestamp
    is_date_only = len(start_iso) == 10 and "T" not in start_iso
    start_body = {"date": start_iso} if is_date_only else {"dateTime": start_iso}
    end_body = {"date": end_iso} if is_date_only else {"dateTime": end_iso}

    event_body = {
        "summary": summary,
        "description": description,
        "location": location,
        "start": start_body,
        "end": end_body,
    }

    created = service.events().insert(calendarId=calendar_id, body=event_body).execute()
    return {
        "id": created.get("id"),
        "summary": created.get("summary"),
        "start": created.get("start"),
        "end": created.get("end"),
        "htmlLink": created.get("htmlLink"),
    }


def update_event(
    event_id: str,
    summary: Optional[str] = None,
    start_iso: Optional[str] = None,
    end_iso: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """
    Update an existing event's fields (partial update via patch).

    Args:
        event_id: The unique Google Calendar event ID.
        summary: New title, or None to keep existing.
        start_iso: New start time, or None to keep existing.
        end_iso: New end time, or None to keep existing.
        description: New description text, or None to keep existing.
        location: New location string, or None to keep existing.
        calendar_id: Target calendar ('primary').

    Returns:
        dict: The updated event resource.
    """
    service = get_calendar_service()
    patch_body: dict[str, Any] = {}

    if summary is not None:
        patch_body["summary"] = summary
    if description is not None:
        patch_body["description"] = description
    if location is not None:
        patch_body["location"] = location

    if start_iso is not None:
        is_date_only = len(start_iso) == 10 and "T" not in start_iso
        patch_body["start"] = {"date": start_iso} if is_date_only else {"dateTime": start_iso}

    if end_iso is not None:
        is_date_only = len(end_iso) == 10 and "T" not in end_iso
        patch_body["end"] = {"date": end_iso} if is_date_only else {"dateTime": end_iso}

    updated = service.events().patch(calendarId=calendar_id, eventId=event_id, body=patch_body).execute()
    return {
        "id": updated.get("id"),
        "summary": updated.get("summary"),
        "start": updated.get("start"),
        "end": updated.get("end"),
        "htmlLink": updated.get("htmlLink"),
    }


def delete_event(event_id: str, calendar_id: str = "primary") -> bool:
    """
    Delete an event from Google Calendar.

    Args:
        event_id: Unique event ID.
        calendar_id: Target calendar ('primary').

    Returns:
        bool: True if deletion succeeded.
    """
    service = get_calendar_service()
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    return True


def clean_html_description(raw_desc: str) -> str:
    """Strip raw Google Calendar HTML markup into clean human-readable Markdown text."""
    if not raw_desc:
        return ""
    import html
    import re
    # Convert paragraph closures, breaks, and list items into newlines
    text = re.sub(r"<br\s*/?>", "\n", raw_desc, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
    # Convert <a href="URL">TEXT</a> into Markdown link format [TEXT](URL)
    text = re.sub(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', r"[\2](\1)", text, flags=re.IGNORECASE)
    # Strip remaining HTML tags (like <strong>, <em>, <ol>, etc.)
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities (&amp;, &nbsp;, &#39;, etc.)
    text = html.unescape(text)
    # Clean up blank lines while preserving indentation
    lines = [line.strip() for line in text.splitlines()]
    return "\n  ".join([l for l in lines if l])


def format_events_as_markdown(events: list[dict[str, Any]], title: str = "Today's Schedule") -> str:
    """Format a list of events into a clean markdown block for prompts and notes."""
    if not events:
        return f"### {title}\n*No scheduled events found for this window.*"

    lines = [f"### {title}"]
    for ev in events:
        # Extract readable time strings
        start_str = ev["start"]
        end_str = ev["end"]
        # Format ISO string like 2026-09-29T14:00:00-04:00 to 14:00 if possible
        if "T" in start_str:
            time_part_start = start_str.split("T")[1][:5]
            time_part_end = end_str.split("T")[1][:5] if "T" in end_str else ""
            time_display = f"{time_part_start} – {time_part_end}"
        else:
            time_display = "All Day"

        summary = ev["summary"]
        cleaned_desc = clean_html_description(ev.get("description", ""))
        desc_block = f"\n  - *Notes:* {cleaned_desc}" if cleaned_desc else ""
        lines.append(f"- **{time_display}**: {summary}{desc_block}")

    return "\n".join(lines)


# ── Interactive CLI Entrypoint ───────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Google Calendar CLI for Nexus Engine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python src/nexus/shared_tools/calendar_engine.py --auth\n"
            "  python src/nexus/shared_tools/calendar_engine.py --today\n"
            "  python src/nexus/shared_tools/calendar_engine.py --create 'Deep Work' '2026-09-29T16:00:00-04:00' '2026-09-29T17:30:00-04:00'\n"
        ),
    )
    parser.add_argument("--auth", action="store_true", help="Perform initial OAuth browser authorization")
    parser.add_argument("--today", action="store_true", help="List all events for today")
    parser.add_argument("--days", type=int, default=1, help="Number of days ahead to list (default: 1)")
    parser.add_argument("--create", nargs=3, metavar=("TITLE", "START_ISO", "END_ISO"), help="Create a new event")
    parser.add_argument("--delete", metavar="EVENT_ID", help="Delete an event by ID")

    args = parser.parse_args()

    if args.auth:
        print("[Nexus] Authenticating Google Calendar...")
        service = get_calendar_service()
        print("[Nexus] Calendar authentication successful! Token stored at .secrets/token_calendar.json")
        return

    if args.create:
        title, start, end = args.create
        res = create_event(summary=title, start_iso=start, end_iso=end)
        print(f"[Nexus] Event created successfully: {res.get('summary')} ({res.get('id')})")
        return

    if args.delete:
        delete_event(event_id=args.delete)
        print(f"[Nexus] Event {args.delete} deleted successfully.")
        return

    # Default action or --today
    now_local = datetime.now().astimezone()
    start_dt = datetime.combine(now_local.date(), time.min).astimezone()
    end_dt = datetime.combine(now_local.date() + timedelta(days=args.days - 1), time.max).astimezone()

    events = list_events(start_iso=start_dt.isoformat(), end_iso=end_dt.isoformat())
    md = format_events_as_markdown(events, title=f"Schedule ({start_dt.strftime('%A, %b %d')})")
    print(md)


if __name__ == "__main__":
    main()
