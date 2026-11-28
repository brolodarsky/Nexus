"""
test_instruction_guard.py — Comprehensive tests for deterministic tool-layer instruction
injection (Pillar 1), write-time instruction hydration gating (Pillar 2), and automatic
`Section Instructions.md` pre-hydration for `spawn_subagent` (Pillar 3).
"""

import os
from pathlib import Path

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from langchain_core.messages import AIMessage, HumanMessage
import pytest

from nexus.agent import subagent as subagent_mod
from nexus.core import chats_db, conversation_cache, hitl_queue as hq, instruction_guard as ig
from nexus.core.engine_constitution import inject_root_instructions
from nexus.core.hitl_queue import reset_hitl_execution_context, set_hitl_execution_context
from nexus.core.instruction_guard import (
    clear_seen_instructions,
    reset_instruction_batch_id,
    set_instruction_batch_id,
)
from nexus.core.trace import reset_trace_thread_id, set_trace_thread_id
from nexus.shared_tools import shared as shared_module, vault_reader


# ── Isolated Temp Vault & SQLite Fixture ─────────────────────────────────────

@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Isolates `VAULT_PATH`, `hitl.db`, `chats.db`, and the instruction ledger per test."""
    vault_dir = tmp_path / "Vault"
    vault_dir.mkdir(parents=True, exist_ok=True)
    hitl_db = tmp_path / "hitl.db"
    chats_path = tmp_path / "chats.db"

    monkeypatch.setattr(vault_reader, "VAULT_PATH", vault_dir)
    monkeypatch.setattr(shared_module, "VAULT_PATH", vault_dir)
    monkeypatch.setattr(hq, "DB_PATH", hitl_db)
    monkeypatch.setattr(chats_db, "DB_PATH", chats_path)

    hq.init_db()
    chats_db.init_db()
    clear_seen_instructions()
    try:
        yield {"tmp": tmp_path, "vault": vault_dir, "hitl_db": hitl_db, "chats_db": chats_path}
    finally:
        clear_seen_instructions()


def _write_note(vault_dir: Path, rel_path: str, text: str) -> Path:
    """Helper writing UTF-8 Markdown into the isolated test Vault."""
    full = vault_dir / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(text, encoding="utf-8")
    return full


# ── 1. Frontmatter & Heading Context Extraction ──────────────────────────────

def test_parse_frontmatter_and_extract_instructions_variants() -> None:
    """Verify PyYAML parsing for list, scalar, missing, and malformed-YAML fallback `instructions:`."""
    list_doc = (
        "---\n"
        "tags: [strategy]\n"
        "instructions:\n"
        "  - Avoid timed execution containers.\n"
        "  - \"Sync with [[Tasks]].\"\n"
        "---\n"
        "# Body\n"
    )
    fm, fm_end = vault_reader.parse_frontmatter(list_doc)
    assert fm["tags"] == ["strategy"]
    assert fm_end == 6
    rules, rules_end = vault_reader.extract_frontmatter_instructions(list_doc)
    assert rules == ["Avoid timed execution containers.", "Sync with [[Tasks]]."]
    assert rules_end == 6

    scalar_doc = "---\ntype: project\ninstructions: Keep synced with parent project.\n---\nBody\n"
    rules_scalar, end_scalar = vault_reader.extract_frontmatter_instructions(scalar_doc)
    assert rules_scalar == ["Keep synced with parent project."]
    assert end_scalar == 4

    no_fm_doc = "# Just a plain heading\nNo frontmatter.\n"
    assert vault_reader.parse_frontmatter(no_fm_doc) == ({}, 0)
    assert vault_reader.extract_frontmatter_instructions(no_fm_doc) == ([], 0)

    # Unclosed YAML quote / bracket triggers PyYAML YAMLError -> regex fallback rescues instructions lines.
    malformed_yaml_doc = (
        "---\n"
        "tags: [career]\n"
        "instructions:\n"
        "  - Rule one: \"unclosed quote keeps tables clean\n"
        "  - Rule two: [unclosed bracket never append logs\n"
        "---\n"
        "# Summary\n"
    )
    assert vault_reader.parse_frontmatter(malformed_yaml_doc) == ({}, 6)
    fallback_rules, fallback_end = vault_reader.extract_frontmatter_instructions(malformed_yaml_doc)
    assert fallback_rules == [
        'Rule one: "unclosed quote keeps tables clean',
        "Rule two: [unclosed bracket never append logs",
    ]
    assert fallback_end == 6

    # PyYAML parses unquoted `- Key: value` bullets as 1-key dicts; normalization reconstructs clean rule strings.
    colon_bullet_doc = "---\ninstructions:\n  - Rule one: keep tables clean\n---\n# Summary\n"
    colon_rules, _ = vault_reader.extract_frontmatter_instructions(colon_bullet_doc)
    assert colon_rules == ["Rule one: keep tables clean"]


def test_extract_heading_context_inline_rules_and_fence_immunity() -> None:
    """Verify nested heading stacks, code-fence immunity, and inline rule patterns without false positives."""
    doc = (
        "---\n"
        "instructions:\n"
        "  - Top level instruction.\n"
        "---\n"
        "# Today\n"
        "*Active daily checklist rule.*\n"
        "\n"
        "## To Do\n"
        "_Remove completed items from Tasks._\n"
        "\n"
        "- [ ] Item A\n"
        "```python\n"
        "# Fake Python Comment Heading\n"
        "x = 1\n"
        "```\n"
        "\n"
        "## Active\n"
        "Reserved strictly for warm referral pipelines.\n"
        "\n"
        "| Col1 | Col2 |\n"
        "\n"
        "## Saturday\n"
        "\n"
        "> [!warning] Saturday Check-In\n"
        "> Confirm priorities before noon.\n"
        "\n"
        "- Check in\n"
        "\n"
        "## Narrative\n"
        "This is a multi-line narrative paragraph that spans across two\n"
        "consecutive lines and must NOT be treated as a 1-line inline rule.\n"
        "\n"
        "## Recurring\n"
        "* **Daily:**\n"
        "  - Walk 30m\n"
        "**Bold Label:**\n"
        "- Item\n"
    )
    lines = doc.splitlines()
    # Line numbers inside `doc`: verify exact heading extraction and code fence immunity.
    all_headings = vault_reader.extract_all_headings_with_rules(doc)
    heading_texts = [h["text"] for h in all_headings]
    assert "Fake Python Comment Heading" not in heading_texts
    assert heading_texts == ["Today", "To Do", "Active", "Saturday", "Narrative", "Recurring"]

    by_text = {h["text"]: h for h in all_headings}
    assert by_text["Today"]["inline_rule"] == "*Active daily checklist rule.*"
    assert by_text["To Do"]["inline_rule"] == "_Remove completed items from Tasks._"
    assert by_text["Active"]["inline_rule"] == "Reserved strictly for warm referral pipelines."
    assert by_text["Saturday"]["inline_rule"] == "> [!warning] Saturday Check-In\n> Confirm priorities before noon."
    assert by_text["Narrative"]["inline_rule"] is None
    assert by_text["Recurring"]["inline_rule"] is None

    # Line inside `## To Do` (`- [ ] Item A` on line 11) carries both `# Today` and `## To Do`.
    item_a_line = lines.index("- [ ] Item A") + 1
    stack = vault_reader.extract_heading_context_for_line(doc, item_a_line, inclusive=False)
    assert [h["text"] for h in stack] == ["Today", "To Do"]

    # Sibling `## Active` (`| Col1 | Col2 |`) unwinds `## To Do` while retaining `# Today`.
    table_line = lines.index("| Col1 | Col2 |") + 1
    stack_active = vault_reader.extract_heading_context_for_line(doc, table_line, inclusive=False)
    assert [h["text"] for h in stack_active] == ["Today", "Active"]

    # When `target_line` sits ON the heading itself, `inclusive=False` excludes it while `inclusive=True` includes it.
    sat_line = by_text["Saturday"]["line"]
    assert [h["text"] for h in vault_reader.extract_heading_context_for_line(doc, sat_line, inclusive=False)] == [
        "Today"
    ]
    assert [h["text"] for h in vault_reader.extract_heading_context_for_line(doc, sat_line, inclusive=True)] == [
        "Today",
        "Saturday",
    ]


# ── 2. Pillar 1: Partial Reads Inject Missing Context ────────────────────────

def test_partial_read_injects_context_on_disk_and_hitl_staged_notes(isolated_env: dict[str, Path]) -> None:
    """Sliced reads prepend missing frontmatter/heading rules while omitting redundant banners on plain/cache reads."""
    vault = isolated_env["vault"]
    governed = (
        "---\n"
        "tags: [plan]\n"
        "instructions:\n"
        "  - Avoid timed execution containers.\n"
        "  - Keep priorities ordered.\n"
        "---\n"
        "**Back to:** [[Table of Contents]]\n"
        "\n"
        "# Today\n"
        "*Active daily execution checklist.*\n"
        "\n"
        "## To Do\n"
        "*Sync with [[Tasks]] whenever finished.*\n"
        "\n"
        "- [ ] Task 1\n"
        "- [ ] Task 2\n"
        "- [ ] Task 3\n"
    )
    _write_note(vault, "Gameplan.md", governed)
    _write_note(vault, "Plain.md", "\n".join(f"Plain line {i}" for i in range(1, 25)))

    tok = set_hitl_execution_context(conversation_id="conv-p1", thread_id="conv-p1")
    try:
        # 1. Partial slice starting inside `## To Do` (L15..L17) gets frontmatter + `# Today` + `## To Do`.
        sliced = shared_module.read_file.invoke({"file_path": "Gameplan.md", "start_line": 15, "end_line": 17})
        assert "[Document Context — Always obey when reading or editing this slice]" in sliced
        assert "Avoid timed execution containers." in sliced
        assert "`# Today` (L9) — *Active daily execution checklist.*" in sliced
        assert "`## To Do` (L12) — *Sync with [[Tasks]] whenever finished.*" in sliced
        assert "- [ ] Task 1" in sliced

        # 2. Slice starting at line 1 covering all frontmatter (L1..L11) omits redundant frontmatter banner & enclosing path.
        top_slice = shared_module.read_file.invoke({"file_path": "Gameplan.md", "start_line": 1, "end_line": 11})
        assert "[Document Context" not in top_slice

        # 3. Slice starting at line 1 that cuts off BEFORE the closing `---` (L1..L3) still injects frontmatter rules!
        truncated_fm = shared_module.read_file.invoke({"file_path": "Gameplan.md", "start_line": 1, "end_line": 3})
        assert "[Document Context" in truncated_fm
        assert "Avoid timed execution containers." in truncated_fm

        # 4. Plain note without frontmatter or headings leaves slice output clean.
        plain_slice = shared_module.read_file.invoke({"file_path": "Plain.md", "start_line": 10, "end_line": 15})
        assert "[Document Context" not in plain_slice
        assert "Plain line 10" in plain_slice

        # 5. Cache captures (`cache://...`) are untouched by Vault markdown context banners.
        key = conversation_cache.put_capture(
            conversation_id="conv-p1",
            source_type="web",
            title="External",
            content="# Heading\nLine 1\nLine 2\nLine 3",
            source_url="https://example.com/p1",
        )
        cache_slice = shared_module.read_file.invoke({"file_path": key, "start_line": 2, "end_line": 3})
        assert "[Document Context" not in cache_slice
        assert "2: Line 1" in cache_slice

        # 6. HITL-staged modified & moved notes also inject `[Document Context]` on sliced reads.
        hq.add_transaction(
            agent_name="nexus_agent",
            action_type="modify",
            target_file="Vault/Gameplan.md",
            proposed_content=governed.replace("- [ ] Task 3", "- [x] Task 3"),
            original_content=governed,
            reasoning="Test staged read banner",
        )
        staged_slice = shared_module.read_file.invoke({"file_path": "Gameplan.md", "start_line": 15, "end_line": 17})
        assert "[STAGED IN HITL QUEUE" in staged_slice
        assert "[Document Context" in staged_slice
        assert "Avoid timed execution containers." in staged_slice
        assert "`## To Do` (L12)" in staged_slice

        hq.add_transaction(
            agent_name="nexus_agent",
            action_type="move",
            target_file="Vault/Gameplan.md",
            destination_file="Vault/Archive/Gameplan.md",
            proposed_content=governed,
            original_content=governed,
            reasoning="Test staged move read banner",
        )
        moved_slice = shared_module.read_file.invoke({"file_path": "Gameplan.md", "start_line": 15, "end_line": 17})
        assert "[STAGED TO MOVE IN HITL QUEUE" in moved_slice
        assert "[Document Context" in moved_slice
        assert "Keep priorities ordered." in moved_slice
    finally:
        reset_hitl_execution_context(tok)


# ── 3. Pillar 2: Write-Time Instruction Hydration Gate ───────────────────────

def test_plain_ungoverned_notes_pass_immediately_without_gate_friction(isolated_env: dict[str, Path]) -> None:
    """Plain notes with no `Section Instructions.md`, frontmatter `instructions:`, or heading rules pass on 1st call."""
    vault = isolated_env["vault"]
    _write_note(vault, "Simple.md", "# Simple\n\nOld text.\n")

    tok = set_hitl_execution_context(conversation_id="conv-plain", thread_id="conv-plain")
    try:
        mod_res = shared_module.modify_file.invoke(
            {
                "file_path": "Simple.md",
                "target": "Old text.",
                "replacement": "New text.",
                "reasoning": "Simple edit",
            }
        )
        assert "✅ Surgical modification staged to HITL queue" in mod_res

        create_res = shared_module.create_file.invoke(
            {
                "file_path": "AnotherSimple.md",
                "content": "# Another\n\nBody.\n",
                "reasoning": "Simple create",
            }
        )
        assert "✅ File creation staged to HITL queue" in create_res
    finally:
        reset_hitl_execution_context(tok)


def test_write_gate_blocks_all_three_layers_and_passes_on_retry(isolated_env: dict[str, Path]) -> None:
    """First blind write blocks with section, frontmatter, and inline heading rules; retry stages cleanly."""
    vault = isolated_env["vault"]
    _write_note(
        vault,
        "3. Operations/Section Instructions.md",
        "# Operations Rules\nKeep operational records crisp.\n",
    )
    _write_note(
        vault,
        "3. Operations/3.1. Career/Section Instructions.md",
        "# Career Rules\nNever invent YOE or metrics.\n",
    )
    _write_note(
        vault,
        "3. Operations/3.1. Career/Campaign.md",
        "---\n"
        "instructions:\n"
        "  - Obey inline section rules.\n"
        "---\n"
        "# Missions\n"
        "\n"
        "## Active\n"
        "Reserved strictly for warm referrals.\n"
        "\n"
        "- Row 1\n",
    )

    tok = set_hitl_execution_context(conversation_id="conv-gate", thread_id="conv-gate")
    try:
        # 1. Blind modify_file blocks and stages ZERO rows into hitl.db.
        blocked = shared_module.modify_file.invoke(
            {
                "file_path": "3. Operations/3.1. Career/Campaign.md",
                "target": "- Row 1",
                "replacement": "- Row 1\n- Row 2",
                "reasoning": "Add active mission",
            }
        )
        assert blocked.startswith("⚠️ Write Blocked — Instruction Hydration Required")
        assert "3. Operations/Section Instructions.md" in blocked
        assert "Keep operational records crisp." in blocked
        assert "3. Operations/3.1. Career/Section Instructions.md" in blocked
        assert "Never invent YOE or metrics." in blocked
        assert "Obey inline section rules." in blocked
        assert "`## Active` (L7) — Reserved strictly for warm referrals." in blocked
        assert "Master Instructions.md" in blocked
        assert hq.get_pending_transactions() == []

        # 2. Retry passes immediately and stages the transaction.
        passed = shared_module.modify_file.invoke(
            {
                "file_path": "3. Operations/3.1. Career/Campaign.md",
                "target": "- Row 1",
                "replacement": "- Row 1\n- Row 2",
                "reasoning": "Add active mission",
            }
        )
        assert "✅ Surgical modification staged to HITL queue" in passed
        assert len(hq.get_pending_transactions()) == 1

        # 3. `create_file` inside a governed folder blocks on 1st call if ancestor wasn't seen yet, passes on 2nd.
        _write_note(vault, "2. Health/Section Instructions.md", "# Health Rules\nNever extrapolate lab numbers.\n")
        blocked_create = shared_module.create_file.invoke(
            {
                "file_path": "2. Health/2.2. Medical/NewLab.md",
                "content": "# Lab\n\nPending.\n",
                "reasoning": "Create lab note",
            }
        )
        assert blocked_create.startswith("⚠️ Write Blocked — Instruction Hydration Required")
        assert "Never extrapolate lab numbers." in blocked_create
        assert hq.get_pending_for_file("Vault/2. Health/2.2. Medical/NewLab.md") is None

        passed_create = shared_module.create_file.invoke(
            {
                "file_path": "2. Health/2.2. Medical/NewLab.md",
                "content": "# Lab\n\nPending.\n",
                "reasoning": "Create lab note",
            }
        )
        assert "✅ File creation staged to HITL queue" in passed_create
    finally:
        reset_hitl_execution_context(tok)


def test_full_section_read_plus_partial_read_satisfies_gate_but_partial_section_read_does_not(
    isolated_env: dict[str, Path],
) -> None:
    """Full `Section Instructions.md` + partial target slice clears gate; partial `Section Instructions.md` does not."""
    vault = isolated_env["vault"]
    sec_lines = ["# Career Rules", "Line 2"] + [f"Rule {i}" for i in range(3, 30)]
    _write_note(vault, "3.1. Career/Section Instructions.md", "\n".join(sec_lines))
    _write_note(
        vault,
        "3.1. Career/Tracker.md",
        "---\ninstructions:\n  - Track only real leads.\n---\n# Pipeline\n*Sorted newest first.*\n\n- Lead 1\n",
    )

    tok = set_hitl_execution_context(conversation_id="conv-partial-sec", thread_id="conv-partial-sec")
    try:
        # Partial read of Section Instructions + partial read of Tracker leaves Section Instructions UNSATISFIED.
        shared_module.read_file.invoke(
            {"file_path": "3.1. Career/Section Instructions.md", "start_line": 1, "end_line": 10}
        )
        shared_module.read_file.invoke(
            {"file_path": "3.1. Career/Tracker.md", "start_line": 7, "end_line": 8}
        )
        blocked = shared_module.modify_file.invoke(
            {
                "file_path": "3.1. Career/Tracker.md",
                "target": "- Lead 1",
                "replacement": "- Lead 1\n- Lead 2",
                "reasoning": "Partial section read must still block",
            }
        )
        assert blocked.startswith("⚠️ Write Blocked")
        assert "3.1. Career/Section Instructions.md" in blocked
        # Frontmatter and `# Pipeline` WERE already exposed by Pillar 1 on Tracker's partial slice!
        assert "Track only real leads." not in blocked
        assert "Sorted newest first." not in blocked

        # Reading the FULL `Section Instructions.md` in a fresh scope satisfies the gate on the 1st write!
        clear_seen_instructions("conv-partial-sec")
        shared_module.read_file.invoke({"file_path": "3.1. Career/Section Instructions.md"})
        shared_module.read_file.invoke({"file_path": "3.1. Career/Tracker.md", "start_line": 7, "end_line": 8})
        passed = shared_module.modify_file.invoke(
            {
                "file_path": "3.1. Career/Tracker.md",
                "target": "- Lead 1",
                "replacement": "- Lead 1\n- Lead 2",
                "reasoning": "Full section read + partial slice satisfies gate",
            }
        )
        assert "✅ Surgical modification staged to HITL queue" in passed
    finally:
        reset_hitl_execution_context(tok)


def test_scope_isolation_and_content_hash_invalidation_and_nonmatch_no_pollution(
    isolated_env: dict[str, Path],
) -> None:
    """Verify parent vs subagent scope isolation, SHA-256 invalidation on disk/HITL edits, and target miss safety."""
    vault = isolated_env["vault"]
    sec_path = _write_note(vault, "6. Engineering/Section Instructions.md", "# Eng Rules\nRule v1.\n")
    _write_note(vault, "6. Engineering/Project.md", "---\ninstructions:\n  - Keep roadmap clean.\n---\n# Tasks\n- [ ] A\n")

    # 1. Parent reads everything cleanly.
    parent_tok = set_hitl_execution_context(conversation_id="conv-iso", thread_id="conv-iso")
    try:
        shared_module.read_file.invoke({"file_path": "6. Engineering/Section Instructions.md"})
        shared_module.read_file.invoke({"file_path": "6. Engineering/Project.md"})

        # Non-matching target must return exact target-not-found error without mutating ledger or staging.
        clear_seen_instructions("conv-iso")
        miss_res = shared_module.modify_file.invoke(
            {
                "file_path": "6. Engineering/Project.md",
                "target": "NONEXISTENT_SNIPPET",
                "replacement": "X",
                "reasoning": "Should fail target lookup",
            }
        )
        assert "Error: `target` text was not found" in miss_res
        # Ledger must remain empty so next real write still hits the gate!
        still_blocked = shared_module.modify_file.invoke(
            {
                "file_path": "6. Engineering/Project.md",
                "target": "- [ ] A",
                "replacement": "- [x] A",
                "reasoning": "First real write must still block",
            }
        )
        assert still_blocked.startswith("⚠️ Write Blocked")

        # 2. Fresh subagent scope (`conv-iso:subagent-1`) does NOT inherit parent's seen ledger.
        sub_tok = set_hitl_execution_context(conversation_id="conv-iso", thread_id="conv-iso:subagent-1")
        try:
            sub_blocked = shared_module.modify_file.invoke(
                {
                    "file_path": "6. Engineering/Project.md",
                    "target": "- [ ] A",
                    "replacement": "- [x] A",
                    "reasoning": "Subagent must have its own scope",
                }
            )
            assert sub_blocked.startswith("⚠️ Write Blocked")
            assert "Rule v1." in sub_blocked
        finally:
            reset_hitl_execution_context(sub_tok)

        # 3. Updating `Section Instructions.md` on disk invalidates parent's cached digest.
        sec_path.write_text("# Eng Rules\nRule v2 updated on disk.\n", encoding="utf-8")
        reblocked_disk = shared_module.modify_file.invoke(
            {
                "file_path": "6. Engineering/Project.md",
                "target": "- [ ] A",
                "replacement": "- [x] A",
                "reasoning": "Disk instruction edit must re-trigger gate",
            }
        )
        assert reblocked_disk.startswith("⚠️ Write Blocked")
        assert "Rule v2 updated on disk." in reblocked_disk

        # 4. Staging an HITL edit on `Section Instructions.md` ALSO invalidates the cached digest.
        hq.add_transaction(
            agent_name="nexus_agent",
            action_type="modify",
            target_file="Vault/6. Engineering/Section Instructions.md",
            proposed_content="# Eng Rules\nRule v3 staged in HITL.\n",
            original_content="# Eng Rules\nRule v2 updated on disk.\n",
            reasoning="Update section rules",
        )
        reblocked_hitl = shared_module.modify_file.invoke(
            {
                "file_path": "6. Engineering/Project.md",
                "target": "- [ ] A",
                "replacement": "- [x] A",
                "reasoning": "HITL instruction edit must re-trigger gate",
            }
        )
        assert reblocked_hitl.startswith("⚠️ Write Blocked")
        assert "Rule v3 staged in HITL." in reblocked_hitl
    finally:
        reset_hitl_execution_context(parent_tok)


def test_same_batch_parallel_calls_cannot_bypass_gate_and_deduplicate_section_text(
    isolated_env: dict[str, Path],
) -> None:
    """Within one `ToolNode` batch, sibling writes/reads cannot unlock each other; next batch succeeds."""
    vault = isolated_env["vault"]
    _write_note(vault, "3.1. Career/Section Instructions.md", "# Career Rules\nStrict 0-2 YOE filter.\n")
    _write_note(vault, "3.1. Career/Note.md", "# Header\nOld body.\n")

    tok = set_hitl_execution_context(conversation_id="conv-batch", thread_id="conv-batch")
    try:
        # Batch 1: Two parallel `create_file` calls in the same folder -> BOTH blocked, 2nd deduplicates full text.
        b1 = set_instruction_batch_id("batch-1")
        try:
            c1 = shared_module.create_file.invoke(
                {"file_path": "3.1. Career/Job1.md", "content": "Job 1", "reasoning": "Save 1"}
            )
            c2 = shared_module.create_file.invoke(
                {"file_path": "3.1. Career/Job2.md", "content": "Job 2", "reasoning": "Save 2"}
            )
        finally:
            reset_instruction_batch_id(b1)

        assert c1.startswith("⚠️ Write Blocked")
        assert "Strict 0-2 YOE filter." in c1
        assert c2.startswith("⚠️ Write Blocked")
        assert "already returned in an earlier blocked tool result in this batch" in c2
        assert "Strict 0-2 YOE filter." not in c2
        assert hq.get_pending_transactions() == []

        # Batch 2 (next LLM turn): Both retries succeed!
        b2 = set_instruction_batch_id("batch-2")
        try:
            p1 = shared_module.create_file.invoke(
                {"file_path": "3.1. Career/Job1.md", "content": "Job 1", "reasoning": "Save 1"}
            )
            p2 = shared_module.create_file.invoke(
                {"file_path": "3.1. Career/Job2.md", "content": "Job 2", "reasoning": "Save 2"}
            )
        finally:
            reset_instruction_batch_id(b2)
        assert "✅ File creation staged to HITL queue" in p1
        assert "✅ File creation staged to HITL queue" in p2

        # Parallel `[read_file, modify_file]` in a fresh batch: `modify_file` must still block in same batch!
        clear_seen_instructions("conv-batch")
        b3 = set_instruction_batch_id("batch-3")
        try:
            shared_module.read_file.invoke({"file_path": "3.1. Career/Section Instructions.md"})
            same_turn_mod = shared_module.modify_file.invoke(
                {
                    "file_path": "3.1. Career/Note.md",
                    "target": "Old body.",
                    "replacement": "New body.",
                    "reasoning": "Same-batch read + write must block",
                }
            )
        finally:
            reset_instruction_batch_id(b3)
        assert same_turn_mod.startswith("⚠️ Write Blocked")

        b4 = set_instruction_batch_id("batch-4")
        try:
            next_turn_mod = shared_module.modify_file.invoke(
                {
                    "file_path": "3.1. Career/Note.md",
                    "target": "Old body.",
                    "replacement": "New body.",
                    "reasoning": "Next-turn write after seeing read succeeds",
                }
            )
        finally:
            reset_instruction_batch_id(b4)
        assert "✅ Surgical modification staged to HITL queue" in next_turn_mod
    finally:
        reset_hitl_execution_context(tok)


# ── 4. Pillar 3: Subagent Auto-Hydration, Cleanup & Cache Invariant ──────────

def test_spawn_subagent_autohydrates_section_instructions_from_context_files_and_task_prompt(
    isolated_env: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify `spawn_subagent` auto-injects ancestor Section Instructions, lets Turn-1 writes pass, and cleans up."""
    vault = isolated_env["vault"]
    _write_note(vault, "3. Operations/3.1. Career/Section Instructions.md", "# Career Rules\nStrict 0-2 YOE filter.\n")
    _write_note(
        vault,
        "3. Operations/3.1. Career/Campaign.md",
        "---\ninstructions:\n  - Keep summary updated.\n---\n# Summary\n- Status: Open\n",
    )
    _write_note(vault, "6. Engineering/Section Instructions.md", "# Eng Rules\nKeep ADR synced.\n")
    _write_note(vault, "6. Engineering/Roadmap.md", "# Roadmap\n- [ ] Task X\n")
    _write_note(vault, "PlainNote.md", "# Plain\nGroceries list.\n")

    captured_prompts: list[str] = []
    write_results: list[str] = []
    sub_scopes_during_run: list[str] = []

    def _fake_invoke_with_turn1_write(**kwargs):
        msgs = kwargs["messages"]
        assert isinstance(msgs[1], HumanMessage)
        captured_prompts.append(msgs[1].content)
        sub_scopes_during_run.append(ig.get_active_instruction_scope_id())

        # Execute a Turn-1 write INSIDE the active subagent execution context!
        prompt_text = msgs[1].content
        if "Update Campaign status" in prompt_text:
            res = shared_module.modify_file.invoke(
                {
                    "file_path": "3. Operations/3.1. Career/Campaign.md",
                    "target": "- Status: Open",
                    "replacement": "- Status: Active",
                    "reasoning": "Turn-1 subagent update",
                }
            )
            write_results.append(res)
        elif "Create new career listing" in prompt_text:
            res = shared_module.create_file.invoke(
                {
                    "file_path": "3. Operations/3.1. Career/Saved/Acme.md",
                    "content": "# Acme\n",
                    "reasoning": "Turn-1 subagent create from prompt discovery",
                }
            )
            write_results.append(res)
        return AIMessage(content="Done.")

    monkeypatch.setattr(subagent_mod, "_invoke_llm_with_resilience", _fake_invoke_with_turn1_write)

    conv_id = chats_db.create_conversation(title="Subagent Hydration Thread")
    ctx_tok = set_hitl_execution_context(conversation_id=conv_id, thread_id=conv_id)
    trace_tok = set_trace_thread_id(conv_id)
    try:
        # Case A: Explicit `context_files` omits `Section Instructions.md` -> auto-hydrated & Turn-1 write passes!
        out_a = subagent_mod.spawn_subagent.invoke(
            {
                "task_prompt": "Update Campaign status to Active.",
                "model_tier": "low",
                "context_files": ["3. Operations/3.1. Career/Campaign.md"],
            }
        )
        assert "Done." in out_a
        assert "Auto-Hydrated Section Instructions" in captured_prompts[-1]
        assert "Strict 0-2 YOE filter." in captured_prompts[-1]
        assert "✅ Surgical modification staged to HITL queue" in write_results[-1]

        # When `Section Instructions.md` IS already explicitly in `context_files`, it is NOT duplicated.
        subagent_mod.spawn_subagent.invoke(
            {
                "task_prompt": "Inspect Campaign.",
                "model_tier": "low",
                "context_files": [
                    "3. Operations/3.1. Career/Campaign.md",
                    "3. Operations/3.1. Career/Section Instructions.md",
                ],
            }
        )
        assert captured_prompts[-1].count("Strict 0-2 YOE filter.") == 1

        # Case B: `context_files=None`, `task_prompt` references `3.1. Career` and `[[Roadmap]]` -> auto-discovers BOTH!
        out_b = subagent_mod.spawn_subagent.invoke(
            {
                "task_prompt": "Create new career listing in `3. Operations/3.1. Career/Saved/` and check [[Roadmap]].",
                "model_tier": "low",
            }
        )
        assert "Done." in out_b
        assert "Strict 0-2 YOE filter." in captured_prompts[-1]
        assert "Keep ADR synced." in captured_prompts[-1]
        assert "✅ File creation staged to HITL queue" in write_results[-1]

        # Case C: Plain `task_prompt` touching no governed section gets NO `# Pre-Hydrated Disk Context` bloat.
        subagent_mod.spawn_subagent.invoke(
            {
                "task_prompt": "Summarize general notes about groceries.",
                "model_tier": "low",
            }
        )
        assert not captured_prompts[-1].startswith("# Pre-Hydrated Disk Context")
        assert captured_prompts[-1] == "Summarize general notes about groceries."

        # Verify every ephemeral subagent scope was cleaned up in `finally:`.
        for scope in sub_scopes_during_run:
            assert scope not in ig._SEEN_RULES

        # Case D: Hallucinated `context_files` still fails fast before LLM invocation.
        called_after = len(captured_prompts)
        bad_out = subagent_mod.spawn_subagent.invoke(
            {
                "task_prompt": "Check nonexistent file.",
                "model_tier": "low",
                "context_files": ["3. Operations/3.1. Career/Phantom.md"],
            }
        )
        assert "Fail-Fast Context Hydration Error" in bad_out
        assert len(captured_prompts) == called_after

        # Verify parent conversation deletion cleans up parent scope and any residual child scopes cleanly.
        ig._SEEN_RULES[conv_id] = {("a.md", "frontmatter_instructions", "123"): "__direct__"}
        ig._SEEN_RULES[f"{conv_id}:subagent-99"] = {("a.md", "frontmatter_instructions", "123"): "__direct__"}
        chats_db.delete_conversation(conv_id)
        assert conv_id not in ig._SEEN_RULES
        assert f"{conv_id}:subagent-99" not in ig._SEEN_RULES
    finally:
        reset_trace_thread_id(trace_tok)
        reset_hitl_execution_context(ctx_tok)


def test_root_instructions_kv_prefix_stays_byte_identical_across_guard_operations(
    isolated_env: dict[str, Path],
) -> None:
    """Confirm `inject_root_instructions()` stays byte-identical before and after reads, gate blocks, and hydrations."""
    vault = isolated_env["vault"]
    _write_note(vault, "3.1. Career/Section Instructions.md", "# Rules\nAlways verify.\n")
    _write_note(vault, "3.1. Career/Doc.md", "---\ninstructions:\n  - Rule A\n---\n# H\nLine\n")

    baseline = inject_root_instructions()
    tok = set_hitl_execution_context(conversation_id="conv-kv", thread_id="conv-kv")
    try:
        shared_module.read_file.invoke({"file_path": "3.1. Career/Doc.md", "start_line": 5, "end_line": 7})
        shared_module.modify_file.invoke(
            {"file_path": "3.1. Career/Doc.md", "target": "Line", "replacement": "Updated", "reasoning": "KV check"}
        )
        shared_module.hydrate_subagent_context_files(["3.1. Career/Doc.md"], task_prompt="Read Doc")
    finally:
        reset_hitl_execution_context(tok)

    after = inject_root_instructions()
    assert after == baseline


def test_discover_section_instructions_ignores_fenced_code_blocks(
    isolated_env: dict[str, Path],
) -> None:
    """Fenced code/draft blocks in `task_prompt` (incl. 4-backtick wrappers) must not trigger section auto-hydration."""
    vault = isolated_env["vault"]
    _write_note(vault, "1. Core/1.1. Philosophy/Section Instructions.md", "# Philosophy Rules\nRule 1.\n")
    _write_note(vault, "3. Operations/3.1. Career Strategy/Section Instructions.md", "# Career Rules\nRule 2.\n")

    fenced_only_prompt = (
        "Create `Draft - Orchestrator Instructions.md` at Vault root with this content:\n\n"
        "````markdown\n"
        "# Orchestrator Draft\n"
        "See [[1. Core/1.1. Philosophy/Section Instructions]] or `3. Operations/3.1. Career Strategy/Section Instructions.md`.\n"
        "```text\n"
        "3.1. Career Strategy\n"
        "1.1. Philosophy\n"
        "```\n"
        "````\n"
    )
    assert ig.discover_section_instructions_for_subagent(fenced_only_prompt, vault_path=vault) == []

    # Prose outside fenced blocks still triggers discovery, while fenced-only sections remain ignored.
    mixed_prompt = (
        "Audit `3.1. Career Strategy` and include this example:\n\n"
        "```markdown\n"
        "Example mention of 1.1. Philosophy inside a fence.\n"
        "```\n"
    )
    discovered = ig.discover_section_instructions_for_subagent(mixed_prompt, vault_path=vault)
    assert discovered == ["3. Operations/3.1. Career Strategy/Section Instructions.md"]
