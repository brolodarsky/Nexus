/**
 * background.js — Manifest V3 Service Worker for the Nexus Read-Only Browser Bridge.
 *
 * Architecture & Security Invariants:
 * 1. Strictly Read-Only: Only inspects tab metadata (`chrome.tabs.query`), tab groups
 *    (`chrome.tabGroups.query`), and extracts rendered DOM text/Markdown via isolated
 *    read-only script execution (`chrome.scripting.executeScript`). Never clicks, submits
 *    forms, mutates DOM state, or closes/navigates tabs.
 * 2. Loopback-Only Transport: Connects exclusively to `ws://127.0.0.1:8000/api/browser/ws`
 *    (when the FastAPI Control Panel is running) and `ws://127.0.0.1:8765/api/browser/ws`
 *    (when `python -m nexus.shared_tools.browser_bridge` runs in standalone CLI mode).
 * 3. Zero Anti-Bot Footprint: Reads the already-rendered DOM inside the user's real,
 *    authenticated Chrome session—generating zero extra HTTP requests to external sites.
 */

// Loopback WebSocket endpoints:
// - 8000: Primary Nexus FastAPI backend (`start.ps1`)
// - 8765: Ephemeral standalone CLI listener (`python -m nexus.shared_tools.browser_bridge`)
const ENDPOINTS = {
  api: "ws://127.0.0.1:8000/api/browser/ws",
  cli: "ws://127.0.0.1:8765/api/browser/ws",
};

// Map holding active WebSocket instances keyed by endpoint name ("api" | "cli")
const sockets = {
  api: null,
  cli: null,
};

// Guard flag preventing duplicate concurrent offscreen document creation calls
let creatingOffscreen = false;

/**
 * Ensures the hidden offscreen document (`offscreen.html`) exists so its 2-second
 * heartbeat keeps this Manifest V3 service worker awake across idle periods.
 */
async function ensureOffscreenDocument() {
  if (creatingOffscreen) return;
  try {
    // chrome.runtime.getContexts queries active extension contexts (Chrome 116+)
    if (chrome.runtime.getContexts) {
      const existing = await chrome.runtime.getContexts({
        contextTypes: ["OFFSCREEN_DOCUMENT"],
      });
      if (existing && existing.length > 0) return;
    }
    creatingOffscreen = true;
    await chrome.offscreen.createDocument({
      url: "offscreen.html",
      reasons: ["BLOBS"],
      justification: "Keep local WebSocket bridge responsive for Nexus Agentic Engine CLI and API queries.",
    });
  } catch (_err) {
    // Ignore error if an offscreen document already exists
  } finally {
    creatingOffscreen = false;
  }
}

/**
 * Establishes a WebSocket connection to a local Nexus endpoint ("api" or "cli")
 * if not already connected or connecting.
 *
 * @param {"api" | "cli"} key - Endpoint key from ENDPOINTS
 */
function connectEndpoint(key) {
  const existing = sockets[key];
  // WebSocket.OPEN === 1, WebSocket.CONNECTING === 0
  if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
    return;
  }

  const url = ENDPOINTS[key];
  let ws;
  try {
    ws = new WebSocket(url);
  } catch (_err) {
    return;
  }

  sockets[key] = ws;

  ws.onopen = async () => {
    // Send initial hello handshake with current browser metadata
    const summary = await getQuickCounts();
    safeSend(ws, {
      type: "hello",
      bridge_version: "1.0.0",
      mode: "read_only",
      endpoint: key,
      user_agent: navigator.userAgent,
      tab_count: summary.tabCount,
      group_count: summary.groupCount,
      timestamp: Date.now(),
    });
  };

  ws.onmessage = async (event) => {
    // Parse incoming JSON command from Nexus Python backend/CLI
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch (_err) {
      return;
    }

    const requestId = payload.request_id || null;
    const action = payload.action || "";

    try {
      if (action === "ping") {
        const summary = await getQuickCounts();
        safeSend(ws, {
          type: "response",
          request_id: requestId,
          ok: true,
          data: {
            status: "ok",
            mode: "read_only",
            bridge_version: "1.0.0",
            user_agent: navigator.userAgent,
            tab_count: summary.tabCount,
            group_count: summary.groupCount,
            timestamp: Date.now(),
          },
        });
      } else if (action === "list_tabs") {
        const data = await handleListTabs(payload.params || {});
        safeSend(ws, {
          type: "response",
          request_id: requestId,
          ok: true,
          data,
        });
      } else if (action === "read_tabs") {
        const data = await handleReadTabs(payload.params || {});
        safeSend(ws, {
          type: "response",
          request_id: requestId,
          ok: true,
          data,
        });
      } else {
        safeSend(ws, {
          type: "response",
          request_id: requestId,
          ok: false,
          error: `Unsupported read-only action: '${action}'. Allowed actions: ping, list_tabs, read_tabs.`,
        });
      }
    } catch (err) {
      safeSend(ws, {
        type: "response",
        request_id: requestId,
        ok: false,
        error: err && err.message ? err.message : String(err),
      });
    }
  };

  ws.onerror = () => {
    // Silently close when local server is not running; keepalive loop will retry
    try {
      ws.close();
    } catch (_e) {}
  };

  ws.onclose = () => {
    if (sockets[key] === ws) {
      sockets[key] = null;
    }
  };
}

/**
 * Safely serializes and sends a JSON message over an open WebSocket.
 */
function safeSend(ws, obj) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify(obj));
    } catch (_err) {}
  }
}

/**
 * Attempts connection to both primary API (8000) and standalone CLI (8765) loopback sockets.
 */
function ensureConnections() {
  ensureOffscreenDocument();
  connectEndpoint("api");
  connectEndpoint("cli");

  // Also send a lightweight heartbeat over any open socket to prevent idle socket drops
  for (const key of ["api", "cli"]) {
    const ws = sockets[key];
    if (ws && ws.readyState === WebSocket.OPEN) {
      safeSend(ws, { type: "heartbeat", timestamp: Date.now() });
    }
  }
}

/**
 * Returns fast tab and tab-group counts for status handshakes and popup UI.
 */
async function getQuickCounts() {
  try {
    const [tabs, groups] = await Promise.all([
      chrome.tabs.query({}),
      chrome.tabGroups ? chrome.tabGroups.query({}) : Promise.resolve([]),
    ]);
    return { tabCount: tabs.length, groupCount: groups.length };
  } catch (_err) {
    return { tabCount: 0, groupCount: 0 };
  }
}

/**
 * Queries all Chrome tabs and Tab Groups, joining each tab with its group title and color.
 *
 * @param {Object} params
 * @param {string} [params.group_name] - Optional case-insensitive substring or exact match on Tab Group name
 * @param {string} [params.query] - Optional case-insensitive substring filter on tab title or URL
 * @param {boolean} [params.active_only] - If true, only return the active tab(s)
 */
async function handleListTabs(params = {}) {
  const [rawTabs, rawGroups] = await Promise.all([
    chrome.tabs.query({}),
    chrome.tabGroups ? chrome.tabGroups.query({}) : Promise.resolve([]),
  ]);

  // Build lookup dictionary: groupId (number) -> group metadata object
  const groupMap = new Map();
  for (const g of rawGroups) {
    groupMap.set(g.id, {
      group_id: g.id,
      title: g.title || "(Untitled Group)",
      color: g.color || "grey",
      collapsed: Boolean(g.collapsed),
      window_id: g.windowId,
    });
  }

  const groupFilter = (params.group_name || "").trim().toLowerCase();
  const queryFilter = (params.query || "").trim().toLowerCase();
  const activeOnly = Boolean(params.active_only);

  // Enrich each tab with its Tab Group metadata and apply optional filters
  const enrichedTabs = [];
  const groupCounts = new Map();

  for (const t of rawTabs) {
    const hasGroup = typeof t.groupId === "number" && t.groupId >= 0 && groupMap.has(t.groupId);
    const groupInfo = hasGroup ? groupMap.get(t.groupId) : null;

    if (groupInfo) {
      groupCounts.set(groupInfo.group_id, (groupCounts.get(groupInfo.group_id) || 0) + 1);
    }

    const tabRecord = {
      tab_id: t.id,
      window_id: t.windowId,
      index: t.index,
      title: t.title || "(Untitled Tab)",
      url: t.url || "",
      active: Boolean(t.active),
      pinned: Boolean(t.pinned),
      discarded: Boolean(t.discarded),
      status: t.status || "complete",
      group_id: groupInfo ? groupInfo.group_id : -1,
      group_title: groupInfo ? groupInfo.title : null,
      group_color: groupInfo ? groupInfo.color : null,
      group_collapsed: groupInfo ? groupInfo.collapsed : null,
    };

    // Filter 1: active_only
    if (activeOnly && !tabRecord.active) {
      continue;
    }

    // Filter 2: group_name (matches group_title case-insensitively)
    if (groupFilter) {
      const gTitle = (tabRecord.group_title || "").toLowerCase();
      if (!gTitle || (!gTitle.includes(groupFilter) && gTitle !== groupFilter)) {
        continue;
      }
    }

    // Filter 3: query (matches tab title, URL, or group title)
    if (queryFilter) {
      const haystack = `${tabRecord.title} ${tabRecord.url} ${tabRecord.group_title || ""}`.toLowerCase();
      if (!haystack.includes(queryFilter)) {
        continue;
      }
    }

    enrichedTabs.push(tabRecord);
  }

  // Build summary array of all Chrome Tab Groups currently open
  const groupsSummary = Array.from(groupMap.values()).map((g) => ({
    ...g,
    tab_count: groupCounts.get(g.group_id) || 0,
  }));

  return {
    groups: groupsSummary,
    tabs: enrichedTabs,
    total_open_tabs: rawTabs.length,
    matched_tabs: enrichedTabs.length,
  };
}

/**
 * Self-contained read-only function injected into target tabs via `chrome.scripting.executeScript`.
 *
 * IMPORTANT: Because Chrome serializes this function to run inside the target tab's isolated world,
 * it MUST NOT reference any outer closures or global variables from `background.js`.
 * It strictly reads the live DOM and returns a structured object with clean Markdown.
 *
 * @param {number} maxChars - Maximum character budget for the returned Markdown string
 */
function extractTabMarkdownReadOnly(maxChars) {
  const charBudget = typeof maxChars === "number" && maxChars > 0 ? maxChars : 20000;

  // 1. Extract page metadata (<meta name="description">, canonical URL, OG tags)
  const getMeta = (selector) => {
    const el = document.querySelector(selector);
    return el ? (el.getAttribute("content") || el.getAttribute("href") || "").trim() : "";
  };

  const metaDescription =
    getMeta('meta[name="description"]') ||
    getMeta('meta[property="og:description"]') ||
    "";
  const siteName = getMeta('meta[property="og:site_name"]') || "";

  // 2. Extract structured JSON-LD (<script type="application/ld+json">) if present.
  // Job boards (LinkedIn, Greenhouse, Lever, Workday, Ashby) and retailers embed rich
  // structured data here (e.g. JobPosting salary, location, company, and full description).
  const jsonLdBlocks = [];
  const ldScripts = document.querySelectorAll('script[type="application/ld+json"]');
  const stripHtmlTags = (htmlStr) => {
    if (!htmlStr || typeof htmlStr !== "string") return "";
    const tmp = document.createElement("div");
    tmp.innerHTML = htmlStr;
    return (tmp.textContent || tmp.innerText || "").replace(/\s+/g, " ").trim();
  };

  for (const script of ldScripts) {
    try {
      const raw = (script.textContent || "").trim();
      if (!raw) continue;
      const parsed = JSON.parse(raw);
      const items = Array.isArray(parsed)
        ? parsed
        : parsed && Array.isArray(parsed["@graph"])
        ? parsed["@graph"]
        : [parsed];

      for (const item of items) {
        if (!item || typeof item !== "object") continue;
        const typeVal = Array.isArray(item["@type"]) ? item["@type"].join(", ") : String(item["@type"] || "");
        if (/JobPosting|Product|Article|NewsArticle|SoftwareApplication/i.test(typeVal)) {
          const summaryLines = [`### Structured Schema (${typeVal})`];
          if (item.title || item.name) summaryLines.push(`- **Title:** ${item.title || item.name}`);
          if (item.hiringOrganization && item.hiringOrganization.name) {
            summaryLines.push(`- **Company:** ${item.hiringOrganization.name}`);
          }
          if (item.employmentType) {
            summaryLines.push(
              `- **Employment Type:** ${Array.isArray(item.employmentType) ? item.employmentType.join(", ") : item.employmentType}`
            );
          }
          if (item.datePosted) summaryLines.push(`- **Date Posted:** ${item.datePosted}`);
          if (item.validThrough) summaryLines.push(`- **Valid Through:** ${item.validThrough}`);
          if (item.jobLocation) {
            try {
              const locs = Array.isArray(item.jobLocation) ? item.jobLocation : [item.jobLocation];
              const locStrings = locs
                .map((l) => {
                  const addr = l && l.address ? l.address : {};
                  return [addr.addressLocality, addr.addressRegion, addr.addressCountry].filter(Boolean).join(", ");
                })
                .filter(Boolean);
              if (locStrings.length > 0) summaryLines.push(`- **Location:** ${locStrings.join(" | ")}`);
            } catch (_e) {}
          }
          if (item.baseSalary && item.baseSalary.value) {
            const val = item.baseSalary.value;
            const currency = item.baseSalary.currency || "$";
            const range =
              val.minValue || val.maxValue
                ? `${currency} ${val.minValue ?? ""} - ${val.maxValue ?? ""} (${val.unitText || "YEAR"})`
                : `${currency} ${val.value ?? ""}`;
            summaryLines.push(`- **Base Salary:** ${range}`);
          }
          if (item.description) {
            const cleanDesc = stripHtmlTags(String(item.description));
            if (cleanDesc) {
              summaryLines.push(`- **Schema Description:** ${cleanDesc.slice(0, 4000)}`);
            }
          }
          if (summaryLines.length > 1) {
            jsonLdBlocks.push(summaryLines.join("\n"));
          }
        }
      }
    } catch (_err) {
      // Ignore malformed JSON-LD blocks on the page
    }
  }

  // 3. Walk the live DOM read-only to produce clean Markdown
  const SKIP_TAGS = new Set([
    "SCRIPT",
    "STYLE",
    "NOSCRIPT",
    "SVG",
    "CANVAS",
    "IFRAME",
    "OBJECT",
    "EMBED",
    "TEMPLATE",
    "AUDIO",
    "VIDEO",
  ]);

  const BOILERPLATE_TAGS = new Set(["NAV", "FOOTER"]);

  // Checks if an element is visually hidden via inline attributes or computed CSS
  const isElementHidden = (el, skipBoilerplate) => {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) return false;
    const tag = el.tagName.toUpperCase();
    if (SKIP_TAGS.has(tag)) return true;
    if (skipBoilerplate && BOILERPLATE_TAGS.has(tag)) return true;
    if (el.hasAttribute("hidden") || el.getAttribute("aria-hidden") === "true") return true;
    try {
      const style = window.getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") return true;
    } catch (_e) {}
    return false;
  };

  // Recursive DOM-to-Markdown serializer (also traverses open Shadow DOM roots)
  const nodeToMarkdown = (node, listDepth = 0, skipBoilerplate = true) => {
    if (!node) return "";

    // Text node: normalize internal whitespace while preserving single spaces
    if (node.nodeType === Node.TEXT_NODE) {
      const txt = (node.nodeValue || "").replace(/[ \t\r\n]+/g, " ");
      return txt;
    }

    if (node.nodeType !== Node.ELEMENT_NODE) {
      return "";
    }

    const el = node;
    if (isElementHidden(el, skipBoilerplate)) {
      return "";
    }

    const tag = el.tagName.toUpperCase();

    // Collect children (including open shadowRoot children if web components are used)
    const childNodes = [];
    if (el.shadowRoot && el.shadowRoot.childNodes) {
      for (const sc of el.shadowRoot.childNodes) childNodes.push(sc);
    }
    for (const c of el.childNodes) childNodes.push(c);

    const renderChildren = (nextListDepth = listDepth) =>
      childNodes.map((c) => nodeToMarkdown(c, nextListDepth, skipBoilerplate)).join("");

    if (tag === "BR") return "\n";
    if (tag === "HR") return "\n\n---\n\n";

    // Headings H1 - H6
    if (/^H[1-6]$/.test(tag)) {
      const level = Number(tag[1]);
      const text = renderChildren().replace(/\s+/g, " ").trim();
      return text ? `\n\n${"#".repeat(level)} ${text}\n\n` : "";
    }

    // Paragraphs and block containers
    if (tag === "P") {
      const text = renderChildren().trim();
      return text ? `\n\n${text}\n\n` : "";
    }

    if (tag === "BLOCKQUOTE") {
      const text = renderChildren().trim();
      if (!text) return "";
      const quoted = text
        .split("\n")
        .map((l) => `> ${l}`)
        .join("\n");
      return `\n\n${quoted}\n\n`;
    }

    // Preformatted code blocks
    if (tag === "PRE") {
      const rawCode = (el.textContent || "").trim();
      return rawCode ? `\n\n\`\`\`\n${rawCode}\n\`\`\`\n\n` : "";
    }

    if (tag === "CODE" && (!el.parentElement || el.parentElement.tagName.toUpperCase() !== "PRE")) {
      const codeTxt = renderChildren().trim();
      return codeTxt ? `\`${codeTxt}\`` : "";
    }

    // Inline emphasis
    if (tag === "STRONG" || tag === "B") {
      const text = renderChildren().trim();
      return text ? `**${text}**` : "";
    }

    if (tag === "EM" || tag === "I") {
      const text = renderChildren().trim();
      return text ? `*${text}*` : "";
    }

    // Links: preserve href if it is an http/https link and text is meaningful
    if (tag === "A") {
      const text = renderChildren().replace(/\s+/g, " ").trim();
      if (!text) return "";
      const href = el.href || el.getAttribute("href") || "";
      if (href && /^https?:\/\//i.test(href) && !href.startsWith("javascript:")) {
        return `[${text}](${href})`;
      }
      return text;
    }

    // Unordered and Ordered Lists
    if (tag === "UL" || tag === "OL") {
      const items = [];
      let idx = 1;
      for (const child of childNodes) {
        if (child.nodeType === Node.ELEMENT_NODE && child.tagName.toUpperCase() === "LI") {
          if (isElementHidden(child, skipBoilerplate)) continue;
          const liContent = nodeToMarkdown(child, listDepth + 1, skipBoilerplate)
            .replace(/\n{2,}/g, "\n")
            .trim();
          if (liContent) {
            const indent = "  ".repeat(listDepth);
            const prefix = tag === "OL" ? `${idx}. ` : "- ";
            items.push(`${indent}${prefix}${liContent}`);
            idx += 1;
          }
        }
      }
      return items.length > 0 ? `\n${items.join("\n")}\n` : "";
    }

    if (tag === "LI") {
      return renderChildren(listDepth).trim();
    }

    // Tables -> Markdown table rows
    if (tag === "TABLE") {
      const rows = el.querySelectorAll("tr");
      const mdRows = [];
      for (const tr of rows) {
        const cells = Array.from(tr.querySelectorAll("th, td")).map((cell) =>
          (cell.textContent || "").replace(/\s+/g, " ").replace(/\|/g, "\\|").trim()
        );
        if (cells.some(Boolean)) {
          mdRows.push(`| ${cells.join(" | ")} |`);
          if (mdRows.length === 1) {
            mdRows.push(`| ${cells.map(() => "---").join(" | ")} |`);
          }
        }
      }
      return mdRows.length > 0 ? `\n\n${mdRows.join("\n")}\n\n` : "";
    }

    // Block-level layout elements: add newline boundaries so adjacent blocks don't mash words together
    if (
      tag === "DIV" ||
      tag === "SECTION" ||
      tag === "ARTICLE" ||
      tag === "MAIN" ||
      tag === "HEADER" ||
      tag === "ASIDE" ||
      tag === "TR" ||
      tag === "DT" ||
      tag === "DD"
    ) {
      const inner = renderChildren();
      return inner ? `\n${inner}\n` : "";
    }

    return renderChildren();
  };

  // 4. Identify best content root(s): prioritize semantic job description / article containers
  // if they contain substantial content; otherwise fall back to full document.body.
  const PRIORITY_SELECTORS = [
    ".jobs-description__content",
    ".jobs-box__html-content",
    "#job-details",
    '[data-testid="job-details"]',
    ".job-description",
    "#jobDescriptionText",
    '[role="main"]',
    "main",
    "article",
  ];

  let bodyMarkdown = "";
  for (const sel of PRIORITY_SELECTORS) {
    const matches = document.querySelectorAll(sel);
    if (matches && matches.length > 0) {
      const candidateParts = [];
      for (const m of matches) {
        if (!isElementHidden(m, false)) {
          const rendered = nodeToMarkdown(m, 0, true).trim();
          if (rendered.length > 120) {
            candidateParts.push(rendered);
          }
        }
      }
      const joined = candidateParts.join("\n\n---\n\n").trim();
      if (joined.length >= 350) {
        bodyMarkdown = joined;
        break;
      }
    }
  }

  // Fallback to full document.body (skipping nav/footer boilerplate first, then raw innerText if still tiny)
  if (bodyMarkdown.length < 350 && document.body) {
    bodyMarkdown = nodeToMarkdown(document.body, 0, true).trim();
  }
  if (bodyMarkdown.length < 200 && document.body) {
    bodyMarkdown = (document.body.innerText || document.body.textContent || "").trim();
  }

  // Normalize excessive blank lines
  const cleanMarkdown = bodyMarkdown
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

  // Assemble header + optional JSON-LD schema + rendered DOM markdown
  const sections = [];
  if (siteName) sections.push(`**Site:** ${siteName}`);
  if (metaDescription) sections.push(`**Meta Description:** ${metaDescription}`);
  if (jsonLdBlocks.length > 0) {
    sections.push(jsonLdBlocks.join("\n\n"));
  }
  sections.push(cleanMarkdown);

  const fullText = sections.filter(Boolean).join("\n\n");
  const truncated = fullText.length > charBudget;
  const finalMarkdown = truncated
    ? `${fullText.slice(0, charBudget)}\n\n... [Truncated at ${charBudget} chars; ${fullText.length} total chars]`
    : fullText;

  return {
    title: document.title || "",
    url: window.location.href || "",
    markdown: finalMarkdown,
    char_count: fullText.length,
    truncated,
  };
}

/**
 * Resolves target tabs (by `tab_ids`, `group_name`, `query`, or `active_only`) and runs
 * `extractTabMarkdownReadOnly` in each tab concurrently.
 */
async function handleReadTabs(params = {}) {
  const maxChars = typeof params.max_chars === "number" && params.max_chars > 0 ? params.max_chars : 20000;
  const requestedIds = Array.isArray(params.tab_ids)
    ? params.tab_ids.map((id) => Number(id)).filter((id) => !Number.isNaN(id))
    : [];

  // Reuse handleListTabs to get full tab + group metadata
  const listed = await handleListTabs({
    group_name: params.group_name,
    query: params.query,
    active_only: params.active_only,
  });

  let targetTabs = listed.tabs;
  if (requestedIds.length > 0) {
    const idSet = new Set(requestedIds);
    targetTabs = targetTabs.filter((t) => idSet.has(t.tab_id));
  } else if (!params.group_name && !params.query && !params.active_only) {
    // Safety default: if caller gave no filter at all, read only the active tab in the current window
    targetTabs = targetTabs.filter((t) => t.active);
  }

  // Extract content from each target tab in parallel
  const results = await Promise.all(
    targetTabs.map(async (tab) => {
      const url = tab.url || "";
      // Chrome blocks script injection on internal chrome://, edge://, and Chrome Web Store pages
      if (
        !url ||
        url.startsWith("chrome://") ||
        url.startsWith("chrome-extension://") ||
        url.startsWith("edge://") ||
        url.startsWith("about:")
      ) {
        return {
          ...tab,
          ok: false,
          error: `Cannot extract DOM from restricted browser URL: ${url || "(empty)"}`,
          markdown: "",
          char_count: 0,
          truncated: false,
        };
      }

      try {
        const injectionResults = await chrome.scripting.executeScript({
          target: { tabId: tab.tab_id },
          func: extractTabMarkdownReadOnly,
          args: [maxChars],
        });

        const first = injectionResults && injectionResults[0] ? injectionResults[0].result : null;
        if (!first) {
          return {
            ...tab,
            ok: false,
            error: "Script injection returned empty result (tab may be unloaded or discarded).",
            markdown: "",
            char_count: 0,
            truncated: false,
          };
        }

        return {
          ...tab,
          title: first.title || tab.title,
          url: first.url || tab.url,
          ok: true,
          markdown: first.markdown || "",
          char_count: first.char_count || 0,
          truncated: Boolean(first.truncated),
          error: null,
        };
      } catch (err) {
        return {
          ...tab,
          ok: false,
          error: err && err.message ? err.message : String(err),
          markdown: "",
          char_count: 0,
          truncated: false,
        };
      }
    })
  );

  return {
    requested_count: targetTabs.length,
    succeeded_count: results.filter((r) => r.ok).length,
    tabs: results,
  };
}

// ── Extension Lifecycle & Message Listeners ──────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  ensureConnections();
});

chrome.runtime.onStartup.addListener(() => {
  ensureConnections();
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || typeof msg !== "object") return false;

  if (msg.type === "NEXUS_KEEPALIVE_TICK") {
    ensureConnections();
    sendResponse({ ok: true });
    return false;
  }

  if (msg.type === "NEXUS_FORCE_RECONNECT") {
    for (const key of ["api", "cli"]) {
      if (sockets[key]) {
        try {
          sockets[key].close();
        } catch (_e) {}
        sockets[key] = null;
      }
    }
    ensureConnections();
    sendResponse({ ok: true });
    return false;
  }

  if (msg.type === "NEXUS_GET_POPUP_STATUS") {
    getQuickCounts().then((counts) => {
      sendResponse({
        apiConnected: Boolean(sockets.api && sockets.api.readyState === WebSocket.OPEN),
        cliConnected: Boolean(sockets.cli && sockets.cli.readyState === WebSocket.OPEN),
        tabCount: counts.tabCount,
        groupCount: counts.groupCount,
      });
    });
    return true; // Async response
  }

  return false;
});

// Boot connection immediately when service worker script loads
ensureConnections();
