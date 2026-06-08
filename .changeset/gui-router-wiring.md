---
type: minor
---

Wire GUI Ask Brain page to the Content Router agent instead of calling the Librarian directly. The /api/agents/ask endpoint now routes through classify → domain dispatch, and the frontend displays which agent handled each query with domain and confidence metadata.
