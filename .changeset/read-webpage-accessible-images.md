---
type: patch
---
### Changed
- Enhanced `src/nexus/shared_tools/read_webpage.py` to extract accessible visual metadata (`alt`, `aria-label`, `aria-labelledby`/`aria-describedby`, `title`, `<figcaption>`, and semantic `<svg role="img">` labels) alongside `trafilatura` and JSON-LD/meta fallbacks, resolve relative and lazy-loaded (`data-src`, `srcset`, `<picture>`) image URLs, and filter decorative/tracking pixels (`1x1`, `alt=""`, nav/footer chrome).
- Added unit test `test_read_webpage_extracts_accessible_images_and_filters_noise` in `tests/test_conversation_cache.py` and updated `README.md`.
