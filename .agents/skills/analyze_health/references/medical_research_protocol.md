# Clinical Research, Citation, and Tone Protocol

Standing standards for health, psychiatric, and diagnostic analysis.

---

## 1. Web Research & Current Science

- Ground hypotheses and recommendations in the latest peer-reviewed clinical consensus using `search_web`.
- Do not anchor search queries to a single year; use dynamic qualifiers like "latest", "current guidelines", or "recent evidence".
- Verify side-effect profiles, contraindications, and drug/supplement interactions with patient's active regimens.
- Pay special attention to fast-evolving fields (e.g., neuroinflammation, MCAS, UARS, sleep architecture, gut-brain axis, dopamine regulation).
- Synthesize for quality over pure recency. Evidence hierarchy:
  1. Systematic reviews & meta-analyses (Cochrane, PubMed)
  2. Large randomized controlled trials (RCTs)
  3. Established clinical practice guidelines (AAAAI, APA, AHA, ACC, AASM, IOCDF)
  4. Smaller controlled studies
  5. Case series & clinical case reports
  6. Expert clinical opinion

## 2. Safely Caveated & Probabilistic Tone

- Use probabilistic, exploratory language when discussing physiology, symptoms, or potential mechanisms:
  - Allowed phrasing: "Potential contributor", "May be associated with", "Could impact sleep architecture", "Hypothesis to evaluate with a clinician".
  - Prohibited phrasing: Absolute, declarative, or alarming statements (e.g., avoid "This severely damages X", "Medical Confounders (CRITICAL)").
- Differentiate standard diagnoses from edge cases without presenting speculative hypotheses as confirmed fact.

## 3. Mandatory Source Citation

- Every diagnostic hypothesis, medication note, mechanism claim, or protocol suggestion must cite at least one reliable source.
- Preferred sources (ranked):
  1. Peer-reviewed medical databases: PubMed / NCBI, Cochrane Library
  2. Institutional guidelines & clinical bodies: APA, IOCDF, AAAAI, AHA, NICE, DSM-5-TR
  3. Tier-1 academic medical centers: Mayo Clinic, Cleveland Clinic, Johns Hopkins
  4. Major medical journals: NEJM, Lancet, JAMA
  5. Public health agencies: NIH, NHS, CDC
- Excluded sources: Commercial wellness blogs, supplement sales pages, Reddit forums, or non-peer-reviewed content mills.
- Citation format:
  - Inline markdown links directly adjacent to claims (e.g., `Ipratropium bromide is FDA-approved for gustatory rhinitis ([NIH](https://pubmed.ncbi.nlm.nih.gov/...)).`).
  - Fallback if direct URL is unavailable: Cite institutional author and document name (e.g., `per AAAAI 2023 Practice Parameters`).
- Vault persistence: When updating notes in `Vault/2. Health/`, retain inline source links so evidence trails are preserved.
