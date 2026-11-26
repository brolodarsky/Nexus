"""
test_vault_search.py — Unit tests for single-keyword and multi-keyword Vault search (`vault_reader.search_within`, `@tool search_vault`, and CLI `--search`).
"""

import sys
from pathlib import Path

import pytest

from nexus.shared_tools import shared as shared_module
from nexus.shared_tools import vault_reader


@pytest.fixture
def sample_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create an isolated Vault directory tree with tagged/untagged notes for search tests."""
    vault_dir = tmp_path / "Vault"
    career_dir = vault_dir / "3. Operations" / "3.1. Career"
    core_dir = vault_dir / "1. Core"
    career_dir.mkdir(parents=True)
    core_dir.mkdir(parents=True)

    (career_dir / "Events Hub.md").write_text(
        "---\ntags: [career, networking]\n---\nTracking NYC AI meetup, Luma invites, and hackathon schedules.\n",
        encoding="utf-8",
    )
    (career_dir / "Luma Note.md").write_text(
        "---\ntags: [networking]\n---\nRegistered via Luma for Bond AI Builder Nights.\n",
        encoding="utf-8",
    )
    (core_dir / "Tasks.md").write_text(
        "---\ntags: [ops]\n---\nAttend Thursday AI hackathon demo day.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(vault_reader, "VAULT_PATH", vault_dir)
    return vault_dir


def test_search_within_preserves_single_keyword_format(sample_vault: Path) -> None:
    """Single-keyword search keeps exact legacy output format and respects path scoping."""
    out = vault_reader.search_within("luma")
    assert out.startswith("Found 'luma' in 2 files across the entire vault:")
    assert "Events Hub.md" in out
    assert "Luma Note.md" in out
    assert "[matched:" not in out

    miss = vault_reader.search_within("nonexistent_term_xyz", root_path="1. Core")
    assert miss == "No results found for keyword: 'nonexistent_term_xyz' in '1. Core'."


def test_search_within_and_tool_multi_keyword_dedup_ranking_and_filters(sample_vault: Path) -> None:
    """Multi-keyword search deduplicates files, ranks by match count, and respects tags/path filters."""
    out = shared_module.search_vault.invoke(
        {"keywords": ["meetup", "Luma", "hackathon", "luma", "  "]}
    )
    assert out.startswith("Found matches for ['meetup', 'Luma', 'hackathon'] in 3 files across the entire vault:")

    lines = [line for line in out.splitlines() if line.startswith("- ")]
    assert len(lines) == 3
    # Events Hub matches all 3 distinct terms, so it ranks first
    assert "Events Hub.md [matched: meetup, Luma, hackathon]:" in lines[0]
    # Luma Note and Tasks match 1 term each, ordered alphabetically
    assert "Tasks.md [matched: hackathon]:" in lines[1]
    assert "Luma Note.md [matched: Luma]:" in lines[2]

    # Tag filter narrows multi-keyword sweep
    tagged = vault_reader.search_within(
        keywords=["meetup", "hackathon"],
        tags=["ops"],
    )
    assert "in 1 files across the entire vault:" in tagged
    assert "Tasks.md" in tagged
    assert "Events Hub.md" not in tagged

    # Path filter narrows multi-keyword sweep
    scoped = vault_reader.search_within(
        keywords=["meetup", "hackathon"],
        root_path="1. Core",
    )
    assert "in 1 files in '1. Core':" in scoped
    assert "Tasks.md" in scoped

    # Empty keyword validation
    err = vault_reader.search_within(keyword="   ", keywords=["", "  "])
    assert err.startswith("Error: Provide at least one non-empty keyword")


def test_vault_reader_cli_search_supports_multiple_terms(sample_vault: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """Verify `python -m nexus.shared_tools.vault_reader --search term1 term2` runs multi-keyword search."""
    monkeypatch.setattr(sys, "argv", ["vault_reader", "--search", "meetup", "Luma", "--path", "3. Operations"])
    vault_reader.main()
    stdout = capsys.readouterr().out
    assert "Found matches for ['meetup', 'Luma'] in 2 files in '3. Operations':" in stdout
    assert "Events Hub.md [matched: meetup, Luma]:" in stdout
