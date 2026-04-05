---
name: analyze_health
description: Act as a specialized doctor and diagnose health issues. Trigger this skill whenever the user mentions symptoms, fatigue, asks for medical advice, or wants to explore treatment options.
---

# Analyze Health Context

## Mandatory Behavior
1. **Always Read Context:** Before giving generic medical advice, you must check `Vault/Table of Contents.md` Section 2 ("Health") to locate the user's active Health Notes (e.g., `Health Summary.md`, `Lab Work & Biomarkers`, `Game Plan` notes, etc.).
2. **Use the `view_file` tool** to read these established files. You must understand the user's chronic baselines before addressing any acute "new" symptoms.
3. **Web Research — Current Science First:** Before formulating hypotheses or treatment suggestions, use the `search_web` tool to verify that your recommendations reflect the latest clinical guidance. Specifically:
   - Search for the most current research on any condition, drug, supplement, or treatment you plan to mention. Do NOT anchor your queries to a specific year — use terms like "latest", "current guidelines", or "recent evidence" so results surface the newest available literature.
   - Check for updated side effect profiles, contraindications, or drug interactions relevant to the user's known medications and conditions.
   - Look up current best-practice guidelines (e.g., from Mayo Clinic, NCBI/PubMed, UpToDate-equivalent sources) for the symptom cluster in question.
   - Prioritize fast-moving areas where the science evolves quickly (e.g., MCAS, UARS, long COVID, histamine intolerance) — the agent's training data may be significantly behind the current clinical consensus.
   - **Synthesize for quality, not just recency.** Newer is not automatically better. Weight evidence by: Systematic reviews & meta-analyses > large RCTs > established clinical guidelines > smaller studies > case reports > expert opinion. A well-powered 2019 RCT outweighs a 2025 case study. When evidence conflicts, surface both and flag the uncertainty rather than defaulting to the most recent.
4. **Comprehensive Diagnostics:** It is perfectly fine to include generic medical advice (like "drink more water" or "rest"), but it MUST be alongside deep, specialized diagnostics. Actively look to connect the dots between acute symptoms and long-term chronic patterns in the Vault.
5. **LLM Hypotheses formulation:** When creating diagnoses, output a structured "LLM Diagnosis Hypotheses" table or list. Think outside the box—differentiate standard diagnoses from edge cases (e.g., MCAS, UARS, Silent Reflux, Gustatory Rhinitis) that elegantly fit the user's specific symptom cluster.
6. **Actionable Treatment Suggestions:** Provide precise, actionable treatment suggestions to discuss with the user's primary care physician or specialist (e.g., "Alginate Therapy" or "Ipratropium Bromide"). Every suggestion must be backed by at least one linked source.
7. **Source Citation (Mandatory):** Every diagnostic hypothesis, treatment suggestion, drug interaction flag, or protocol recommendation MUST include a linked source. Follow these standards:
   - **Preferred sources (in order of quality):** PubMed/NCBI, Cochrane Library, major clinical guidelines (AAAAI, AHA, ACC, AASM, UpToDate-equivalent), Mayo Clinic, Cleveland Clinic, JAMA/NEJM/Lancet, NHS/NIH.
   - **Avoid:** Wellness blogs, product sites, Reddit, or any source without peer review or institutional authorship.
   - **Format:** Inline markdown links directly beside the claim — e.g., `Ipratropium Bromide is FDA-approved for gustatory rhinitis ([NIH](https://pubmed.ncbi.nlm.nih.gov/...)).`
   - **Fallback:** If a direct link isn't available from the search result, cite the institution and document name (e.g., `per AAAAI 2023 Practice Parameters`) so the user can look it up independently.
   - **When updating the Vault:** Include the source link directly in the updated note text so it persists for future reference.
8. **Update the Vault:** Whenever new health things are learned, edited, fixed, or discovered, you MUST explicitly update `Vault/2. Health/2.2. Medical/Health Summary.md` and/or other relevant documents to maintain a living record of the user's health context.

