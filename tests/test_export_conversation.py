"""
tests/test_export_conversation.py — Unit tests for universal conversation exporter and turn coalescing.
"""

import json
from pathlib import Path
import pytest

from nexus.shared_tools.export_conversation import (
    ChatMessage,
    ConversationTurn,
    clean_text_content,
    coalesce_conversation_turns,
    format_tool_action,
    format_turns_to_markdown,
    normalize_role,
    parse_json_data,
    parse_jsonl_stream,
)


def test_clean_text_content_user_request():
    raw = "<CONTEXT_SUMMARY>summary</CONTEXT_SUMMARY>\n<USER_REQUEST>\nfix the bug in chat\n</USER_REQUEST>"
    cleaned = clean_text_content(raw)
    assert cleaned == "fix the bug in chat"


def test_clean_text_content_plain():
    raw = "hello nexus"
    assert clean_text_content(raw) == "hello nexus"


def test_normalize_role_precedence():
    # User input precedence
    assert normalize_role("model", "USER_EXPLICIT", "USER_INPUT") == "user"
    assert normalize_role("", "user", "") == "user"

    # Tool output precedence (must NOT be treated as assistant even if source is MODEL)
    assert normalize_role("tool", "MODEL", "GENERIC") == "tool"
    assert normalize_role("", "MODEL", "GENERIC") == "tool"
    assert normalize_role("", "TOOL", "TOOL_RESPONSE") == "tool"

    # Assistant
    assert normalize_role("", "MODEL", "PLANNER_RESPONSE") == "assistant"
    assert normalize_role("assistant", "", "") == "assistant"

    # System
    assert normalize_role("", "SYSTEM", "SYSTEM_MESSAGE") == "system"
    assert normalize_role("", "SYSTEM", "CHECKPOINT") == "system"


def test_format_tool_action():
    # run_command
    tc1 = {
        "name": "run_command",
        "args": {
            "CommandLine": "pytest tests/test_chat.py",
            "toolSummary": "Run chat tests",
        },
    }
    f1 = format_tool_action(tc1)
    assert "run_command" in f1
    assert "Run chat tests" in f1
    assert "pytest tests/test_chat.py" in f1

    # read_file with lines
    tc2 = {
        "name": "read_file",
        "args": {
            "Path": "c:\\Users\\Willi\\Documents\\Projects\\Nexus\\src\\nexus\\core\\chats_db.py",
            "StartLine": 1,
            "EndLine": 50,
        },
    }
    f2 = format_tool_action(tc2)
    assert "read_file" in f2
    assert "chats_db.py" in f2
    assert "(Lines 1–50)" in f2


def test_coalesce_conversation_turns():
    raw_messages = [
        ChatMessage(role="user", content="Add a stop button", timestamp="2026-11-06T12:00:00"),
        ChatMessage(
            role="assistant",
            content="",
            tool_calls=[{"name": "read_file", "args": {"Path": "src/nexus/api.py"}}],
            timestamp="2026-11-06T12:00:01",
        ),
        ChatMessage(role="tool", content="file contents here...", timestamp="2026-11-06T12:00:02"),
        ChatMessage(
            role="assistant",
            content="",
            tool_calls=[{"name": "edit_file", "args": {"Path": "src/nexus/api.py"}}],
            timestamp="2026-11-06T12:00:03",
        ),
        ChatMessage(
            role="assistant",
            content="Stop button added successfully!",
            timestamp="2026-11-06T12:00:04",
        ),
        ChatMessage(role="user", content="Run the tests now", timestamp="2026-11-06T12:01:00"),
        ChatMessage(
            role="assistant",
            content="All tests passed!",
            tool_calls=[{"name": "run_command", "args": {"CommandLine": "pytest"}}],
            timestamp="2026-11-06T12:01:05",
        ),
    ]

    turns = coalesce_conversation_turns(raw_messages)
    assert len(turns) == 2

    turn1 = turns[0]
    assert turn1.turn_index == 1
    assert turn1.user_prompt == "Add a stop button"
    assert turn1.assistant_response == "Stop button added successfully!"
    assert len(turn1.tool_actions) == 2
    assert "read_file" in turn1.tool_actions[0]
    assert "edit_file" in turn1.tool_actions[1]

    turn2 = turns[1]
    assert turn2.turn_index == 2
    assert turn2.user_prompt == "Run the tests now"
    assert turn2.assistant_response == "All tests passed!"
    assert len(turn2.tool_actions) == 1
    assert "run_command" in turn2.tool_actions[0]


def test_format_turns_to_markdown():
    turn = ConversationTurn(
        turn_index=1,
        user_prompt="Explain stop and revert",
        assistant_response="Stop and revert halts execution and rolls back state.",
        tool_actions=["- **`run_command`** — pytest"],
    )
    md = format_turns_to_markdown("test_id", [turn], vault_format=True)
    assert "### Turn 1: Explain stop and revert" in md
    assert "**User**:" in md
    assert "> Explain stop and revert" in md
    assert "**Assistant**:" in md
    assert "Stop and revert halts execution and rolls back state." in md
    assert "Tool Executions (1 actions)" in md
    assert "pytest" in md
    assert "tags: [engineering, transcript" in md
