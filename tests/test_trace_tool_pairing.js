/**
 * test_trace_tool_pairing.js — Node.js regression suite for `gui/src/lib/traceToolPairing.ts`.
 *
 * Verifies:
 * 1. Parallel & out-of-order `call_id` correlation across concurrent tool calls.
 * 2. `tool_error` pairing, `isError` flags, and `callArgs` propagation onto error steps.
 * 3. Legacy FIFO fallback scoped per `(agent_id, tool_name)` and legacy inline arg extraction.
 * 4. Pending `tool_call` and orphan `tool_result` handling without crashes.
 * 5. Collision-resistant `formatShortCallId` across UUIDv4, Anthropic `toolu_01...`, and OpenAI `call_...` IDs.
 * 6. `formatCallDuration` formatting and rounding boundaries (including `119_600ms` -> `2m 0s`).
 */

const fs = require("fs");
const path = require("path");
const assert = require("assert");
const Module = require("module");

const repoRoot = path.resolve(__dirname, "..");
const guiDir = path.join(repoRoot, "gui");
const ts = require(path.join(guiDir, "node_modules", "typescript"));

const pairingSource = fs.readFileSync(
  path.join(guiDir, "src", "lib", "traceToolPairing.ts"),
  "utf8"
);
const compiled = ts.transpileModule(pairingSource, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;

const mod = new Module("traceToolPairing.js");
mod._compile(compiled, "traceToolPairing.js");
const {
  formatShortCallId,
  formatCallDuration,
  extractLegacyToolArgs,
  buildToolCallPairMap,
} = mod.exports;

// 1. Parallel & out-of-order `call_id` pairing
{
  const events = [
    {
      type: "tool_call",
      agent_id: "nexus",
      message: "Calling tool: read_file(path='a.md')",
      timestamp: "2026-11-25T18:00:00.000Z",
      data: { tool: "read_file", call_id: "call_1", args: { path: "a.md" } },
    },
    {
      type: "tool_call",
      agent_id: "nexus",
      message: "Calling tool: read_file(path='b.md')",
      timestamp: "2026-11-25T18:00:00.100Z",
      data: { tool: "read_file", call_id: "call_2", args: { path: "b.md" } },
    },
    {
      type: "tool_call",
      agent_id: "nexus",
      message: "Calling tool: read_file(path='c.md')",
      timestamp: "2026-11-25T18:00:00.200Z",
      data: { tool: "read_file", call_id: "call_3", args: { path: "c.md" } },
    },
    {
      type: "tool_result",
      agent_id: "nexus",
      message: "read_file -> c",
      timestamp: "2026-11-25T18:00:00.242Z",
      data: { tool: "read_file", call_id: "call_3", result: "content-c" },
    },
    {
      type: "tool_result",
      agent_id: "nexus",
      message: "read_file -> a",
      timestamp: "2026-11-25T18:00:01.400Z",
      data: { tool: "read_file", call_id: "call_1", result: "content-aaa" },
    },
    {
      type: "tool_result",
      agent_id: "nexus",
      message: "read_file -> b",
      timestamp: "2026-11-25T18:00:02.600Z",
      data: { tool: "read_file", call_id: "call_2", result: "content-bb" },
    },
  ];

  const pairMap = buildToolCallPairMap(events);
  assert.strictEqual(pairMap.size, 6);

  // call_1 (idx 0) <-> idx 4
  assert.strictEqual(pairMap.get(0).counterpartIndex, 4);
  assert.strictEqual(pairMap.get(0).counterpartRole, "result");
  assert.strictEqual(pairMap.get(0).durationMs, 1400);
  assert.strictEqual(pairMap.get(0).durationLabel, "1.4s");
  assert.strictEqual(pairMap.get(0).resultCharCount, "content-aaa".length);
  assert.strictEqual(pairMap.get(4).counterpartIndex, 0);
  assert.strictEqual(pairMap.get(4).counterpartRole, "call");
  assert.deepStrictEqual(pairMap.get(4).callArgs, { path: "a.md" });

  // call_2 (idx 1) <-> idx 5
  assert.strictEqual(pairMap.get(1).counterpartIndex, 5);
  assert.strictEqual(pairMap.get(5).counterpartIndex, 1);
  assert.deepStrictEqual(pairMap.get(5).callArgs, { path: "b.md" });
  assert.strictEqual(pairMap.get(5).durationMs, 2500);
  assert.strictEqual(pairMap.get(5).durationLabel, "2.5s");

  // call_3 (idx 2) <-> idx 3
  assert.strictEqual(pairMap.get(2).counterpartIndex, 3);
  assert.strictEqual(pairMap.get(3).counterpartIndex, 2);
  assert.deepStrictEqual(pairMap.get(3).callArgs, { path: "c.md" });
  assert.strictEqual(pairMap.get(3).durationMs, 42);
  assert.strictEqual(pairMap.get(3).durationLabel, "42ms");
}

// 2. `tool_error` pairing
{
  const events = [
    {
      type: "tool_call",
      agent_id: "nexus",
      message: "Calling tool: modify_file",
      timestamp: "2026-11-25T18:01:00.000Z",
      data: {
        tool: "modify_file",
        call_id: "2b6a5234-debc-4216-9818-09a581369fdf",
        args: { path: "Vault/Gameplan.md", target: "foo" },
      },
    },
    {
      type: "tool_error",
      agent_id: "nexus",
      message: "modify_file error: Target not found",
      timestamp: "2026-11-25T18:01:00.500Z",
      data: {
        tool: "modify_file",
        call_id: "2b6a5234-debc-4216-9818-09a581369fdf",
        error: "Target not found",
      },
    },
  ];

  const pairMap = buildToolCallPairMap(events);
  assert.strictEqual(pairMap.get(0).isError, true);
  assert.strictEqual(pairMap.get(0).counterpartRole, "error");
  assert.strictEqual(pairMap.get(0).counterpartIndex, 1);
  assert.strictEqual(pairMap.get(0).shortCallId, "2b6a5234");
  assert.strictEqual(pairMap.get(1).role, "error");
  assert.strictEqual(pairMap.get(1).isError, true);
  assert.strictEqual(pairMap.get(1).counterpartRole, "call");
  assert.strictEqual(pairMap.get(1).counterpartIndex, 0);
  assert.strictEqual(pairMap.get(1).resultCharCount, "Target not found".length);
  assert.deepStrictEqual(pairMap.get(1).callArgs, { path: "Vault/Gameplan.md", target: "foo" });
}

// 3. Legacy FIFO fallback (no `call_id`) isolated per `(agent_id, tool_name)`
{
  const events = [
    {
      type: "tool_call",
      agent_id: "nexus",
      message: "Calling tool: search_vault(query='abc')",
      timestamp: "2026-10-21T14:16:29.000Z",
      data: { tool: "search_vault", args: {} },
    },
    {
      type: "tool_call",
      agent_id: "subagent-1",
      message: "Calling tool: search_vault(query='sub')",
      timestamp: "2026-10-21T14:16:29.500Z",
      data: { tool: "search_vault" },
    },
    {
      type: "tool_call",
      agent_id: "nexus",
      message: "Calling tool: search_vault(query='def')",
      timestamp: "2026-10-21T14:16:30.000Z",
      data: { tool: "search_vault" },
    },
    {
      type: "tool_result",
      agent_id: "subagent-1",
      message: "search_vault -> sub-ok",
      timestamp: "2026-10-21T14:16:30.500Z",
      data: { tool: "search_vault", result: "sub-ok" },
    },
    {
      type: "tool_result",
      agent_id: "nexus",
      message: "search_vault -> abc-ok",
      timestamp: "2026-10-21T14:16:31.000Z",
      data: { tool: "search_vault", result: "abc-ok" },
    },
    {
      type: "tool_result",
      agent_id: "nexus",
      message: "search_vault -> def-ok",
      timestamp: "2026-10-21T14:16:32.000Z",
      data: { tool: "search_vault", result: "def-ok" },
    },
  ];

  const pairMap = buildToolCallPairMap(events);
  assert.strictEqual(extractLegacyToolArgs(events[0]), "query='abc'");

  // subagent-1 (idx 1) <-> idx 3
  assert.strictEqual(pairMap.get(1).counterpartIndex, 3);
  assert.strictEqual(pairMap.get(3).counterpartIndex, 1);
  assert.strictEqual(pairMap.get(3).legacyArgsStr, "query='sub'");

  // nexus first call (idx 0) <-> idx 4
  assert.strictEqual(pairMap.get(0).counterpartIndex, 4);
  assert.strictEqual(pairMap.get(4).counterpartIndex, 0);
  assert.strictEqual(pairMap.get(4).legacyArgsStr, "query='abc'");

  // nexus second call (idx 2) <-> idx 5
  assert.strictEqual(pairMap.get(2).counterpartIndex, 5);
  assert.strictEqual(pairMap.get(5).counterpartIndex, 2);
  assert.strictEqual(pairMap.get(5).legacyArgsStr, "query='def'");
}

// 4. Pending `tool_call` and orphan `tool_result`
{
  const events = [
    {
      type: "tool_result",
      agent_id: "nexus",
      message: "orphan",
      timestamp: "2026-11-25T18:02:00.000Z",
      data: { tool: "read_file", call_id: "missing_call", result: "orphan-out" },
    },
    {
      type: "tool_call",
      agent_id: "nexus",
      message: "Calling tool: web_search",
      timestamp: "2026-11-25T18:02:01.000Z",
      data: { tool: "web_search", call_id: "pending_call", args: { q: "test" } },
    },
  ];

  const pairMap = buildToolCallPairMap(events);
  assert.strictEqual(pairMap.get(0).counterpartIndex, null);
  assert.strictEqual(pairMap.get(0).role, "result");
  assert.strictEqual(pairMap.get(0).resultCharCount, "orphan-out".length);

  assert.strictEqual(pairMap.get(1).counterpartIndex, null);
  assert.strictEqual(pairMap.get(1).role, "call");
  assert.strictEqual(pairMap.get(1).durationMs, null);
  assert.deepStrictEqual(pairMap.get(1).callArgs, { q: "test" });
}

// 5. `formatShortCallId`
assert.strictEqual(formatShortCallId("2b6a5234-debc-4216-9818-09a581369fdf"), "2b6a5234");
const anthropicA = formatShortCallId("toolu_01ABCXYZ11112222");
const anthropicB = formatShortCallId("toolu_01ABCXYZ99998888");
assert.strictEqual(anthropicA, "11112222");
assert.strictEqual(anthropicB, "99998888");
assert.notStrictEqual(anthropicA, anthropicB);
assert.strictEqual(formatShortCallId("call_abc123"), "abc123");
assert.strictEqual(formatShortCallId("fc_9876543210abcdef"), "10abcdef");
assert.strictEqual(formatShortCallId("short"), "short");
assert.strictEqual(formatShortCallId("   "), null);
assert.strictEqual(formatShortCallId(null), null);
assert.strictEqual(formatShortCallId(undefined), null);

// 6. `formatCallDuration`
assert.strictEqual(formatCallDuration(0), "0ms");
assert.strictEqual(formatCallDuration(42), "42ms");
assert.strictEqual(formatCallDuration(1400), "1.4s");
assert.strictEqual(formatCallDuration(12500), "12.5s");
assert.strictEqual(formatCallDuration(72_000), "1m 12s");
assert.strictEqual(formatCallDuration(119_600), "2m 0s");
assert.strictEqual(formatCallDuration(-5), null);
assert.strictEqual(formatCallDuration(Number.NaN), null);
assert.strictEqual(formatCallDuration(null), null);
assert.strictEqual(formatCallDuration(undefined), null);

console.log("All trace tool pairing tests passed!");
