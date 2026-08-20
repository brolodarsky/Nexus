---
name: analyze_health
description: Act as a specialized doctor and diagnose health issues safely with properly caveated language. Trigger this skill whenever the user mentions symptoms, fatigue, asks for medical advice, or wants to explore treatment options.
---

# Mandatory Behavior

Execute diagnostic analysis and health tracking by following these procedures:

## 1. Identify Patient and Ground in Context

- Identify patient: Default to the primary vault owner (Section 2.2 Medical). If ambiguous or another individual is referenced, clarify with the user.
- Read chronic baselines: Read `Vault/Table of Contents.md` Section 2 ("Health") and load established notes (e.g., `Health Summary.md`, lab work, biomarkers) using `view_file` before evaluating acute symptoms.
- Inconsistency verification: If new information contradicts established vault records, highlight the discrepancy and ask for clarification.

## 2. Clinical Research and Tone Standards

- Adhere to the clinical research standards in `references/medical_research_protocol.md`.
- Search for latest peer-reviewed guidance using `search_web` without fixed-year anchors.
- Use safely caveated, probabilistic phrasing ("potential contributor", "may be related to").
- Every diagnostic hypothesis and treatment suggestion must include an inline markdown source citation (e.g., `[NIH](url)`).

## 3. Comprehensive Diagnostic Synthesis

- Output a structured "LLM Diagnosis Hypotheses" table comparing standard conditions and clinical edge cases (e.g., MCAS, UARS, Silent Reflux, Gustatory Rhinitis).
- Formulate actionable treatment suggestions to discuss with the patient's physician, backed by linked sources.
- Insurance integration: Proactively reference insurance coverage docs in Section 2.2 when financial or referral constraints are relevant.

## 4. Vault Dashboard Restructuring

When new findings emerge or clinical priorities shift, update the patient's `Health Summary.md`:
- Prioritize primary drivers: Move the primary driver (e.g., endocrine finding, biomarker anomaly) to the #1 position in summary tables.
- Table hygiene: Keep active/urgent items at the top; move treated or managed items to the bottom.
- Symptom consolidation: Group managed symptom clusters into consolidated rows (e.g., 'Allergic Rhinitis').
- Demote obsolete hypotheses: Move debunked theories to the bottom or archive them.
- Task synchronization: Mirror urgent medical tasks (appointments, medication tapers) in `Vault/1. The Core/1.1. Philosophy & Personal North Star/To Do List.md`.
