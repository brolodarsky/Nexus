---
type: patch
---

Fix live status model label (`Routing query with ...`) mislabeling Anthropic turns (`Claude Haiku 5.5` shown as `Gemini 3.8 Flash`, `Claude Opus 5.5` shown as `Gemini 4 Argon`) due to single-pass `m.id === activeRunModel.tier` collisions in `gui/src/app/chat/page.tsx`. Added name-first `resolveModelOption` and `resolveLiveModelLabel` helpers in `gui/src/components/chat/types.ts` and wired them across `liveStatusModelLabel`, `onDone`, and `onError` in `ChatPage`.
