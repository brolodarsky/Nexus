/**
 * test_browser_extension_dom.js — Node.js DOM simulation test for the Nexus Browser Bridge.
 *
 * Dynamically extracts `extractTabMarkdownReadOnly` from `background.js` and tests:
 * 1. LinkedIn expanded chat bubbles extraction into `## Active Chat & Floating Overlays`
 * 2. Message sequence, sender, timestamp, and link formatting
 * 3. Minimized bubble exclusion
 * 4. Cookie consent dialog exclusion
 * 5. Clean page extraction without overlays
 */

const fs = require("fs");
const path = require("path");

const bgPath = path.resolve(__dirname, "../src/nexus/shared_tools/browser_extension/background.js");
if (!fs.existsSync(bgPath)) {
  console.error("background.js not found at " + bgPath);
  process.exit(1);
}

const bgCode = fs.readFileSync(bgPath, "utf-8");
const startIdx = bgCode.indexOf("function extractTabMarkdownReadOnly(");
const endIdx = bgCode.indexOf("async function handleReadTabs(");

if (startIdx === -1 || endIdx === -1) {
  console.error("Could not locate extractTabMarkdownReadOnly in background.js");
  process.exit(1);
}

const funcCode = bgCode.slice(startIdx, endIdx).trim();

// Lightweight Mock DOM for Node.js
class MockNode {
  constructor(tag, attrs = {}, text = "") {
    this.tagName = tag.toUpperCase();
    this.nodeType = 1;
    this.attrs = { ...attrs };
    this.className = attrs.class || "";
    this.id = attrs.id || "";
    this.children = [];
    this.parentElement = null;
    this.shadowRoot = null;
    this._text = text;
    if (attrs.href) this.href = attrs.href;
    if (text) this.appendChild(new MockTextNode(text));
  }

  getAttribute(name) { return this.attrs[name] ?? null; }
  hasAttribute(name) { return name in this.attrs; }
  get textContent() {
    if (this._text && this.children.length === 0) return this._text;
    return this.children.map(c => c.textContent || c.nodeValue || "").join("");
  }
  appendChild(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }
  get childNodes() { return this.children; }
  closest(selector) {
    let curr = this;
    while (curr) {
      if (curr.matches && curr.matches(selector)) return curr;
      curr = curr.parentElement;
    }
    return null;
  }
  matches(selector) {
    const parts = selector.split(",").map(p => p.trim());
    return parts.some(sel => {
      let s = sel;
      let notFilter = null;
      const notMatch = s.match(/:not\(([^)]+)\)/);
      if (notMatch) {
        notFilter = notMatch[1];
        s = s.replace(notMatch[0], "");
      }
      if (notFilter && this.matches(notFilter)) return false;

      let tagMatch = true, classMatch = true, attrMatch = true, idMatch = true;
      const idParts = s.match(/#[\w-]+/g);
      if (idParts) {
        idMatch = idParts.every(id => this.id === id.slice(1));
        s = s.replace(/#[\w-]+/g, "");
      }
      const tagPart = s.match(/^[a-zA-Z0-9]+/);
      if (tagPart) {
        tagMatch = this.tagName.toLowerCase() === tagPart[0].toLowerCase();
        s = s.slice(tagPart[0].length);
      }
      const classParts = s.match(/\.[\w-]+/g);
      if (classParts) {
        const nodeClasses = this.className.split(/\s+/);
        classMatch = classParts.every(c => nodeClasses.includes(c.slice(1)));
        s = s.replace(/\.[\w-]+/g, "");
      }
      const attrParts = s.match(/\[([^\]]+)\]/g);
      if (attrParts) {
        attrMatch = attrParts.every(ap => {
          const inner = ap.slice(1, -1);
          if (inner.includes("=")) {
            const [k, v] = inner.split("=");
            const cleanV = v.replace(/['"]/g, "");
            if (k.endsWith("*")) {
              return (this.getAttribute(k.slice(0, -1)) || "").includes(cleanV);
            }
            return this.getAttribute(k) === cleanV;
          }
          return this.hasAttribute(inner);
        });
      }
      return tagMatch && classMatch && attrMatch && idMatch;
    });
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  querySelectorAll(selector) {
    const results = [];
    const parts = selector.split(",").map(p => p.trim());
    const matchOne = (node, sel) => {
      if (!node || node.nodeType !== 1 || typeof node.matches !== "function") return false;
      const tokens = sel.split(/\s+/);
      if (tokens.length === 1) return node.matches(tokens[0]);
      if (node.matches(tokens[tokens.length - 1])) {
        let p = node.parentElement;
        for (let i = tokens.length - 2; i >= 0; i--) {
          while (p && !p.matches(tokens[i])) p = p.parentElement;
          if (!p) return false;
          p = p.parentElement;
        }
        return true;
      }
      return false;
    };
    const traverse = (node) => {
      if (!node || !node.children) return;
      for (const child of node.children) {
        for (const sel of parts) {
          if (matchOne(child, sel)) {
            if (!results.includes(child)) results.push(child);
            break;
          }
        }
        traverse(child);
      }
    };
    traverse(this);
    return results;
  }
  cloneNode(deep = true) {
    const clone = new MockNode(this.tagName, { ...this.attrs }, this._text);
    if (deep) {
      for (const c of this.children) clone.appendChild(c.cloneNode(deep));
    }
    return clone;
  }
  remove() {
    if (this.parentElement) {
      const idx = this.parentElement.children.indexOf(this);
      if (idx !== -1) this.parentElement.children.splice(idx, 1);
      this.parentElement = null;
    }
  }
}

class MockTextNode {
  constructor(text) {
    this.nodeType = 3;
    this.nodeValue = text;
    this.textContent = text;
    this.parentElement = null;
  }
}

global.Node = { ELEMENT_NODE: 1, TEXT_NODE: 3 };
global.window = {
  location: { href: "https://www.linkedin.com/jobs/view/999" },
  getComputedStyle: () => ({ display: "block", visibility: "visible" }),
};

// ── Test 1: Page with LinkedIn Expanded Overlay & Messages ──
const root = new MockNode("html");
const body = root.appendChild(new MockNode("body"));
const main = body.appendChild(new MockNode("main"));
main.appendChild(new MockNode("h1", {}, "Senior AI Engineer - Nexus Core Team"));
main.appendChild(new MockNode("p", {}, "We are seeking a Senior AI Engineer to architect, build, and maintain production autonomous multi-agent swarms, local tool execution bridges, and real-time Chrome browser integrations. The ideal candidate has deep expertise in Python, asyncio, LangGraph, TypeScript, and modern distributed systems. You will collaborate closely with product and systems engineering to deliver high-reliability agentic workflows."));

const aside = body.appendChild(new MockNode("aside", { class: "msg-overlay-container" }));

// Minimized bubble (should be skipped)
const minBubble = aside.appendChild(new MockNode("div", { class: "msg-overlay-conversation-bubble msg-overlay-conversation-bubble--is-minimized" }));
minBubble.appendChild(new MockNode("header", { class: "msg-overlay-bubble-header" }))
  .appendChild(new MockNode("h2", { class: "msg-overlay-bubble-header__title" }, "Hidden Minimized"));

// Expanded bubble
const expBubble = aside.appendChild(new MockNode("div", { class: "msg-overlay-conversation-bubble msg-overlay-conversation-bubble--is-expanded" }));
const expHeader = expBubble.appendChild(new MockNode("header", { class: "msg-overlay-bubble-header" }));
const titleH2 = expHeader.appendChild(new MockNode("h2", { class: "msg-overlay-bubble-header__title" }));
titleH2.appendChild(new MockNode("a", { href: "https://www.linkedin.com/in/janedoe/" }, "Jane Doe, 1st"));
expHeader.appendChild(new MockNode("span", { class: "msg-overlay-bubble-header__status" }, "Active now"));

const listUl = expBubble.appendChild(new MockNode("div", { class: "msg-s-message-list-container" }))
  .appendChild(new MockNode("ul", { class: "msg-s-message-list" }));

const grp1 = listUl.appendChild(new MockNode("li", { class: "msg-s-message-group" }));
const meta1 = grp1.appendChild(new MockNode("div", { class: "msg-s-message-group__meta" }));
meta1.appendChild(new MockNode("span", { class: "msg-s-message-group__name" }, "Jane Doe"));
meta1.appendChild(new MockNode("time", { class: "msg-s-message-group__timestamp" }, "10:14 AM"));

const evt1 = grp1.appendChild(new MockNode("div", { class: "msg-s-event-listitem" }));
const b1 = evt1.appendChild(new MockNode("div", { class: "msg-s-event-listitem__body" }));
b1.appendChild(new MockTextNode("Hi William, saw your profile! Check role: "));
b1.appendChild(new MockNode("a", { href: "https://jobs.example.com/ai-eng" }, "AI Engineer"));

const grp2 = listUl.appendChild(new MockNode("li", { class: "msg-s-message-group msg-s-message-group--viewer" }));
const meta2 = grp2.appendChild(new MockNode("div", { class: "msg-s-message-group__meta" }));
meta2.appendChild(new MockNode("span", { class: "msg-s-message-group__name" }, "William"));
meta2.appendChild(new MockNode("time", { class: "msg-s-message-group__timestamp" }, "10:20 AM"));

const evt2 = grp2.appendChild(new MockNode("div", { class: "msg-s-event-listitem" }));
const b2 = evt2.appendChild(new MockNode("div", { class: "msg-s-event-listitem__body" }));
b2.appendChild(new MockTextNode("Thanks Jane, reviewing the job spec now!"));

// Cookie dialog (must be ignored)
body.appendChild(new MockNode("div", { role: "dialog", class: "cookie-consent-banner" }))
  .appendChild(new MockNode("p", {}, "Accept cookies"));

global.document = root;
global.document.title = "Senior AI Engineer Job";
global.document.body = body;

// Evaluate extractTabMarkdownReadOnly
const evalFunc = new Function(`${funcCode}; return extractTabMarkdownReadOnly;`)();
const result1 = evalFunc(20000);

// Assertions on result 1
if (!result1.markdown.includes("## Active Chat & Floating Overlays")) throw new Error("Missing Active Chat header");
if (!result1.markdown.includes("### Jane Doe")) throw new Error("Missing Jane Doe participant header");
if (!result1.markdown.includes("- **Sender:** Jane Doe (10:14 AM)")) throw new Error("Missing Jane Doe sender line");
if (!result1.markdown.includes("> Hi William, saw your profile! Check role: [AI Engineer](https://jobs.example.com/ai-eng)")) throw new Error("Missing Jane Doe message body or link");
if (!result1.markdown.includes("- **Sender:** William (10:20 AM)")) throw new Error("Missing William sender line");
if (!result1.markdown.includes("> Thanks Jane, reviewing the job spec now!")) throw new Error("Missing William message body");

if (result1.markdown.includes("Active now")) throw new Error("Status indicator 'Active now' was not stripped");
if (result1.markdown.includes("Hidden Minimized")) throw new Error("Minimized bubble was not skipped");
if (result1.markdown.includes("Accept cookies")) throw new Error("Cookie consent banner was not skipped");

// ── Test 2: Clean Page with No Overlays ──
const root2 = new MockNode("html");
const body2 = root2.appendChild(new MockNode("body"));
const main2 = body2.appendChild(new MockNode("main"));
main2.appendChild(new MockNode("h1", {}, "Clean Documentation Page"));
main2.appendChild(new MockNode("p", {}, "This is standard documentation content for the Nexus browser bridge. It provides a comprehensive explanation of how read-only DOM extraction works, ensuring that pages with no floating overlays or active dialogs return clean rendered Markdown without any injected overlay sections. The progressive enhancement model guarantees zero side effects for ordinary web pages."));

global.document = root2;
global.document.title = "Documentation";
global.document.body = body2;

const result2 = evalFunc(20000);
if (result2.markdown.includes("## Active Chat & Floating Overlays")) {
  throw new Error("Clean page should not contain Active Chat header");
}
if (!result2.markdown.includes("Clean Documentation Page")) {
  throw new Error("Missing main content on clean page");
}

console.log("All Node.js browser extension DOM tests passed successfully!");
