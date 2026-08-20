---
description: Automates the release process by compiling changesets into the changelog, bumping the version, and committing/pushing the release. Use when the user asks to "do a release" or "release changesets".
---

# Steps

1. Run the Release Script:
   - Execute the meta script to compile changesets and bump the version:
     ```bash
     .venv/Scripts/python.exe scripts/release.py
     ```

2. Review Output:
   - Verify that the release script completed successfully and extracted the new version number `vX.Y.Z`.

3. Commit the Changes:
   - Stage the updated changelog and removed changeset files, then commit using Conventional Commits:
     ```bash
     git add .
     git commit -m "docs(changelog): compile vX.Y.Z release from changesets"
     ```

4. Push the Release:
   - Push the new release commit to origin:
     ```bash
     git push
     ```

5. Summarize:
   - Inform the user that release `vX.Y.Z` has been compiled and pushed.
