---
type: minor
---

### Added
- **Chat Image Uploads & Multimodal Vision Support:** Added native image attachment support to the Nexus Agent chat interface, enabling users to upload, paste from clipboard (`Ctrl+V`), or drag-and-drop images (PNG, JPEG, WEBP, GIF, BMP) for visual analysis alongside their prompts.
- **FastAPI Upload & Asset Serving Routes (`/api/agents/upload`, `/api/agents/uploads/{filename}`):** Added multipart file upload endpoint validating image integrity via Pillow, auto-resizing oversized assets (>1600px max edge) to control token consumption, and serving persisted images from `logs/uploads/` with strict path traversal guards.
- **Multimodal HumanMessage Construction (`src/nexus/agent/api.py`):** Extended `run_nexus_agent_with_trace` to resolve uploaded image paths into base64 data URLs (`data:image/...;base64,...`) and construct structured multimodal LangChain `HumanMessage` content blocks for native processing by Gemini, Claude, and OpenAI frontier models.
- **SQLite Schema Migration (`chats.db`):** Added `images TEXT` column to `messages` table in `chats_db.py`, persisting attached image URLs without database bloat and hydrating message history for thread rendering.
- **Staged Image Attachments Ribbon & User Bubble Grid:** Added thumbnail preview ribbon with removal buttons to `ChatInputBar.tsx` and rich clickable image cards to `ChatMessageItem.tsx` preserving 100% prompt text visibility.
- **Unit Test Coverage (`tests/test_image_upload_and_multimodal.py`):** Added 8 unit tests covering image upload, Pillow downscaling, MIME validation, path traversal prevention, database persistence, and base64 data URL conversion.
