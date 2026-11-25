/**
 * background.js — Manifest V3 Service Worker for the Nexus Browser Bridge.
 *
 * Architecture & Security Invariants:
 * 1. Assisted Draft Mode (No Auto-Submit): Inspects tab metadata (`chrome.tabs.query`),
 *    tab groups (`chrome.tabGroups.query`), extracts rendered DOM Markdown (with optional
 *    transient `data-nexus-ref` handles), opens/groups `http(s)` tabs, and draft-fills
 *    form fields while hard-blocking passwords, payment/SSN fields, and form submission.
 * 2. Loopback-Only Transport: Connects exclusively to `ws://127.0.0.1:8000/api/browser/ws`
 *    (when the FastAPI Control Panel is running) and `ws://127.0.0.1:8765/api/browser/ws`
 *    (when `python -m nexus.shared_tools.browser_bridge` runs in standalone CLI mode).
 * 3. Zero Anti-Bot Footprint: Reads and drafts directly inside the user's real,
 *    authenticated Chrome session—generating zero extra HTTP requests to external sites.
 */

// Extension protocol/extractor version verified by `browser_bridge.py` to flag stale loaded workers
const BRIDGE_VERSION = "1.2.0";

// Hard bounds preventing runaway tab opening or massive form-fill payloads
const MAX_OPEN_TABS = 10;
const MAX_FILL_FIELDS = 50;
// Chrome Tab Group color enum accepted by `chrome.tabGroups.update`
const VALID_GROUP_COLORS = new Set(["grey", "blue", "red", "yellow", "green", "pink", "purple", "cyan", "orange"]);

// Loopback WebSocket endpoints:
// - 8000: Primary Nexus FastAPI backend (`start.ps1`)
// - 8765: Ephemeral standalone CLI listener (`python -m nexus.shared_tools.browser_bridge`)
const ENDPOINTS = {
  api: "ws://127.0.0.1:8000/api/browser/ws",
  cli: "ws://127.0.0.1:8765/api/browser/ws",
};

// Lightweight HTTP probe URLs checked via `fetch()` before constructing `new WebSocket(...)`
// so Chrome never logs `WebSocket connection to 'ws://...' failed: net::ERR_CONNECTION_REFUSED`
// in `chrome://extensions` Errors when an endpoint is offline.
const PROBE_URLS = {
  api: "http://127.0.0.1:8000/api/browser/status",
  cli: "http://127.0.0.1:8765/api/browser/status",
};

// Map holding active WebSocket instances keyed by endpoint name ("api" | "cli")
const sockets = {
  api: null,
  cli: null,
};

// In-flight HTTP probe guards keyed by endpoint name ("api" | "cli")
const probing = {
  api: false,
  cli: false,
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
 * Probes and establishes a WebSocket connection to a local Nexus endpoint ("api" or "cli")
 * if not already connected or connecting.
 *
 * By verifying the endpoint is reachable over HTTP (`fetch(PROBE_URLS[key])`) inside a
 * `try / catch` block before calling `new WebSocket(url)`, we prevent Chromium's C++
 * WebSocket handshake layer from logging `net::ERR_CONNECTION_REFUSED` into the
 * `chrome://extensions` Error console when a local listener is offline.
 *
 * @param {"api" | "cli"} key - Endpoint key from ENDPOINTS
 * @returns {Promise<boolean>} True if already connected or probe succeeded
 */
async function connectEndpoint(key) {
  const existing = sockets[key];
  // WebSocket.OPEN === 1, WebSocket.CONNECTING === 0
  if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
    return true;
  }
  if (probing[key]) {
    return false;
  }

  probing[key] = true;
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 800);
    try {
      const res = await fetch(PROBE_URLS[key], {
        method: "GET",
        cache: "no-store",
        signal: controller.signal,
      });
      if (!res.ok) {
        return false;
      }
    } finally {
      clearTimeout(timer);
    }
  } catch (_err) {
    // Endpoint is offline; return cleanly without invoking `new WebSocket(url)`
    return false;
  } finally {
    probing[key] = false;
  }

  // Re-check socket state after async probe completes
  const afterProbe = sockets[key];
  if (afterProbe && (afterProbe.readyState === WebSocket.OPEN || afterProbe.readyState === WebSocket.CONNECTING)) {
    return true;
  }

  const url = ENDPOINTS[key];
  let ws;
  try {
    ws = new WebSocket(url);
  } catch (_err) {
    return false;
  }

  sockets[key] = ws;

  ws.onopen = async () => {
    // Send initial hello handshake with current browser metadata
    const summary = await getQuickCounts();
    safeSend(ws, {
      type: "hello",
      bridge_version: BRIDGE_VERSION,
      mode: "assisted_draft",
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
            mode: "assisted_draft",
            bridge_version: BRIDGE_VERSION,
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
      } else if (action === "open_tabs") {
        const data = await handleOpenTabs(payload.params || {});
        safeSend(ws, {
          type: "response",
          request_id: requestId,
          ok: true,
          data,
        });
      } else if (action === "fill_form") {
        const data = await handleFillForm(payload.params || {});
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
          error: `Unsupported action: '${action}'. Allowed actions: ping, list_tabs, read_tabs, open_tabs, fill_form.`,
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

  return true;
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
 * Maintains connection to the primary API (`8000`) loopback socket, falling back to the
 * standalone CLI (`8765`) socket only when port `8000` is offline. When `8000` is already
 * open, skips all probes to port `8765` because `browser_bridge.py` routes CLI commands
 * through the active FastAPI relay on port `8000`.
 */
async function ensureConnections() {
  ensureOffscreenDocument();

  // Send a lightweight heartbeat over any already-open socket to prevent idle socket drops
  for (const key of ["api", "cli"]) {
    const ws = sockets[key];
    if (ws && ws.readyState === WebSocket.OPEN) {
      safeSend(ws, { type: "heartbeat", timestamp: Date.now() });
    }
  }

  // If the primary FastAPI bridge (`8000`) is already connected or connects now, do not poll `8765`
  const apiReady = await connectEndpoint("api");
  if (!apiReady) {
    await connectEndpoint("cli");
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
 * Self-contained function injected into target tabs via `chrome.scripting.executeScript`.
 *
 * IMPORTANT: Because Chrome serializes this function to run inside the target tab's isolated world,
 * it MUST NOT reference any outer closures or global variables from `background.js`.
 * Reads the live DOM into clean Markdown and, only when `includeRefs === true`, stamps transient
 * `data-nexus-ref` handles onto visible form controls so `fillFormFieldsInFrame` can target them.
 *
 * @param {number} maxChars - Maximum character budget for the returned Markdown string
 * @param {boolean} [includeRefs=false] - When true, stamp `data-nexus-ref` attributes onto form controls
 */
function extractTabMarkdownReadOnly(maxChars, includeRefs = false) {
  const charBudget = typeof maxChars === "number" && maxChars > 0 ? maxChars : 20000;
  const stampRefs = Boolean(includeRefs);

  // Detect whether this script instance is executing inside an embedded <iframe> vs. top frame
  let isSubframe = false;
  try {
    isSubframe = window.self !== window.top;
  } catch (_e) {
    // Cross-origin access to window.top throws SecurityError, proving this is an iframe
    isSubframe = true;
  }

  const currentUrl = window.location && window.location.href ? window.location.href : "";

  // Deterministic per-frame prefix (`f0` for top frame, `s<hash>` for iframes) so cross-frame refs never collide
  const computeShortHash = (str) => {
    let h = 2166136261;
    for (let i = 0; i < str.length; i += 1) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return (h >>> 0).toString(36).slice(0, 5);
  };
  const framePrefix = isSubframe ? `s${computeShortHash(currentUrl || "sub")}` : "f0";
  let refCounter = 0;

  // Clear stale `data-nexus-ref` stamps on re-capture so refs stay aligned with the latest read
  if (stampRefs && typeof document.querySelectorAll === "function") {
    try {
      const priorStamped = document.querySelectorAll("[data-nexus-ref]");
      for (const node of priorStamped) {
        if (node && typeof node.removeAttribute === "function") {
          node.removeAttribute("data-nexus-ref");
        }
      }
    } catch (_e) {}
  }

  // Assigns (or reuses if visited in both main and modal walks) a transient `data-nexus-ref` handle
  const assignFormRef = (el) => {
    if (!stampRefs || !el) return "";
    const existingRef = typeof el.getAttribute === "function" ? el.getAttribute("data-nexus-ref") : null;
    if (existingRef) return existingRef;
    refCounter += 1;
    const refId = `${framePrefix}_${refCounter}`;
    if (typeof el.setAttribute === "function") {
      el.setAttribute("data-nexus-ref", refId);
    }
    return refId;
  };
  if (isSubframe) {
    const lowerUrl = currentUrl.toLowerCase();
    // Skip blank, tracking, payment-card, or CAPTCHA iframes with no readable content/forms
    if (
      !lowerUrl ||
      lowerUrl === "about:blank" ||
      lowerUrl.startsWith("javascript:") ||
      /recaptcha|hcaptcha|challenges\.cloudflare\.com|doubleclick\.net|googlesyndication\.com|googletagmanager\.com|facebook\.com\/tr|stripe\.com\/v3\/elements-inner/i.test(
        lowerUrl
      )
    ) {
      return {
        title: "",
        url: currentUrl,
        markdown: "",
        char_count: 0,
        truncated: false,
        is_subframe: true,
        has_form_controls: false,
      };
    }
    if (typeof window.innerWidth === "number" && (window.innerWidth < 120 || window.innerHeight < 80)) {
      return {
        title: "",
        url: currentUrl,
        markdown: "",
        char_count: 0,
        truncated: false,
        is_subframe: true,
        has_form_controls: false,
      };
    }
  }

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
  // Store candidate entries alongside their description text so Step 6 can include them
  // ONLY when the live rendered DOM is sparse or missing that schema content.
  const jsonLdEntries = [];
  const ldScripts = document.querySelectorAll('script[type="application/ld+json"]');
  const stripHtmlTags = (htmlStr) => {
    if (!htmlStr || typeof htmlStr !== "string") return "";
    const tmp = document.createElement("div");
    tmp.innerHTML = htmlStr;
    // Run a second pass in case the JSON-LD string contained HTML-escaped tags (e.g. `&lt;p&gt;`)
    const pass1 = tmp.textContent || tmp.innerText || "";
    tmp.innerHTML = pass1;
    return (tmp.textContent || tmp.innerText || "")
      .replace(/<[^>]+>/g, " ")
      .replace(/\\"/g, '"')
      .replace(/\s+/g, " ")
      .trim();
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
          let cleanDesc = "";
          if (item.description) {
            cleanDesc = stripHtmlTags(String(item.description));
            if (cleanDesc) {
              // Cap at `charBudget` (not hardcoded 4,000) so fallback subpages preserve full text
              summaryLines.push(`- **Schema Description:** ${cleanDesc.slice(0, charBudget)}`);
            }
          }
          if (summaryLines.length > 1) {
            jsonLdEntries.push({
              block: summaryLines.join("\n"),
              descText: cleanDesc,
              fullText: summaryLines.slice(1).join(" "),
            });
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
    if (skipBoilerplate) {
      if (BOILERPLATE_TAGS.has(tag)) return true;
      // Skip floating chat overlay containers and dialogs during the main document body walk
      // so raw floating drawer noise does not pollute the primary document flow.
      // The dedicated active overlay / chat pass cleanly structures them at the end.
      const cls = (el.className || "").toString();
      if (cls.includes("msg-overlay-container") || cls.includes("chat-window") || cls.includes("chat-overlay")) {
        return true;
      }
      const role = (el.getAttribute && el.getAttribute("role")) || "";
      if (role === "dialog" || role === "alertdialog" || tag === "DIALOG") {
        return true;
      }
      if (el.getAttribute && el.getAttribute("aria-modal") === "true") {
        return true;
      }
    }
    if (el.hasAttribute("hidden") || el.getAttribute("aria-hidden") === "true") return true;
    try {
      const style = window.getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") return true;
      // Catch CSS fade-out / closed transition modals while keeping MockNode safe (opacity undefined)
      if (style.opacity !== undefined && style.opacity !== "" && parseFloat(style.opacity) === 0) {
        return true;
      }
    } catch (_e) {}
    return false;
  };

  // Pure parentElement-chain ancestor check (avoids Element.prototype.contains for MockNode compatibility)
  const isAncestorOf = (ancestor, descendant) => {
    if (!ancestor || !descendant) return false;
    let curr = descendant.parentElement;
    while (curr) {
      if (curr === ancestor) return true;
      curr = curr.parentElement;
    }
    return false;
  };

  // Returns visible interactive form controls inside `rootEl` for modal/form detection
  const getVisibleFormControls = (rootEl) => {
    if (!rootEl || typeof rootEl.querySelectorAll !== "function") return [];
    try {
      const candidates = rootEl.querySelectorAll(
        'input:not([type="hidden"]), textarea, select, [role="combobox"], [role="listbox"], [role="checkbox"], [role="radio"], [role="switch"], [contenteditable="true"]'
      );
      const visible = [];
      for (const c of candidates) {
        if (!isElementHidden(c, false)) {
          visible.push(c);
        }
      }
      return visible;
    } catch (_e) {
      return [];
    }
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

    // Interactive form controls: serialize inputs, textareas, selects, and custom ARIA widgets
    // (stamping transient `ref=<id>` handles when `stampRefs` is enabled)
    if (tag === "INPUT") {
      const inputType = (el.getAttribute("type") || el.type || "text").toLowerCase();
      if (inputType === "hidden") return "";

      if (inputType === "submit" || inputType === "button" || inputType === "reset") {
        const btnVal = (
          (typeof el.value === "string" ? el.value : el.getAttribute("value")) ||
          el.getAttribute("aria-label") ||
          ""
        ).trim();
        return btnVal ? `\n[Button: ${btnVal}]\n` : "";
      }

      if (inputType === "checkbox" || inputType === "radio") {
        const isChecked = Boolean(el.checked || el.hasAttribute("checked"));
        const box = isChecked ? "[x]" : "[ ]";
        const refId = stampRefs ? assignFormRef(el) : "";
        const refTag = refId ? ` [ref=${refId}]` : "";
        const insideLabel = Boolean(el.closest && el.closest("label"));
        if (insideLabel) {
          return `\n${box}${refTag} `;
        }
        const ariaLbl = (el.getAttribute("aria-label") || "").trim();
        return `\n${box}${refTag}${ariaLbl ? ` ${ariaLbl}` : ""}\n`;
      }

      // Never expose raw secrets or stamp fillable refs on password fields
      const isPassword = inputType === "password";
      const rawVal = typeof el.value === "string" ? el.value : el.getAttribute("value") || "";
      const displayVal = isPassword ? (rawVal ? "(redacted)" : "") : rawVal;
      const placeholder = (el.getAttribute("placeholder") || el.getAttribute("aria-placeholder") || "").trim();
      const ariaLabel = (el.getAttribute("aria-label") || "").trim();
      const isRequired = Boolean(
        el.required || el.hasAttribute("required") || el.getAttribute("aria-required") === "true"
      );
      const roleAttr = (el.getAttribute("role") || "").toLowerCase();
      const hasPopup = (el.getAttribute("aria-haspopup") || "").toLowerCase();
      const fieldKind = roleAttr === "combobox" || hasPopup === "listbox" ? "combobox" : inputType;
      const meta = isRequired ? `${fieldKind}, required` : fieldKind;

      const parentLabel = el.closest ? el.closest("label") : null;
      const parentLabelText = parentLabel
        ? (parentLabel.textContent || "").replace(/\s+/g, " ").trim().toLowerCase()
        : "";
      const refId = stampRefs && !isPassword ? assignFormRef(el) : "";
      const parts = [];
      if (refId) {
        parts.push(`ref=${refId}`);
      }
      if (ariaLabel && !parentLabelText.includes(ariaLabel.toLowerCase())) {
        parts.push(`label="${ariaLabel}"`);
      }
      if (displayVal) {
        parts.push(isPassword ? displayVal : `"${displayVal}"`);
      }
      if (placeholder) {
        parts.push(`placeholder="${placeholder}"`);
      }
      if (parts.length === 0) {
        parts.push("(empty)");
      }
      return `\n\`[Input (${meta}): ${parts.join(", ")}]\`\n`;
    }

    if (tag === "TEXTAREA") {
      const rawVal = typeof el.value === "string" ? el.value : el.textContent || "";
      const cleanVal = rawVal.replace(/\s+/g, " ").trim();
      const placeholder = (el.getAttribute("placeholder") || el.getAttribute("aria-placeholder") || "").trim();
      const ariaLabel = (el.getAttribute("aria-label") || "").trim();
      const isRequired = Boolean(
        el.required || el.hasAttribute("required") || el.getAttribute("aria-required") === "true"
      );
      const meta = isRequired ? "required" : "optional";
      const parentLabel = el.closest ? el.closest("label") : null;
      const parentLabelText = parentLabel
        ? (parentLabel.textContent || "").replace(/\s+/g, " ").trim().toLowerCase()
        : "";
      const refId = stampRefs ? assignFormRef(el) : "";
      const parts = [];
      if (refId) parts.push(`ref=${refId}`);
      if (ariaLabel && !parentLabelText.includes(ariaLabel.toLowerCase())) {
        parts.push(`label="${ariaLabel}"`);
      }
      if (cleanVal) parts.push(`"${cleanVal}"`);
      if (placeholder) parts.push(`placeholder="${placeholder}"`);
      if (parts.length === 0) parts.push("(empty)");
      return `\n\`[Textarea (${meta}): ${parts.join(", ")}]\`\n`;
    }

    if (tag === "SELECT") {
      const isRequired = Boolean(
        el.required || el.hasAttribute("required") || el.getAttribute("aria-required") === "true"
      );
      const isMulti = Boolean(el.multiple || el.hasAttribute("multiple"));
      const ariaLabel = (el.getAttribute("aria-label") || "").trim();
      const options = Array.from(el.querySelectorAll("option"));
      const allLabels = [];
      const selectedLabels = [];
      for (const opt of options) {
        const lbl = (opt.textContent || opt.getAttribute("value") || "").replace(/\s+/g, " ").trim();
        if (!lbl) continue;
        allLabels.push(lbl);
        const optVal = opt.getAttribute("value");
        const isSel = Boolean(
          opt.selected ||
            opt.hasAttribute("selected") ||
            (typeof el.value === "string" && el.value !== "" && (optVal === el.value || lbl === el.value))
        );
        if (isSel) selectedLabels.push(lbl);
      }
      const typeLabel = isMulti ? "Select (multi)" : "Select";
      const reqLabel = isRequired ? " (required)" : "";
      const refId = stampRefs ? assignFormRef(el) : "";
      const parts = [];
      if (refId) parts.push(`ref=${refId}`);
      if (ariaLabel) parts.push(`label="${ariaLabel}"`);
      if (selectedLabels.length > 0) parts.push(`selected="${selectedLabels.join(", ")}"`);
      if (allLabels.length > 0) {
        const shown = allLabels.slice(0, 25);
        const extra = allLabels.length > 25 ? ` (+${allLabels.length - 25} more)` : "";
        parts.push(`options: ${shown.join(" | ")}${extra}`);
      } else {
        parts.push("(no options)");
      }
      return `\n\`[${typeLabel}${reqLabel}: ${parts.join("; ")}]\`\n`;
    }

    // Custom ARIA form controls on non-native elements (e.g. React-Select, Radix, Luma dropdowns)
    const elRole = (el.getAttribute("role") || "").toLowerCase();
    const elHasPopup = (el.getAttribute("aria-haspopup") || "").toLowerCase();

    if (elRole === "checkbox" || elRole === "radio" || elRole === "switch") {
      const checked = el.getAttribute("aria-checked") === "true";
      const box = checked ? "[x]" : "[ ]";
      const refId = stampRefs ? assignFormRef(el) : "";
      const refTag = refId ? ` [ref=${refId}]` : "";
      const txt = (renderChildren().replace(/\s+/g, " ").trim() || el.getAttribute("aria-label") || "").trim();
      return `\n${box}${refTag}${txt ? ` ${txt}` : ""}\n`;
    }

    if (elRole === "combobox" || elHasPopup === "listbox") {
      const isRequired = Boolean(el.getAttribute("aria-required") === "true" || el.hasAttribute("required"));
      const reqLabel = isRequired ? " (required)" : "";
      const ariaLabel = (el.getAttribute("aria-label") || "").trim();
      const ariaPlaceholder = (el.getAttribute("aria-placeholder") || "").trim();
      const innerTxt = renderChildren().replace(/\s+/g, " ").replace(/`/g, "").trim();
      const currentDisplay = innerTxt || (ariaPlaceholder ? `placeholder="${ariaPlaceholder}"` : "(empty)");
      let optionsSuffix = "";
      const controlledId = el.getAttribute("aria-controls") || el.getAttribute("aria-owns") || "";
      if (controlledId) {
        const firstId = controlledId.trim().split(/\s+/)[0];
        let listboxEl = null;
        try {
          listboxEl =
            typeof document.getElementById === "function"
              ? document.getElementById(firstId)
              : document.querySelector(`[id="${firstId}"]`);
        } catch (_e) {}
        if (listboxEl && !isElementHidden(listboxEl, false)) {
          const optNodes = Array.from(listboxEl.querySelectorAll('[role="option"]'));
          const optTexts = optNodes
            .map((o) => (o.textContent || "").replace(/\s+/g, " ").trim())
            .filter(Boolean);
          if (optTexts.length > 0) {
            const shown = optTexts.slice(0, 25);
            const extra = optTexts.length > 25 ? ` (+${optTexts.length - 25} more)` : "";
            optionsSuffix = `; options: ${shown.join(" | ")}${extra}`;
          }
        }
      }
      const refId = stampRefs ? assignFormRef(el) : "";
      const refPrefix = refId ? `ref=${refId}; ` : "";
      const prefix = ariaLabel ? `label="${ariaLabel}"; ` : "";
      return `\n\`[Dropdown${reqLabel}: ${refPrefix}${prefix}${currentDisplay}${optionsSuffix}]\`\n`;
    }

    if (el.getAttribute("contenteditable") === "true") {
      const refId = stampRefs ? assignFormRef(el) : "";
      const refPrefix = refId ? `ref=${refId}; ` : "";
      const inner = renderChildren().trim();
      if (inner) {
        return refId ? `\n\`[Editable: ref=${refId}]\`\n${inner}\n` : `\n${inner}\n`;
      }
      const ph = (el.getAttribute("aria-placeholder") || el.getAttribute("data-placeholder") || "").trim();
      return ph ? `\n\`[Editable: ${refPrefix}placeholder="${ph}"]\`\n` : `\n\`[Editable: ${refPrefix}(empty)]\`\n`;
    }

    if (tag === "LEGEND") {
      const text = renderChildren().replace(/\s+/g, " ").trim();
      return text ? `\n\n**${text}**\n` : "";
    }

    // Block-level layout elements: add newline boundaries so adjacent blocks don't mash words together
    if (
      tag === "DIV" ||
      tag === "SECTION" ||
      tag === "ARTICLE" ||
      tag === "MAIN" ||
      tag === "HEADER" ||
      tag === "ASIDE" ||
      tag === "FORM" ||
      tag === "FIELDSET" ||
      tag === "LABEL" ||
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
  const selectedContentRoots = [];
  for (const sel of PRIORITY_SELECTORS) {
    const matches = document.querySelectorAll(sel);
    if (matches && matches.length > 0) {
      const candidateParts = [];
      const candidateRoots = [];
      for (const m of matches) {
        if (!isElementHidden(m, false)) {
          const rendered = nodeToMarkdown(m, 0, true).trim();
          if (rendered.length > 120) {
            candidateParts.push(rendered);
            candidateRoots.push(m);
          }
        }
      }
      const joined = candidateParts.join("\n\n---\n\n").trim();
      if (joined.length >= 350) {
        bodyMarkdown = joined;
        selectedContentRoots.push(...candidateRoots);
        break;
      }
    }
  }

  // Fallback to full document.body (skipping nav/footer boilerplate first, then raw innerText if still tiny)
  if (bodyMarkdown.length < 350 && document.body) {
    bodyMarkdown = nodeToMarkdown(document.body, 0, true).trim();
    selectedContentRoots.length = 0;
    selectedContentRoots.push(document.body);
  }
  if (bodyMarkdown.length < 200 && document.body) {
    bodyMarkdown = (document.body.innerText || document.body.textContent || "").trim();
    if (selectedContentRoots.length === 0) {
      selectedContentRoots.push(document.body);
    }
  }

  // Normalize excessive blank lines
  const cleanMarkdown = bodyMarkdown
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

  // Checks whether `candidateText` is already substantially present in `referenceText`
  // using normalized 5+-char unique token recall (universal, zero site-specific regexes).
  const isSubstantiallyCovered = (candidateText, referenceText) => {
    const normRef = (referenceText || "").toLowerCase().replace(/[^a-z0-9]+/g, " ");
    const normCand = (candidateText || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
    if (!normCand) return true;
    // Fast substring hit when the leading 120 normalized characters match verbatim in referenceText
    if (normCand.length >= 60 && normRef.includes(normCand.slice(0, 120))) {
      return true;
    }
    const refWords = new Set(normRef.split(" ").filter((w) => w.length >= 5));
    const candWords = [];
    const seen = new Set();
    for (const w of normCand.split(" ")) {
      if (w.length >= 5 && !seen.has(w)) {
        seen.add(w);
        candWords.push(w);
        if (candWords.length >= 80) break;
      }
    }
    if (candWords.length === 0) return true;
    let hits = 0;
    for (const w of candWords) {
      if (refWords.has(w)) hits += 1;
    }
    return hits / candWords.length >= 0.55;
  };

  // 5. Active Overlay / Chat / Portal Modal Extraction Pass
  // Captures expanded floating chat windows (e.g. LinkedIn InMail/messaging overlay), semantic
  // ARIA/native dialogs, non-ARIA framework portals (e.g. Luma lux-modal, Radix, Tailwind fixed
  // portals), and sibling <form> containers rendered outside the selected content root.
  const extractActiveOverlaysMarkdown = () => {
    try {
      const chatBlocks = [];
      const modalBlocks = [];
      const processedElements = new Set();

      // Collect candidates in strict priority order:
      // 1. Chat overlays -> 2. Semantic dialogs -> 3. Non-ARIA portals/fixed siblings -> 4. Standalone forms
      const candidates = [];
      const pushSelectorMatches = (sel, kind) => {
        try {
          const matches = document.querySelectorAll(sel);
          for (const el of matches) {
            candidates.push({ el, kind });
          }
        } catch (_e) {}
      };

      const CHAT_SELECTORS = [
        "aside.msg-overlay-container .msg-overlay-conversation-bubble--is-expanded",
        ".msg-overlay-conversation-bubble--is-expanded",
        "aside.msg-overlay-container .msg-overlay-conversation-bubble:not(.msg-overlay-conversation-bubble--is-minimized)",
        '[data-testid*="chat-window"]',
        '[data-testid*="conversation-overlay"]',
        '[data-testid*="chat-overlay"]',
        '.chat-window:not([hidden])',
        '.chat-overlay:not([hidden])',
      ];
      for (const sel of CHAT_SELECTORS) pushSelectorMatches(sel, "chat");

      const DIALOG_SELECTORS = [
        '[role="dialog"]:not([aria-hidden="true"])',
        '[role="alertdialog"]:not([aria-hidden="true"])',
        '[aria-modal="true"]:not([aria-hidden="true"])',
        "dialog[open]",
      ];
      for (const sel of DIALOG_SELECTORS) pushSelectorMatches(sel, "dialog");

      const PORTAL_SELECTORS = [
        '[class*="modal"]:not([hidden])',
        '[class*="Modal"]:not([hidden])',
        '[class*="dialog"]:not([hidden])',
        '[class*="Dialog"]:not([hidden])',
        '[class*="drawer"]:not([hidden])',
        '[class*="Drawer"]:not([hidden])',
        '[class*="sheet"]:not([hidden])',
        '[class*="Sheet"]:not([hidden])',
        '[class*="overlay"]:not([hidden])',
        '[class*="Overlay"]:not([hidden])',
        '[data-testid*="modal"]',
        '[data-testid*="Modal"]',
        '[data-testid*="dialog"]',
        '[data-testid*="Dialog"]',
        "[data-radix-portal]",
        "[data-floating-ui-portal]",
        "[data-portal]",
      ];
      for (const sel of PORTAL_SELECTORS) pushSelectorMatches(sel, "portal");

      // Scan direct children of <body>, #__next, #root, and #app for CSS-in-JS portals with hashed class names
      const portalParents = [document.body];
      for (const rootSel of ["#__next", "#root", "#app"]) {
        try {
          const rEl = document.querySelector(rootSel);
          if (rEl) portalParents.push(rEl);
        } catch (_e) {}
      }
      for (const p of portalParents) {
        if (p && p.children) {
          for (const child of p.children) {
            if (child && child.nodeType === Node.ELEMENT_NODE) {
              candidates.push({ el: child, kind: "portal" });
            }
          }
        }
      }

      pushSelectorMatches("form:not([hidden])", "form");

      for (const candidate of candidates) {
        const el = candidate.el;
        const kind = candidate.kind;
        if (!el || el.nodeType !== Node.ELEMENT_NODE) continue;
        if (processedElements.has(el)) continue;

        // Skip hidden elements (display: none, visibility: hidden, opacity: 0, hidden attr)
        if (isElementHidden(el, false)) continue;

        // Skip collapsed or minimized elements
        const classStr = (el.className || "").toString().toLowerCase();
        if (classStr.includes("minimized") || classStr.includes("collapsed")) continue;
        if (el.getAttribute("aria-expanded") === "false") continue;

        // Filter out structural page shells and navigation landmarks
        const tag = el.tagName.toUpperCase();
        if (tag === "BODY" || tag === "MAIN" || tag === "HTML" || tag === "NAV" || tag === "HEADER" || tag === "FOOTER") {
          continue;
        }

        const ariaLabel = (el.getAttribute("aria-label") || "").toLowerCase();
        const idStr = (el.id || "").toLowerCase();

        // Check if element is a cookie consent / privacy modal
        if (
          /cookie|consent|gdpr|onetrust|privacy-modal|cookie-banner|consent-banner/i.test(
            `${classStr} ${idStr} ${ariaLabel}`
          )
        ) {
          continue;
        }

        // Bidirectional deduplication: skip if el is inside a processed element OR wraps a processed element
        let hasHierarchyConflict = false;
        for (const prev of processedElements) {
          if (isAncestorOf(prev, el) || isAncestorOf(el, prev)) {
            hasHierarchyConflict = true;
            break;
          }
        }
        if (hasHierarchyConflict) continue;

        const controlsCount = getVisibleFormControls(el).length;
        const isInsideSelectedRoot = selectedContentRoots.some((r) => isAncestorOf(r, el));
        let isFixed = false;

        if (kind === "portal" || kind === "form") {
          // Dedicated chat selectors own chat containers so minimized chat docks are never re-parsed as forms
          if (classStr.includes("msg-overlay-container") || classStr.includes("chat-window") || classStr.includes("chat-overlay")) {
            continue;
          }
          // Never treat a selected content root or an app wrapper containing a selected content root as a modal
          if (selectedContentRoots.includes(el) || selectedContentRoots.some((r) => isAncestorOf(el, r))) {
            continue;
          }

          try {
            isFixed = window.getComputedStyle(el).position === "fixed";
          } catch (_e) {}

          if (kind === "form") {
            if (isInsideSelectedRoot) continue;
          } else {
            if (isInsideSelectedRoot && !isFixed) continue;
            if (typeof el.getBoundingClientRect === "function") {
              try {
                const rect = el.getBoundingClientRect();
                if (rect.width < 120 || rect.height < 60) continue;
              } catch (_e) {}
            }
            const testIdStr = (el.getAttribute("data-testid") || "").toLowerCase();
            const hasModalSignal =
              isFixed ||
              controlsCount > 0 ||
              /(?:modal|dialog|drawer|sheet|portal)/i.test(`${classStr} ${idStr} ${testIdStr}`);
            if (!hasModalSignal) continue;
          }
        }

        // Step B probe: identify true chat threads without letting form validation errors trigger chat mode
        const MESSAGE_SELECTORS = [
          ".msg-s-event-listitem",
          ".msg-s-message-list__event",
          "[data-event-urn]",
          ".msg-s-message-group",
          ".chat-message",
          ".message-item",
          '[data-testid*="chat-message"]',
          '[data-testid*="message-item"]',
          '[data-testid*="message-bubble"]',
          '[data-testid*="dm-message"]',
          '[class*="message-bubble"]',
          '[class*="chat-bubble"]',
        ];

        let messageElements = [];
        if (kind === "chat" || controlsCount < 2) {
          for (const mSel of MESSAGE_SELECTORS) {
            try {
              const found = el.querySelectorAll(mSel);
              if (found && found.length > 0) {
                messageElements = Array.from(found);
                break;
              }
            } catch (_e) {}
          }
        }

        const isChatOverlay = kind === "chat" || (controlsCount < 2 && messageElements.length > 0);

        if (isChatOverlay) {
          processedElements.add(el);

          // Step A: Extract Conversation Participant / Title
          let participant = "";
          const TITLE_SELECTORS = [
            "header .msg-overlay-bubble-header__title",
            ".msg-overlay-bubble-header__title",
            ".msg-overlay-bubble-header__details h2",
            "header h2",
            "header [role='heading']",
            ".msg-conversation-card__participant-names",
            "[data-control-name='overlay.open_thread']",
            "header a[href*='/in/']",
            "[role='heading']",
            "h1, h2, h3, h4",
            "[class*='participant-name']",
            "[class*='user-name']",
            "[class*='chat-title']",
          ];

          for (const tSel of TITLE_SELECTORS) {
            try {
              const titleEl = el.querySelector(tSel);
              if (titleEl && !isElementHidden(titleEl, false)) {
                const rawTitle = (titleEl.textContent || "").trim();
                if (rawTitle) {
                  participant = rawTitle;
                  break;
                }
              }
            } catch (_e) {}
          }

          if (!participant) {
            participant = (el.getAttribute("aria-label") || "").trim();
          }

          // Clean status artifacts from participant name (e.g. "Active now", "Status is reachable", "1st degree")
          participant = participant
            .replace(/(?:Status is reachable|Status is active|Active now|Available on mobile|Available on desktop)/gi, "")
            .replace(/,\s*\d+(?:st|nd|rd|th)?\s*(?:degree)?(?:\s+connection)?/gi, "")
            .replace(/^Conversation with\s+/i, "")
            .replace(/\s+/g, " ")
            .trim();

          if (participant.includes("\n")) {
            participant = participant.split("\n")[0].trim();
          }

          if (!participant) {
            participant = "Conversation Participant";
          }

          const messages = [];
          let lastSender = participant;
          let lastTimestamp = "";

          if (messageElements.length > 0) {
            for (const mEl of messageElements) {
              if (isElementHidden(mEl, false)) continue;

              // 1. Resolve Sender
              let sender = "";
              const SENDER_SELECTORS = [
                ".msg-s-message-group__name",
                ".msg-s-event-listitem__name",
                "a.msg-s-event-listitem__link",
                ".msg-s-message-group__profile-link",
                "[class*='sender-name']",
                "[class*='author-name']",
                "[class*='sender']",
              ];

              for (const sSel of SENDER_SELECTORS) {
                const sEl = mEl.querySelector(sSel) || mEl.closest(".msg-s-message-group, [class*='message-group']")?.querySelector(sSel);
                if (sEl) {
                  const sText = (sEl.textContent || "").trim();
                  if (sText) {
                    sender = sText;
                    break;
                  }
                }
              }

              // Check if message belongs to the current user (viewer/me)
              const mClass = (mEl.className || "").toString().toLowerCase();
              const groupEl = mEl.closest(".msg-s-message-group, [class*='message-group']");
              const gClass = groupEl ? (groupEl.className || "").toString().toLowerCase() : "";
              const isViewer =
                mClass.includes("--me") ||
                mClass.includes("--viewer") ||
                gClass.includes("--me") ||
                gClass.includes("--viewer");

              if (!sender) {
                if (isViewer) {
                  sender = "You";
                } else if (lastSender) {
                  sender = lastSender;
                } else {
                  sender = participant;
                }
              } else {
                lastSender = sender;
              }

              // Clean sender text
              sender = sender.replace(/\s+/g, " ").trim();
              if (sender.includes("\n")) sender = sender.split("\n")[0].trim();

              // 2. Resolve Timestamp
              let timestamp = "";
              const timeEl =
                mEl.querySelector("time, .msg-s-event-listitem__timestamp, .msg-s-message-group__timestamp, [class*='timestamp'], [class*='time']") ||
                groupEl?.querySelector("time, .msg-s-message-group__timestamp, [class*='timestamp']");

              if (timeEl) {
                timestamp = (timeEl.textContent || timeEl.getAttribute("datetime") || "").replace(/\s+/g, " ").trim();
                if (timestamp) {
                  lastTimestamp = timestamp;
                }
              }
              if (!timestamp && lastTimestamp) {
                timestamp = lastTimestamp;
              }

              // 3. Resolve Subject (for InMail messages)
              let subjectPrefix = "";
              const subjEl = mEl.querySelector(".msg-s-event-listitem__subject, [class*='subject']");
              if (subjEl) {
                const sTxt = (subjEl.textContent || "").replace(/\s+/g, " ").trim();
                if (sTxt) subjectPrefix = `**Subject:** ${sTxt}\n\n`;
              }

              // 4. Resolve Body: Check if mEl contains multiple message bodies (e.g. if grouped)
              const bodyElements = mEl.querySelectorAll(
                ".msg-s-event-listitem__body, .msg-s-message-bubble__content, p.msg-s-event-listitem__body"
              );

              const bodies = bodyElements.length > 0 ? Array.from(bodyElements) : [mEl];

              for (const bEl of bodies) {
                let bodyText = "";
                if (bEl !== mEl) {
                  bodyText = nodeToMarkdown(bEl, 0, false).trim();
                } else {
                  try {
                    const clone = mEl.cloneNode(true);
                    const toRemove = clone.querySelectorAll(
                      "time, [class*='sender'], [class*='timestamp'], [class*='author'], [class*='meta'], header, button"
                    );
                    for (const r of toRemove) r.remove();
                    bodyText = nodeToMarkdown(clone, 0, false).trim();
                  } catch (_e) {
                    bodyText = nodeToMarkdown(mEl, 0, false).trim();
                  }
                }

                bodyText = bodyText
                  .replace(/[ \t]+\n/g, "\n")
                  .replace(/\n{3,}/g, "\n\n")
                  .trim();

                if (!bodyText) continue;

                const fullMessageText = subjectPrefix ? `${subjectPrefix}${bodyText}` : bodyText;
                subjectPrefix = "";

                const quotedBody = fullMessageText
                  .split("\n")
                  .map((line) => (line.trim() ? `> ${line}` : ">"))
                  .join("\n");

                const timeStr = timestamp ? ` (${timestamp})` : "";
                messages.push(`- **Sender:** ${sender}${timeStr}\n${quotedBody}`);
              }
            }
          } else {
            const rawChatContent = nodeToMarkdown(el, 0, false).trim();
            if (rawChatContent && rawChatContent.length > 30) {
              const quotedBody = rawChatContent
                .split("\n")
                .map((line) => (line.trim() ? `> ${line}` : ">"))
                .join("\n");
              messages.push(`- **Sender:** ${participant}\n${quotedBody}`);
            }
          }

          if (messages.length > 0) {
            chatBlocks.push(`### ${participant}\n${messages.join("\n\n")}`);
          }
        } else {
          // Non-chat modal / dialog / portal / form extraction: render directly as structured Markdown
          const rawContent = nodeToMarkdown(el, 0, false)
            .replace(/[ \t]+\n/g, "\n")
            .replace(/\n{3,}/g, "\n\n")
            .trim();
          const hasControls = controlsCount > 0;
          if (!rawContent || (rawContent.length < 20 && !hasControls)) continue;

          if (kind === "portal" || kind === "form") {
            if (!hasControls && isSubstantiallyCovered(rawContent, cleanMarkdown)) continue;
            // Allow fixed form portals inside a document.body fallback to be promoted when long pages risk truncation
            const protectFromTruncation = isFixed && hasControls && cleanMarkdown.length > charBudget * 0.7;
            if (isInsideSelectedRoot && isSubstantiallyCovered(rawContent, cleanMarkdown) && !protectFromTruncation) {
              continue;
            }
          }

          processedElements.add(el);

          let modalTitle = "";
          const MODAL_TITLE_SELECTORS = ["h1", "h2", "h3", "h4", '[role="heading"]'];
          for (const tSel of MODAL_TITLE_SELECTORS) {
            try {
              const tEl = el.querySelector(tSel);
              if (tEl && !isElementHidden(tEl, false)) {
                const txt = (tEl.textContent || "").replace(/\s+/g, " ").trim();
                if (txt) {
                  modalTitle = txt;
                  break;
                }
              }
            } catch (_e) {}
          }
          if (!modalTitle) {
            modalTitle = (el.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim();
          }
          if (!modalTitle) {
            modalTitle = "Active Modal";
          }

          modalBlocks.push(`### ${modalTitle}\n\n${rawContent}`);
        }
      }

      return {
        modalMarkdown:
          modalBlocks.length > 0 ? `---\n## Active Modal / Dialog\n\n${modalBlocks.join("\n\n")}` : "",
        chatMarkdown:
          chatBlocks.length > 0 ? `---\n## Active Chat & Floating Overlays\n\n${chatBlocks.join("\n\n")}` : "",
      };
    } catch (_err) {
      return { modalMarkdown: "", chatMarkdown: "" };
    }
  };

  const { modalMarkdown, chatMarkdown } = extractActiveOverlaysMarkdown();

  // 6. Universal Coverage Deduplication, Budget Protection & Section Assembly
  // Prioritize `cleanMarkdown` (live rendered DOM body) first so metadata/JSON-LD never triples
  // payload size, while reserving budget for active modals/overlays so long background pages
  // cannot truncate away active form dialogs or chat threads.
  const baseSections = [];
  if (siteName) baseSections.push(`**Site:** ${siteName}`);
  if (cleanMarkdown) baseSections.push(cleanMarkdown);

  // Track cumulative reference text so accepting JSON-LD also suppresses duplicate metaDescription
  let coverageRef = cleanMarkdown;
  const isSparseDom = cleanMarkdown.length < 300;

  for (const entry of jsonLdEntries) {
    const compareTarget = entry.descText || entry.fullText;
    const neededForSparse = isSparseDom && !isSubstantiallyCovered(compareTarget, coverageRef);
    const missingSubstantialDesc = entry.descText.length >= 150 && !isSubstantiallyCovered(entry.descText, coverageRef);
    if (neededForSparse || missingSubstantialDesc) {
      baseSections.push(entry.block);
      coverageRef = `${coverageRef}\n\n${entry.block}`;
    }
  }

  if (metaDescription) {
    const neededMetaForSparse = isSparseDom && !isSubstantiallyCovered(metaDescription, coverageRef);
    const missingSubstantialMeta = metaDescription.length >= 150 && !isSubstantiallyCovered(metaDescription, coverageRef);
    if (neededMetaForSparse || missingSubstantialMeta) {
      baseSections.push(`**Meta Description:** ${metaDescription}`);
    }
  }

  const overlaySections = [];
  if (modalMarkdown) overlaySections.push(modalMarkdown);
  if (chatMarkdown) overlaySections.push(chatMarkdown);

  const baseText = baseSections.filter(Boolean).join("\n\n");
  const activeOverlayText = overlaySections.filter(Boolean).join("\n\n");
  const fullText = [baseText, activeOverlayText].filter(Boolean).join("\n\n");
  const truncated = fullText.length > charBudget;

  let finalMarkdown = fullText;
  if (truncated) {
    if (activeOverlayText) {
      // Reserve up to 60% of charBudget (or unused base space) so active forms/overlays survive truncation
      const overlayBudget = Math.min(
        activeOverlayText.length,
        Math.max(Math.floor(charBudget * 0.6), charBudget - Math.min(baseText.length, Math.floor(charBudget * 0.4)))
      );
      const noticeReserve = 95;
      const baseBudget = Math.max(0, charBudget - overlayBudget - noticeReserve);
      const keptBase = baseBudget > 0 ? baseText.slice(0, baseBudget).trimEnd() : "";
      const truncNotice = `... [Background page truncated to preserve active modal/overlay; ${fullText.length} total chars]`;
      const keptOverlay = activeOverlayText.slice(0, overlayBudget);
      finalMarkdown = [keptBase, truncNotice, keptOverlay].filter(Boolean).join("\n\n");
    } else {
      finalMarkdown = `${fullText.slice(0, charBudget)}\n\n... [Truncated at ${charBudget} chars; ${fullText.length} total chars]`;
    }
  }

  const hasFormControls = Boolean(document.body && getVisibleFormControls(document.body).length > 0);

  return {
    title: document.title || "",
    url: currentUrl,
    markdown: finalMarkdown,
    char_count: fullText.length,
    truncated,
    is_subframe: isSubframe,
    has_form_controls: hasFormControls,
    include_refs: stampRefs,
  };
}

/**
 * Resolves target tabs (by `tab_ids`, `group_name`, `query`, or `active_only`) and runs
 * `extractTabMarkdownReadOnly` in each tab concurrently.
 */
async function handleReadTabs(params = {}) {
  const maxChars = typeof params.max_chars === "number" && params.max_chars > 0 ? params.max_chars : 20000;
  const includeRefs = Boolean(params.include_refs);
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
        let injectionResults;
        try {
          // Inject across all frames to capture embedded application forms (Greenhouse/Lever/Typeform/Luma)
          injectionResults = await chrome.scripting.executeScript({
            target: { tabId: tab.tab_id, allFrames: true },
            func: extractTabMarkdownReadOnly,
            args: [maxChars, includeRefs],
          });
        } catch (_allFramesErr) {
          // Fall back to top frame if an iframe policy rejects allFrames injection
          injectionResults = await chrome.scripting.executeScript({
            target: { tabId: tab.tab_id },
            func: extractTabMarkdownReadOnly,
            args: [maxChars, includeRefs],
          });
        }

        const validFrames = Array.isArray(injectionResults)
          ? injectionResults.filter((r) => r && r.result)
          : [];
        if (validFrames.length === 0) {
          return {
            ...tab,
            ok: false,
            error: "Script injection returned empty result (tab may be unloaded or discarded).",
            markdown: "",
            char_count: 0,
            truncated: false,
          };
        }

        const primaryFrame =
          validFrames.find((r) => r.frameId === 0) ||
          validFrames.find((r) => !r.result.is_subframe) ||
          validFrames[0];
        const first = primaryFrame.result;

        // Merge meaningful subframes while ignoring tiny/empty tracker frames
        const subframeSections = [];
        for (const r of validFrames) {
          if (r === primaryFrame) continue;
          const sub = r.result;
          const subMd = (sub.markdown || "").trim();
          if (!subMd) continue;
          if (!sub.has_form_controls && subMd.length < 120) continue;
          const frameLabel = sub.title || sub.url || `frame ${r.frameId ?? "?"}`;
          subframeSections.push(`---\n## Embedded Frame (${frameLabel})\n\n${subMd}`);
        }

        let mergedMarkdown = first.markdown || "";
        let totalCharCount = first.char_count || mergedMarkdown.length;
        let isTruncated = Boolean(first.truncated);

        if (subframeSections.length > 0) {
          const combinedFrames = subframeSections.join("\n\n");
          totalCharCount += combinedFrames.length + 2;
          if (mergedMarkdown.length + combinedFrames.length + 2 <= maxChars) {
            mergedMarkdown = mergedMarkdown ? `${mergedMarkdown}\n\n${combinedFrames}` : combinedFrames;
          } else {
            isTruncated = true;
            const frameBudget = Math.min(
              combinedFrames.length,
              Math.max(Math.floor(maxChars * 0.6), maxChars - Math.min(mergedMarkdown.length, Math.floor(maxChars * 0.4)))
            );
            const primaryBudget = Math.max(0, maxChars - frameBudget - 95);
            const keptPrimary = primaryBudget > 0 ? mergedMarkdown.slice(0, primaryBudget).trimEnd() : "";
            const notice = `... [Primary frame truncated to preserve embedded frame content; ${totalCharCount} total chars]`;
            mergedMarkdown = [keptPrimary, notice, combinedFrames.slice(0, frameBudget)].filter(Boolean).join("\n\n");
          }
        }

        return {
          ...tab,
          title: first.title || tab.title,
          url: first.url || tab.url,
          ok: true,
          markdown: mergedMarkdown,
          char_count: totalCharCount,
          truncated: isTruncated,
          include_refs: includeRefs,
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
    bridge_version: BRIDGE_VERSION,
    requested_count: targetTabs.length,
    succeeded_count: results.filter((r) => r.ok).length,
    tabs: results,
  };
}

/**
 * Opens 1-10 validated `http(s)` URLs in Chrome tabs and optionally places them into a Chrome Tab Group.
 *
 * @param {Object} params
 * @param {string[]} params.urls - Bounded list of `http://` or `https://` URLs
 * @param {string} [params.group_name] - Optional Tab Group title (reuses existing group in window if found)
 * @param {string} [params.group_color="blue"] - Tab Group badge color
 * @param {boolean} [params.activate_first=false] - Focus the first opened tab
 */
async function handleOpenTabs(params = {}) {
  const rawUrls = Array.isArray(params.urls) ? params.urls : [];
  if (rawUrls.length === 0) {
    throw new Error("Provide at least 1 URL in `urls`.");
  }
  if (rawUrls.length > MAX_OPEN_TABS) {
    throw new Error(`Cannot open more than ${MAX_OPEN_TABS} tabs per call (received ${rawUrls.length}).`);
  }

  // Validate every URL strictly as http/https before creating any tab
  const validUrls = [];
  for (const raw of rawUrls) {
    const str = String(raw || "").trim();
    let parsed;
    try {
      parsed = new URL(str);
    } catch (_e) {
      throw new Error(`Invalid URL: '${str}'.`);
    }
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      throw new Error(`Rejected non-HTTP(S) URL '${str}'. Only http:// and https:// URLs are permitted.`);
    }
    validUrls.push(parsed.toString());
  }

  let targetWindowId;
  try {
    const win = await chrome.windows.getLastFocused({ windowTypes: ["normal"] });
    if (win && typeof win.id === "number") {
      targetWindowId = win.id;
    }
  } catch (_e) {}

  const createdTabs = [];
  const activateFirst = Boolean(params.activate_first);
  for (let idx = 0; idx < validUrls.length; idx += 1) {
    const createOpts = {
      url: validUrls[idx],
      active: activateFirst && idx === 0,
    };
    if (typeof targetWindowId === "number") {
      createOpts.windowId = targetWindowId;
    }
    const created = await chrome.tabs.create(createOpts);
    createdTabs.push(created);
  }

  let groupId = null;
  let resolvedGroupTitle = null;
  let resolvedGroupColor = null;
  const rawGroupName = typeof params.group_name === "string" ? params.group_name.trim() : "";

  if (rawGroupName && createdTabs.length > 0 && chrome.tabs && typeof chrome.tabs.group === "function") {
    const tabIds = createdTabs.map((t) => t.id).filter((id) => typeof id === "number");
    const winId = typeof createdTabs[0].windowId === "number" ? createdTabs[0].windowId : targetWindowId;
    const desiredColor = VALID_GROUP_COLORS.has(String(params.group_color || "").toLowerCase())
      ? String(params.group_color).toLowerCase()
      : "blue";

    let existingGroup = null;
    if (chrome.tabGroups && typeof chrome.tabGroups.query === "function") {
      try {
        const groups = await chrome.tabGroups.query(typeof winId === "number" ? { windowId: winId } : {});
        existingGroup =
          groups.find((g) => (g.title || "").trim().toLowerCase() === rawGroupName.toLowerCase()) || null;
      } catch (_e) {}
    }

    if (existingGroup) {
      groupId = await chrome.tabs.group({ groupId: existingGroup.id, tabIds });
      resolvedGroupTitle = existingGroup.title || rawGroupName;
      resolvedGroupColor = existingGroup.color || desiredColor;
    } else {
      const groupOpts = typeof winId === "number" ? { tabIds, createProperties: { windowId: winId } } : { tabIds };
      groupId = await chrome.tabs.group(groupOpts);
      if (chrome.tabGroups && typeof chrome.tabGroups.update === "function") {
        const updated = await chrome.tabGroups.update(groupId, {
          title: rawGroupName,
          color: desiredColor,
        });
        resolvedGroupTitle = (updated && updated.title) || rawGroupName;
        resolvedGroupColor = (updated && updated.color) || desiredColor;
      } else {
        resolvedGroupTitle = rawGroupName;
        resolvedGroupColor = desiredColor;
      }
    }
  }

  return {
    bridge_version: BRIDGE_VERSION,
    opened_count: createdTabs.length,
    group_id: groupId,
    group_title: resolvedGroupTitle,
    group_color: resolvedGroupColor,
    tabs: createdTabs.map((t) => ({
      tab_id: t.id,
      window_id: t.windowId,
      title: t.title || t.pendingUrl || t.url || "",
      url: t.pendingUrl || t.url || "",
      active: Boolean(t.active),
    })),
  };
}

/**
 * Self-contained draft form-filler injected into target tabs via `chrome.scripting.executeScript`.
 *
 * IMPORTANT: Because Chrome serializes this function to run inside the target tab's isolated world,
 * it MUST NOT reference any outer closures or global variables from `background.js`.
 * Hard-blocks password, file, hidden, submit/button, disabled/readonly, and payment/SSN inputs.
 * Never submits forms.
 *
 * @param {Object<string, any>} fieldsMap - Map of `data-nexus-ref` IDs to draft values
 */
function fillFormFieldsInFrame(fieldsMap) {
  const outcomes = {};
  if (!fieldsMap || typeof fieldsMap !== "object") {
    return outcomes;
  }

  // Index every element stamped with `data-nexus-ref` in this frame
  const refElements = new Map();
  const stampedNodes = document.querySelectorAll("[data-nexus-ref]");
  for (const node of stampedNodes) {
    const refAttr = node && typeof node.getAttribute === "function" ? node.getAttribute("data-nexus-ref") : null;
    if (refAttr) {
      refElements.set(refAttr, node);
    }
  }

  const SENSITIVE_FIELD_RE =
    /(?:\bcc[-_]|credit[-_ ]?card|card[-_ ]?number|\bcv[cv]\b|\bcsc\b|security[-_ ]?code|\bssn\b|social[-_ ]?security)/i;
  const BLOCKED_INPUT_TYPES = new Set(["password", "hidden", "file", "submit", "button", "reset", "image"]);

  const dispatchInputAndChange = (el) => {
    if (!el || typeof el.dispatchEvent !== "function") return;
    for (const evtName of ["input", "change"]) {
      try {
        const evt =
          typeof Event === "function"
            ? new Event(evtName, { bubbles: true })
            : { type: evtName, bubbles: true };
        el.dispatchEvent(evt);
      } catch (_e) {}
    }
  };

  // Highlight draft-filled controls in Chrome so the user can visually verify before submitting
  const highlightFilledElement = (el) => {
    if (!el) return;
    try {
      if (el.style) {
        el.style.outline = "2px solid #0284c7";
        el.style.outlineOffset = "1px";
        el.style.boxShadow = "0 0 0 3px rgba(2, 132, 199, 0.2)";
      }
      if (typeof el.setAttribute === "function") {
        el.setAttribute("data-nexus-filled", "true");
        if (!el.getAttribute("title")) {
          el.setAttribute("title", "Draft-filled by Nexus — review before submitting");
        }
      }
    } catch (_e) {}
  };

  const resolveFieldLabel = (el) => {
    const aria = el.getAttribute && el.getAttribute("aria-label");
    if (aria) return aria.trim();
    const parentLbl = el.closest ? el.closest("label") : null;
    if (parentLbl && parentLbl.textContent) {
      return parentLbl.textContent.replace(/\s+/g, " ").trim().slice(0, 80);
    }
    const ph = el.getAttribute && el.getAttribute("placeholder");
    if (ph) return ph.trim();
    return (el.getAttribute && el.getAttribute("name")) || "";
  };

  const parseBoolValue = (raw) => {
    if (typeof raw === "boolean") return raw;
    if (typeof raw === "number") return raw === 1 ? true : raw === 0 ? false : null;
    const norm = String(raw ?? "").trim().toLowerCase();
    if (["true", "yes", "1", "checked", "on"].includes(norm)) return true;
    if (["false", "no", "0", "unchecked", "off"].includes(norm)) return false;
    return null;
  };

  for (const [refId, rawValue] of Object.entries(fieldsMap)) {
    const el = refElements.get(refId);
    if (!el) continue;

    const tag = (el.tagName || "").toUpperCase();
    const label = resolveFieldLabel(el);
    const inputType = tag === "INPUT" ? (el.getAttribute("type") || el.type || "text").toLowerCase() : "";

    // Safety Guard 1: Block forbidden input/button types (passwords, files, submit buttons)
    if (tag === "INPUT" && BLOCKED_INPUT_TYPES.has(inputType)) {
      outcomes[refId] = {
        ref: refId,
        status: "blocked",
        tag,
        label,
        reason: `Input type '${inputType}' is hard-blocked from automated filling.`,
      };
      continue;
    }

    const roleAttr = (el.getAttribute && (el.getAttribute("role") || "").toLowerCase()) || "";
    const hasPopup = (el.getAttribute && (el.getAttribute("aria-haspopup") || "").toLowerCase()) || "";
    const isInteractiveAriaButton =
      ["checkbox", "radio", "switch", "combobox"].includes(roleAttr) || hasPopup === "listbox";

    if (tag === "BUTTON" && !isInteractiveAriaButton) {
      outcomes[refId] = {
        ref: refId,
        status: "blocked",
        tag,
        label,
        reason: "Button/submit elements cannot be clicked or filled by draft automation.",
      };
      continue;
    }

    // Safety Guard 2: Block disabled/readonly controls
    if (
      Boolean(el.disabled) ||
      Boolean(el.readOnly) ||
      (el.hasAttribute && (el.hasAttribute("disabled") || el.hasAttribute("readonly"))) ||
      (el.getAttribute && el.getAttribute("aria-disabled") === "true")
    ) {
      outcomes[refId] = {
        ref: refId,
        status: "blocked",
        tag,
        label,
        reason: "Control is disabled or read-only.",
      };
      continue;
    }

    // Safety Guard 3: Block sensitive payment card / CVV / SSN heuristics
    const sensitivityHaystack = [
      el.getAttribute && el.getAttribute("autocomplete"),
      el.getAttribute && el.getAttribute("name"),
      el.id,
      el.getAttribute && el.getAttribute("aria-label"),
      el.getAttribute && el.getAttribute("placeholder"),
      label,
    ]
      .filter(Boolean)
      .join(" ");
    if (SENSITIVE_FIELD_RE.test(sensitivityHaystack)) {
      outcomes[refId] = {
        ref: refId,
        status: "blocked",
        tag,
        label,
        reason: "Sensitive payment or SSN field is hard-blocked from automated filling.",
      };
      continue;
    }

    // Fill Path A: Native checkbox or radio input
    if (tag === "INPUT" && (inputType === "checkbox" || inputType === "radio")) {
      const targetBool = parseBoolValue(rawValue);
      if (targetBool === null) {
        outcomes[refId] = {
          ref: refId,
          status: "skipped",
          tag,
          label,
          reason: `Expected boolean value for ${inputType}, got '${String(rawValue)}'.`,
        };
        continue;
      }
      if (inputType === "radio" && !targetBool) {
        outcomes[refId] = {
          ref: refId,
          status: "skipped",
          tag,
          label,
          reason: "Radio buttons cannot be unchecked directly; set the desired option to true instead.",
        };
        continue;
      }

      if (Boolean(el.checked) !== targetBool) {
        if (typeof el.click === "function") {
          el.click();
        }
        if (Boolean(el.checked) !== targetBool) {
          try {
            const proto = typeof HTMLInputElement !== "undefined" ? HTMLInputElement.prototype : null;
            const desc = proto ? Object.getOwnPropertyDescriptor(proto, "checked") : null;
            if (desc && typeof desc.set === "function") {
              desc.set.call(el, targetBool);
            } else {
              el.checked = targetBool;
            }
          } catch (_e) {
            el.checked = targetBool;
          }
          dispatchInputAndChange(el);
        }
      }
      highlightFilledElement(el);
      outcomes[refId] = {
        ref: refId,
        status: "filled",
        tag,
        label,
        new_value: Boolean(el.checked),
      };
      continue;
    }

    // Fill Path B: Native <select> dropdown (match by value, exact label, or partial label)
    if (tag === "SELECT") {
      const desired = String(rawValue ?? "").trim();
      const desiredLow = desired.toLowerCase();
      const options = Array.from(el.querySelectorAll("option"));
      let matchedOpt =
        options.find((o) => String(o.getAttribute("value") ?? o.value ?? "").trim().toLowerCase() === desiredLow) ||
        options.find((o) => (o.textContent || "").replace(/\s+/g, " ").trim().toLowerCase() === desiredLow) ||
        options.find(
          (o) => desiredLow && (o.textContent || "").replace(/\s+/g, " ").trim().toLowerCase().includes(desiredLow)
        );

      if (!matchedOpt) {
        const available = options
          .map((o) => (o.textContent || o.getAttribute("value") || "").replace(/\s+/g, " ").trim())
          .filter(Boolean)
          .slice(0, 20);
        outcomes[refId] = {
          ref: refId,
          status: "skipped",
          tag,
          label,
          reason: `Option '${desired}' not found. Available: ${available.join(" | ") || "(none)"}`,
        };
        continue;
      }

      const optVal =
        matchedOpt.getAttribute("value") !== null
          ? matchedOpt.getAttribute("value")
          : (matchedOpt.textContent || "").trim();
      for (const o of options) {
        o.selected = o === matchedOpt;
      }
      try {
        const proto = typeof HTMLSelectElement !== "undefined" ? HTMLSelectElement.prototype : null;
        const desc = proto ? Object.getOwnPropertyDescriptor(proto, "value") : null;
        if (desc && typeof desc.set === "function") {
          desc.set.call(el, optVal);
        } else {
          el.value = optVal;
        }
      } catch (_e) {
        el.value = optVal;
      }
      dispatchInputAndChange(el);
      highlightFilledElement(el);
      outcomes[refId] = {
        ref: refId,
        status: "filled",
        tag,
        label,
        new_value: (matchedOpt.textContent || optVal).replace(/\s+/g, " ").trim(),
      };
      continue;
    }

    // Fill Path C: Native text/email/url/tel/number/date <input> or <textarea>
    if (tag === "INPUT" || tag === "TEXTAREA") {
      const strVal = String(rawValue ?? "");
      if (typeof el.focus === "function") {
        try {
          el.focus();
        } catch (_e) {}
      }
      try {
        const proto =
          tag === "TEXTAREA"
            ? typeof HTMLTextAreaElement !== "undefined"
              ? HTMLTextAreaElement.prototype
              : null
            : typeof HTMLInputElement !== "undefined"
            ? HTMLInputElement.prototype
            : null;
        const desc = proto ? Object.getOwnPropertyDescriptor(proto, "value") : null;
        if (desc && typeof desc.set === "function") {
          desc.set.call(el, strVal);
        } else {
          el.value = strVal;
        }
      } catch (_e) {
        el.value = strVal;
      }
      dispatchInputAndChange(el);
      highlightFilledElement(el);
      outcomes[refId] = {
        ref: refId,
        status: "filled",
        tag,
        label,
        new_value: strVal,
      };
      continue;
    }

    // Fill Path D: Custom ARIA checkbox / radio / switch
    if (roleAttr === "checkbox" || roleAttr === "radio" || roleAttr === "switch") {
      const targetBool = parseBoolValue(rawValue);
      if (targetBool === null) {
        outcomes[refId] = {
          ref: refId,
          status: "skipped",
          tag,
          label,
          reason: `Expected boolean value for ARIA ${roleAttr}, got '${String(rawValue)}'.`,
        };
        continue;
      }
      const currBool = el.getAttribute("aria-checked") === "true";
      if (currBool !== targetBool) {
        if (typeof el.click === "function") {
          el.click();
        } else if (typeof el.setAttribute === "function") {
          el.setAttribute("aria-checked", targetBool ? "true" : "false");
          dispatchInputAndChange(el);
        }
      }
      highlightFilledElement(el);
      outcomes[refId] = {
        ref: refId,
        status: "filled",
        tag,
        label,
        new_value: targetBool,
      };
      continue;
    }

    // Fill Path E: Rich contenteditable surface
    if (el.getAttribute && el.getAttribute("contenteditable") === "true") {
      const strVal = String(rawValue ?? "");
      el.textContent = strVal;
      dispatchInputAndChange(el);
      highlightFilledElement(el);
      outcomes[refId] = {
        ref: refId,
        status: "filled",
        tag,
        label,
        new_value: strVal,
      };
      continue;
    }

    // Fill Path F: Custom non-input ARIA combobox / listbox when controlled options are open in DOM
    if (roleAttr === "combobox" || hasPopup === "listbox") {
      const desired = String(rawValue ?? "").trim().toLowerCase();
      const controlledId = (el.getAttribute("aria-controls") || el.getAttribute("aria-owns") || "").trim();
      let selectedOpt = null;
      if (controlledId) {
        const firstId = controlledId.split(/\s+/)[0];
        let listboxEl = null;
        try {
          listboxEl =
            typeof document.getElementById === "function"
              ? document.getElementById(firstId)
              : document.querySelector(`[id="${firstId}"]`);
        } catch (_e) {}
        if (listboxEl) {
          const optNodes = Array.from(listboxEl.querySelectorAll('[role="option"]'));
          selectedOpt =
            optNodes.find((o) => (o.textContent || "").replace(/\s+/g, " ").trim().toLowerCase() === desired) ||
            optNodes.find(
              (o) => desired && (o.textContent || "").replace(/\s+/g, " ").trim().toLowerCase().includes(desired)
            ) ||
            null;
        }
      }
      if (selectedOpt && typeof selectedOpt.click === "function") {
        selectedOpt.click();
        highlightFilledElement(el);
        outcomes[refId] = {
          ref: refId,
          status: "filled",
          tag,
          label,
          new_value: (selectedOpt.textContent || "").replace(/\s+/g, " ").trim(),
        };
      } else {
        outcomes[refId] = {
          ref: refId,
          status: "skipped",
          tag,
          label,
          reason: "Custom ARIA dropdown is closed or has no clickable matching option; select this field manually in Chrome.",
        };
      }
      continue;
    }

    outcomes[refId] = {
      ref: refId,
      status: "skipped",
      tag,
      label,
      reason: `Unsupported form element <${tag.toLowerCase()}>.`,
    };
  }

  return outcomes;
}

/**
 * Validates `tab_id` and `fields` and executes `fillFormFieldsInFrame` across all frames of the target tab.
 *
 * @param {Object} params
 * @param {number} params.tab_id - Target Chrome tab ID
 * @param {Object<string, any>} params.fields - Mapping of `ref` IDs to draft values
 */
async function handleFillForm(params = {}) {
  const tabId = Number(params.tab_id);
  if (!Number.isInteger(tabId) || tabId <= 0) {
    throw new Error("`tab_id` must be a positive integer Chrome tab ID.");
  }

  const fields = params.fields;
  if (!fields || typeof fields !== "object" || Array.isArray(fields)) {
    throw new Error("`fields` must be a non-empty JSON object mapping element refs to values.");
  }
  const fieldKeys = Object.keys(fields);
  if (fieldKeys.length === 0) {
    throw new Error("`fields` cannot be empty.");
  }
  if (fieldKeys.length > MAX_FILL_FIELDS) {
    throw new Error(`Cannot fill more than ${MAX_FILL_FIELDS} fields per call (received ${fieldKeys.length}).`);
  }

  const tab = await chrome.tabs.get(tabId);
  const url = (tab && tab.url) || "";
  if (
    !url ||
    url.startsWith("chrome://") ||
    url.startsWith("chrome-extension://") ||
    url.startsWith("edge://") ||
    url.startsWith("about:")
  ) {
    throw new Error(`Cannot fill forms on restricted browser URL: ${url || "(empty)"}`);
  }

  let injectionResults;
  try {
    injectionResults = await chrome.scripting.executeScript({
      target: { tabId, allFrames: true },
      func: fillFormFieldsInFrame,
      args: [fields],
    });
  } catch (_allFramesErr) {
    injectionResults = await chrome.scripting.executeScript({
      target: { tabId },
      func: fillFormFieldsInFrame,
      args: [fields],
    });
  }

  const mergedOutcomes = {};
  if (Array.isArray(injectionResults)) {
    for (const frameRes of injectionResults) {
      if (frameRes && frameRes.result && typeof frameRes.result === "object") {
        for (const [k, v] of Object.entries(frameRes.result)) {
          if (!mergedOutcomes[k]) {
            mergedOutcomes[k] = v;
          }
        }
      }
    }
  }

  const orderedResults = [];
  let filledCount = 0;
  let blockedCount = 0;
  let skippedCount = 0;
  let notFoundCount = 0;

  for (const refId of fieldKeys) {
    const entry = mergedOutcomes[refId];
    if (!entry) {
      notFoundCount += 1;
      orderedResults.push({
        ref: refId,
        status: "not_found",
        reason: "Element ref not found in live DOM (page may have reloaded; re-run read_browser_tabs with include_refs=True).",
      });
    } else {
      if (entry.status === "filled") filledCount += 1;
      else if (entry.status === "blocked") blockedCount += 1;
      else if (entry.status === "skipped") skippedCount += 1;
      orderedResults.push(entry);
    }
  }

  return {
    bridge_version: BRIDGE_VERSION,
    tab_id: tabId,
    title: (tab && tab.title) || "",
    url,
    filled_count: filledCount,
    blocked_count: blockedCount,
    skipped_count: skippedCount,
    not_found_count: notFoundCount,
    results: orderedResults,
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
