#!/usr/bin/env python3
"""
scripts/audit_career_drift.py

Deterministic Tier-1 Career Document Drift Auditor.
Performs zero-cost heuristic checks across the Nexus career document cluster:
1. Timestamp & Staleness Hierarchy Check
2. Platform Profile Character Constraint Validation
3. Core Skill & Keyword Coverage across Master Resume and Platform Profiles
4. Canonical Links & Contact Consistency
5. Flagship Telemetry Parity Check
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Ensure UTF-8 output encoding across Windows terminals
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Resolve base directories
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
VAULT_DIR = REPO_ROOT / "Vault"
CAREER_DIR = VAULT_DIR / "3. Operations & Wealth" / "3.1. Career Strategy & Revenue"
EVIDENCE_DIR = CAREER_DIR / "3.1.3. Professional Portfolio & Evidence"
RESUMES_DIR = EVIDENCE_DIR / "Resumes"
PORTFOLIO_REPO = REPO_ROOT.parent / "portfolio"
TELEMETRY_FILE = PORTFOLIO_REPO / "src" / "data" / "nexusTelemetry.ts"

# Target Documents
DOCS = {
    "my_skills": CAREER_DIR / "My Skills.md",
    "resume_master": RESUMES_DIR / "Resume - Master.md",
    "resume_extended": RESUMES_DIR / "Resume - Master (Extended).md",
    "platform_profiles": EVIDENCE_DIR / "Platform Profiles.md",
    "portfolio_hub": EVIDENCE_DIR / "Portfolio Hub.md",
    "war_room": CAREER_DIR / "Job Hunt War Room.md",
    "employer_skills": CAREER_DIR / "Employer Skill Requirements.md",
    "telemetry": TELEMETRY_FILE,
}

# Platform Profile Constraints (max allowed characters)
PROFILE_CONSTRAINTS = {
    "LinkedIn Headline": {
        "pattern": r"### Headline\s*\n\*Constraint:[^\n]*\*\s*\n```text\s*\n([\s\S]*?)\n```",
        "max_len": 220,
    },
    "LinkedIn About": {
        "pattern": r"### About\s*\n\*Constraint:[^\n]*\*\s*\n```text\s*\n([\s\S]*?)\n```",
        "max_len": 2600,
    },
    "LinkedIn Project": {
        "pattern": r"- \*\*Description\*\* \(\*Constraint: Max \d+ characters\*\):\s*\n```text\s*\n([\s\S]*?)\n```",
        "max_len": 2000,
    },
    "Handshake Full Bio": {
        "pattern": r"### Summary / Bio \(Full\)\s*\n\*Constraint:[^\n]*\*\s*\n```text\s*\n([\s\S]*?)\n```",
        "max_len": 1000,
    },
    "Handshake Short Bio": {
        "pattern": r"### Short Summary\s*\n\*Constraint:[^\n]*\*\s*\n```text\s*\n([\s\S]*?)\n```",
        "max_len": 300,
    },
    "Handshake Project": {
        "pattern": r"- \*\*Description\*\* \(\*Constraint: Max 500 characters\*\):\s*\n```text\s*\n([\s\S]*?)\n```",
        "max_len": 500,
    },
    "Wellfound/YC One-liner": {
        "pattern": r"### Short Bio / One-liner\s*\n\*Constraint:[^\n]*\*\s*\n```text\s*\n([\s\S]*?)\n```",
        "max_len": 160,
    },
    "Wellfound/YC Pitch": {
        "pattern": r"### About / Cover Letter Pitch\s*\n\*Constraint:[^\n]*\*\s*\n```text\s*\n([\s\S]*?)\n```",
        "max_len": 1000,
    },
}

# Core Keywords to verify across downstream documents
CORE_SKILLS = [
    "LangGraph",
    "Deterministic Pre-flight Hydration",
    "Domain Ontology",
    "LLM-as-a-Judge",
    "HITL",
    "FastAPI",
    "Next.js 16",
    "TypeScript",
    "Python",
    "SiliSlick",
    "HIPAA",
]

CANONICAL_LINKS = [
    "williamvolodarsky.com",
    "bill@williamvolodarsky.com",
    "github.com/brolodarsky",
]


def format_timestamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def run_audit():
    print("=" * 70)
    print(" [NEXUS CAREER CLUSTER DRIFT AUDITOR - Tier 1]")
    print("=" * 70)

    issues = []
    warnings = []
    passes = []

    # 1. Existence & Timestamp Check
    print("\n[1] DOCUMENT REPOSITORY & STALENESS HIERARCHY")
    print("-" * 70)
    mtimes = {}
    contents = {}

    for key, path in DOCS.items():
        if not path.exists():
            if key == "telemetry":
                warnings.append(f"Portfolio repo not found at: {path}")
                print(f"  [WARN] {key:18} : Missing ({path.name})")
            else:
                issues.append(f"Missing required career file: {path}")
                print(f"  [FAIL] {key:18} : {path}")
            continue

        stat = path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime)
        mtimes[key] = mtime
        try:
            contents[key] = path.read_text(encoding="utf-8")
            print(f"  [PASS] {key:18} : {format_timestamp(mtime)} ({path.name})")
        except Exception as e:
            issues.append(f"Failed to read {path}: {e}")
            print(f"  [FAIL] {key:18} : Read failure ({e})")

    # Check Waterfall Staleness
    if "my_skills" in mtimes and "platform_profiles" in mtimes:
        if mtimes["my_skills"] > mtimes["platform_profiles"]:
            diff_hours = (mtimes["my_skills"] - mtimes["platform_profiles"]).total_seconds() / 3600
            if diff_hours > 1.0:
                warnings.append(
                    f"My Skills.md is newer than Platform Profiles.md ({diff_hours:.1f}h diff). Verify profile copy."
                )

    if "resume_master" in mtimes and "platform_profiles" in mtimes:
        if mtimes["resume_master"] > mtimes["platform_profiles"]:
            diff_hours = (mtimes["resume_master"] - mtimes["platform_profiles"]).total_seconds() / 3600
            if diff_hours > 1.0:
                warnings.append(
                    f"Resume - Master.md is newer than Platform Profiles.md ({diff_hours:.1f}h diff). Check for unsynced copy."
                )

    # 2. Platform Profile Character Length Checks
    print("\n[2] PLATFORM PROFILE CHARACTER CONSTRAINTS")
    print("-" * 70)
    if "platform_profiles" in contents:
        pp_text = contents["platform_profiles"]
        for block_name, config in PROFILE_CONSTRAINTS.items():
            match = re.search(config["pattern"], pp_text)
            if match:
                snippet = match.group(1).strip()
                char_count = len(snippet)
                max_len = config["max_len"]
                if char_count > max_len:
                    issues.append(
                        f"Platform Profile '{block_name}' exceeds limit: {char_count}/{max_len} chars"
                    )
                    print(f"  [FAIL] {block_name:24} : {char_count}/{max_len} chars (OVERFLOW by {char_count - max_len})")
                else:
                    passes.append(f"Platform Profile '{block_name}' within limit ({char_count}/{max_len})")
                    print(f"  [PASS] {block_name:24} : {char_count}/{max_len} chars (Remaining: {max_len - char_count})")
            else:
                warnings.append(f"Could not parse codeblock for '{block_name}' in Platform Profiles.md")
                print(f"  [WARN] {block_name:24} : Pattern not matched in doc")
    else:
        warnings.append("Skipping character checks: Platform Profiles.md not loaded")

    # 3. Core Keyword & Skill Coverage Check
    print("\n[3] CORE KEYWORD & SKILL COVERAGE")
    print("-" * 70)
    check_targets = {
        "Master Resume": contents.get("resume_master", ""),
        "Extended Resume": contents.get("resume_extended", ""),
        "Platform Profiles": contents.get("platform_profiles", ""),
        "Portfolio Hub": contents.get("portfolio_hub", ""),
        "Job Hunt War Room": contents.get("war_room", ""),
    }

    for skill in CORE_SKILLS:
        missing_in = []
        for doc_name, doc_text in check_targets.items():
            if not doc_text:
                continue
            if skill.lower() not in doc_text.lower():
                missing_in.append(doc_name)
        
        if missing_in:
            warnings.append(f"Skill '{skill}' not mentioned in: {', '.join(missing_in)}")
            print(f"  [WARN] {skill:34} : Missing in [{', '.join(missing_in)}]")
        else:
            passes.append(f"Skill '{skill}' is present across all career documents")
            print(f"  [PASS] {skill:34} : Synchronized across all 5 docs")

    # 4. Canonical Links & Contact Information
    print("\n[4] CANONICAL LINKS & CONTACT VERIFICATION")
    print("-" * 70)
    for link in CANONICAL_LINKS:
        missing_link = []
        for doc_name in ["Master Resume", "Extended Resume", "Platform Profiles"]:
            text = check_targets.get(doc_name, "")
            if text and link.lower() not in text.lower():
                missing_link.append(doc_name)

        if missing_link:
            issues.append(f"Canonical link '{link}' missing from: {', '.join(missing_link)}")
            print(f"  [FAIL] {link:34} : Missing in [{', '.join(missing_link)}]")
        else:
            passes.append(f"Canonical link '{link}' verified")
            print(f"  [PASS] {link:34} : Verified across master resumes & profiles")

    # 5. Telemetry & Metrics Verification
    print("\n[5] VAULT NODE COUNT & FLAGSHIP TELEMETRY")
    print("-" * 70)
    vault_notes = [p for p in VAULT_DIR.rglob("*.md") if ".git" not in p.parts]
    actual_note_count = len(vault_notes)
    print(f"  [INFO] Actual Vault Notes Count   : {actual_note_count} nodes")

    if "telemetry" in contents:
        telemetry_text = contents["telemetry"]
        match_nodes = re.search(r"totalNodes:\s*(\d+)", telemetry_text)
        if match_nodes:
            reported_nodes = int(match_nodes.group(1))
            if abs(reported_nodes - actual_note_count) > 100:
                warnings.append(
                    f"Telemetry totalNodes ({reported_nodes}) has drifted from actual ({actual_note_count})"
                )
                print(f"  [WARN] Telemetry totalNodes       : {reported_nodes} (Drifted from {actual_note_count})")
            else:
                passes.append("Telemetry node count aligned")
                print(f"  [PASS] Telemetry totalNodes       : {reported_nodes} (Within tolerance of {actual_note_count})")

    # Final Summary Report
    print("\n" + "=" * 70)
    print(" [AUDIT SUMMARY & ACTION VERDICT]")
    print("=" * 70)
    print(f"  [+] Passed Checks : {len(passes)}")
    print(f"  [?] Warnings      : {len(warnings)}")
    print(f"  [-] Critical Issues: {len(issues)}")
    print("-" * 70)

    if issues:
        print("\n[-] CRITICAL DRIFT DETECTED:")
        for idx, item in enumerate(issues, 1):
            print(f"  {idx}. {item}")

    if warnings:
        print("\n[?] NOTABLE WARNINGS & SYNC RECOMMENDATIONS:")
        for idx, item in enumerate(warnings, 1):
            print(f"  {idx}. {item}")

    if not issues and not warnings:
        print("\n[PERFECT ALIGNMENT] All career documents are 100% synchronized with zero drift!")
    elif not issues:
        print("\n[HEALTHY] No critical blocking issues. Address warnings during next weekly review.")
    else:
        print("\n[ACTION REQUIRED] Correct the critical issues above to maintain profile integrity.")
    print("=" * 70 + "\n")

    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(run_audit())
