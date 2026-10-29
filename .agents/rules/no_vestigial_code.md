# Zero-Vestige Engineering & Clean Code Deletion Standards

> Standing instruction for all AI coding and builder agents operating across this repository.

## The Core Problem
When AI agents implement new features, build replacements, or modernize existing tools, they frequently fall into a pattern of timidity: leaving behind deprecated CLI scripts, dead functions, obsolete terminal loops, temporary scratch files, and orphaned package dependencies "just in case." Over time, this causes severe code rot, cognitive bloat, and confusion for both humans and future agents.

## The Standing Mandate
**When you build a replacement or refactor a system, you are required to identify and cleanly delete the old, superseded, and vestigial code in the same session.** A task to "replace X with Y" is not complete until X's dead pathways and scaffolds are excised.

---

## Mandatory Pruning Directives

### 1. Replacement Implies Deletion (Clean Deprecation)
- When building a new interface or replacement architecture (e.g., replacing a CLI interactive prompt with a web studio, or upgrading an API router):
  - Do **not** leave the old interactive loops, dead fallback branches, or legacy entrypoints sitting around as zombies unless the user explicitly requested dual backwards-compatibility.
  - If a CLI script is now driven headlessly by an API service, strip out terminal `readline` prompts, interactive menus, and redundant console wrappers.

### 2. Scratch & Debug Scaffolding Must Never Survive
- Remove one-off debugging scripts (e.g., temporary XML unpackers, ad-hoc inspect scripts, throwaway test dumps).
- Never commit scratch exploration files created during intermediate investigation.

### 3. Prune Orphaned Dependencies & Imports
- Whenever you delete or refactor code, check what packages or modules it relied on.
- If an npm package (`package.json`) or Python package (`pyproject.toml`) was only needed by the deleted code, remove it from the dependency manifest and lockfile.
- Strip unused imports across all touched files.

### 4. Collapse Redundant Subprocess & Wrapper Hops
- Never leave circular or multi-runtime adapter hops in place (e.g., Python spawning Node to spawn Python) when the new architecture allows direct native execution.
- If a target module is native to the caller's runtime (e.g., calling Python from Python), import and execute it directly.

### 5. Audit & Verify Before Concluding
Before finishing any refactoring or replacement task, run this 3-step checklist:
1. **Search References:** Run a repo search for the old function, script name, or module to ensure no callers were left dangling.
2. **Run Test Suites:** Run full test suites (`pytest`, `npm run build`) to prove that pruning did not break active functionality.
3. **Document What Was Removed:** Explicitly list what vestigial files, dead functions, and dependencies were excised in your changeset and summary.
