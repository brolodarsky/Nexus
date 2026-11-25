---
type: patch
---

### Changed
- **Standardized Model Catalog Descriptions, Minimal Dropdown UI & Pricing Display (`src/nexus/core/constants.py`, `gui/src/lib/api/agents.ts`, `gui/src/components/chat/types.ts`, `gui/src/components/chat/ModelSelectorDropdown.tsx`):**
  - Standardized all 6 selectable chat models (`Gemini 4 Argon`, `Gemini 4 Hydrogen`, `Gemini 3.8 Flash`, `Claude Opus 5.5`, `Claude Sonnet 5.5`, `Claude Haiku 5.5`) with concise, non-repetitive single-sentence explainers and symmetrical Gemini/Anthropic tier ordering.
  - Derived structured `pricing` metadata (`input_per_m`, `output_per_m`, `cached_per_m`, `summary`, `note`) directly from `nexus.core.cost.resolve_model_pricing()` in `GET /api/agents/models` and mirrored it in `FALLBACK_MODELS`.
  - Redesigned `ModelSelectorDropdown` into a clean dark minimal menu without tier emoji icons or colored selection borders, displaying a `"Model"` / `"USD / 1M (in / out)"` header, thin provider divider, inline price text, subtle caveat pills (`$4/$20 Dec 1`, `$1.50/$7.50 Jan 1`, `5× >100K`), full one-line explainers, and cached-rate hover tooltips.
- **Verified Google Gemini Pricing Sync (`src/nexus/core/cost.py`, `gui/src/components/chat/types.ts`, `tests/test_cost_tracking.py`, `tests/test_model_config_and_resilience.py`):**
  - Updated `gemini-4-argon` to verified active promotional rates (`$2.00` in / `$0.10` cached / `$10.00` out, flat across 1M context; `$4/$20` starting Dec 1, 2026) and `gemini-3.8-flash` to verified introductory rates (`$0.75` in / `$0.075` cached / `$3.75` out; `$1.50/$7.50` starting Jan 1, 2027), while preserving the `>128k` 2x step-up exclusively for legacy `gemini-1.5-pro` / `gemini-2.5-pro`.
