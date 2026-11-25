/**
 * test_chat_model_memory.js — Node.js regression suite for per-conversation model resolution
 * and history extraction helpers in `gui/src/components/chat/types.ts`.
 *
 * Verifies:
 * 1. Exact concrete model resolution across Gemini (Argon, Hydrogen, Flash) and Anthropic (Opus, Sonnet, Haiku 5.5).
 * 2. Cross-provider tier isolation: `claude-haiku-5-5` (`tier: "low"`) and `gemini-4-hydrogen` (`tier: "low"`)
 *    never collide with Gemini Flash (`id: "low"`), and unlisted models (`gpt-5.6-sol`) return `null`.
 * 3. Retired Anthropic 4.5 IDs migrate cleanly to their 5.5 catalog entries.
 * 4. `extractLastUsedModelFromHistory` returns the newest attributed turn while skipping trailing
 *    synthetic `branch_merge` / `branch_context` entries and falling back to trace events.
 */

const fs = require("fs");
const path = require("path");
const assert = require("assert");
const Module = require("module");

const repoRoot = path.resolve(__dirname, "..");
const guiDir = path.join(repoRoot, "gui");
const ts = require(path.join(guiDir, "node_modules", "typescript"));

const typesSource = fs.readFileSync(
  path.join(guiDir, "src", "components", "chat", "types.ts"),
  "utf8"
);
const compiled = ts.transpileModule(typesSource, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;

const mod = new Module("types.js");
mod._compile(compiled, "types.js");
const {
  FALLBACK_MODELS,
  resolveConversationModelSelection,
  extractLastUsedModelFromHistory,
} = mod.exports;

// 1. Standard Gemini & Anthropic exact resolutions (including cross-provider "low" tier isolation)
assert.strictEqual(
  resolveConversationModelSelection(FALLBACK_MODELS, { name: "gemini-4-argon", tier: "strong" }),
  "strong"
);
assert.strictEqual(
  resolveConversationModelSelection(FALLBACK_MODELS, { name: "gemini-4-hydrogen", tier: "low" }),
  "gemini-4-hydrogen"
);
assert.strictEqual(
  resolveConversationModelSelection(FALLBACK_MODELS, { name: "gemini-3.8-flash", tier: "low" }),
  "low"
);
assert.strictEqual(
  resolveConversationModelSelection(FALLBACK_MODELS, { name: "claude-opus-5-5", tier: "strong" }),
  "claude-opus-5-5"
);
assert.strictEqual(
  resolveConversationModelSelection(FALLBACK_MODELS, { name: "claude-sonnet-5-5", tier: "medium" }),
  "claude-sonnet-5-5"
);
assert.strictEqual(
  resolveConversationModelSelection(FALLBACK_MODELS, { name: "claude-haiku-5-5", tier: "low" }),
  "claude-haiku-5-5"
);

// 2. Retired Anthropic 4.5 IDs migrate cleanly to 5.5 catalog entries
assert.strictEqual(
  resolveConversationModelSelection(FALLBACK_MODELS, { name: "claude-sonnet-4-5", tier: "medium" }),
  "claude-sonnet-5-5"
);
assert.strictEqual(
  resolveConversationModelSelection(FALLBACK_MODELS, { name: "claude-opus-4.5", tier: "strong" }),
  "claude-opus-5-5"
);

// 3. Unlisted/other-provider concrete model names must return null rather than falling back to tier
assert.strictEqual(
  resolveConversationModelSelection(FALLBACK_MODELS, { name: "gpt-5.6-sol", tier: "strong" }),
  null
);

// 4. Tier-only legacy fallback works when concrete model_name is absent
assert.strictEqual(
  resolveConversationModelSelection(FALLBACK_MODELS, { name: null, tier: "strong" }),
  "strong"
);
assert.strictEqual(resolveConversationModelSelection(FALLBACK_MODELS, null), null);
assert.strictEqual(
  resolveConversationModelSelection(FALLBACK_MODELS, { name: null, tier: null }),
  null
);

// 5. History extraction skips trailing synthetic branch_merge entries and prefers newest attributed turn
assert.deepStrictEqual(
  extractLastUsedModelFromHistory([
    {
      id: 1,
      role: "user",
      content: "Hello",
      timestamp: "2026-11-25T10:00:00Z",
      model_tier: "strong",
      model_name: "gemini-4-argon",
    },
    {
      id: 2,
      role: "assistant",
      content: "Switched to Haiku",
      timestamp: "2026-11-25T10:01:00Z",
      model_tier: "low",
      model_name: "claude-haiku-5-5",
    },
    {
      id: 3,
      role: "assistant",
      content: "### 🌿 Distilled Merge from Branch",
      agent: "branch_merge",
      timestamp: "2026-11-25T10:02:00Z",
      model_tier: null,
      model_name: null,
    },
  ]),
  { name: "claude-haiku-5-5", tier: "low" }
);

// 6. Trace fallback for legacy rows lacking explicit model_name/model_tier columns
assert.deepStrictEqual(
  extractLastUsedModelFromHistory([
    {
      id: 10,
      role: "assistant",
      content: "Legacy answer",
      timestamp: "2026-11-24T12:00:00Z",
      trace: [
        {
          type: "agent_start",
          agent_id: "nexus",
          data: { model_tier: "strong", model_name: "claude-opus-5-5" },
        },
      ],
    },
  ]),
  { name: "claude-opus-5-5", tier: "strong" }
);

assert.deepStrictEqual(extractLastUsedModelFromHistory([]), null);

console.log("All chat model memory tests passed!");
