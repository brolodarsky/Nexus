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
    this.style = attrs.style && typeof attrs.style === "object" ? { ...attrs.style } : {};
    if (attrs.value !== undefined) this.value = String(attrs.value);
    if (attrs.checked !== undefined) this.checked = Boolean(attrs.checked);
    if (attrs.selected !== undefined) this.selected = Boolean(attrs.selected);
    if (attrs.required !== undefined) this.required = Boolean(attrs.required);
    if (attrs.multiple !== undefined) this.multiple = Boolean(attrs.multiple);
    if (attrs.rect && typeof attrs.rect === "object") {
      this.getBoundingClientRect = () => ({ ...attrs.rect });
    }
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

function attachDocumentHelpers(docNode, title, bodyNode) {
  docNode.title = title;
  docNode.body = bodyNode;
  // Minimal `createElement` shim supporting `stripHtmlTags()` inside `extractTabMarkdownReadOnly`
  docNode.createElement = (_tag) => {
    let rawHtml = "";
    const decodeEntitiesAndStrip = (s) =>
      String(s || "")
        .replace(/&lt;/g, "<")
        .replace(/&gt;/g, ">")
        .replace(/&amp;/g, "&")
        .replace(/&quot;/g, '"')
        .replace(/&#39;/g, "'")
        .replace(/&nbsp;/g, " ")
        .replace(/<[^>]+>/g, " ")
        .replace(/\s+/g, " ")
        .trim();
    return {
      set innerHTML(val) {
        rawHtml = String(val || "");
      },
      get textContent() {
        return decodeEntitiesAndStrip(rawHtml);
      },
      get innerText() {
        return decodeEntitiesAndStrip(rawHtml);
      },
    };
  };
  return docNode;
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
  getComputedStyle: (el) => ({ display: "block", visibility: "visible", ...(el && el.style ? el.style : {}) }),
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

global.document = attachDocumentHelpers(root, "Senior AI Engineer Job", body);

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

global.document = attachDocumentHelpers(root2, "Documentation", body2);

const result2 = evalFunc(20000);
if (result2.markdown.includes("## Active Chat & Floating Overlays")) {
  throw new Error("Clean page should not contain Active Chat header");
}
if (!result2.markdown.includes("Clean Documentation Page")) {
  throw new Error("Missing main content on clean page");
}

// ── Test 3: Rich DOM with duplicate metaDescription + duplicate JobPosting JSON-LD (no payload tripling) ──
const sharedJdParagraph =
  "Merge is the connectivity layer for AI agents. Build scalable enterprise API integrations, lead technical discovery sessions, architect proof-of-concept connectors in Python and TypeScript, and collaborate with product engineering across customer deployments.";
const bottomMarker = "EQUAL_OPPORTUNITY_BOTTOM_ANCHOR_TEXT_PRESERVED";
const root3 = new MockNode("html");
const head3 = root3.appendChild(new MockNode("head"));
head3.appendChild(new MockNode("meta", { name: "description", content: sharedJdParagraph }));
head3.appendChild(
  new MockNode(
    "script",
    { type: "application/ld+json" },
    JSON.stringify({
      "@type": "JobPosting",
      title: "Solutions Engineer",
      hiringOrganization: { name: "Merge" },
      description: `<p>${sharedJdParagraph}</p>`,
    })
  )
);
const body3 = root3.appendChild(new MockNode("body"));
const main3 = body3.appendChild(new MockNode("main"));
main3.appendChild(new MockNode("h1", {}, "Solutions Engineer"));
main3.appendChild(new MockNode("p", {}, sharedJdParagraph));
main3.appendChild(new MockNode("p", {}, `Compensation and benefits details. ${bottomMarker}`));

global.document = attachDocumentHelpers(root3, "Solutions Engineer @ Merge", body3);
const result3 = evalFunc(1500);
if (result3.markdown.includes("**Meta Description:**")) {
  throw new Error("Rich DOM should NOT duplicate Meta Description");
}
if (result3.markdown.includes("### Structured Schema")) {
  throw new Error("Rich DOM should NOT duplicate Structured Schema JobPosting when text is already in cleanMarkdown");
}
if (!result3.markdown.includes(bottomMarker)) {
  throw new Error("Bottom of cleanMarkdown was unexpectedly dropped/truncated");
}

// ── Test 4: /application form subpage (long form DOM lacking JD) + JobPosting JSON-LD + duplicate metaDescription ──
const root4 = new MockNode("html");
const head4 = root4.appendChild(new MockNode("head"));
head4.appendChild(new MockNode("meta", { name: "description", content: sharedJdParagraph }));
head4.appendChild(
  new MockNode(
    "script",
    { type: "application/ld+json" },
    JSON.stringify({
      "@type": "JobPosting",
      title: "Solutions Engineer",
      hiringOrganization: { name: "Merge" },
      description: `<p>${sharedJdParagraph}</p>`,
    })
  )
);
const body4 = root4.appendChild(new MockNode("body"));
const main4 = body4.appendChild(new MockNode("main"));
main4.appendChild(new MockNode("h1", {}, "Apply for Solutions Engineer"));
main4.appendChild(
  new MockNode(
    "p",
    {},
    "Application Form: First Name, Last Name, Email Address, Phone Number, LinkedIn Profile URL, Resume Upload, Work Authorization Sponsorship Question, Voluntary Equal Employment Opportunity Self-Identification Disclosure, Veteran Status, Disability Self-Identification Form. Please verify all fields before submitting your application."
  )
);

global.document = attachDocumentHelpers(root4, "Apply — Solutions Engineer", body4);
const result4 = evalFunc(20000);
if (!result4.markdown.includes("### Structured Schema (JobPosting)")) {
  throw new Error("/application form subpage missing JD text MUST include JobPosting JSON-LD");
}
if (!result4.markdown.includes("Merge is the connectivity layer for AI agents.")) {
  throw new Error("Included JobPosting JSON-LD must preserve the schema description");
}
if (result4.markdown.includes("**Meta Description:**")) {
  throw new Error("Duplicate Meta Description must be suppressed once JSON-LD fallback already covers it");
}

// ── Test 5: Sparse SPA shell DOM + substantial metaDescription (no JSON-LD) ──
const root5 = new MockNode("html");
const head5 = root5.appendChild(new MockNode("head"));
head5.appendChild(new MockNode("meta", { name: "description", content: sharedJdParagraph }));
const body5 = root5.appendChild(new MockNode("body"));
body5.appendChild(new MockNode("p", {}, "Loading application..."));

global.document = attachDocumentHelpers(root5, "Loading...", body5);
const result5 = evalFunc(20000);
if (!result5.markdown.includes("**Meta Description:**")) {
  throw new Error("Sparse SPA shell DOM without JSON-LD MUST include substantial Meta Description");
}

// ── Test 6: Luma-style non-ARIA fixed portal registration modal + form controls ──
const root6 = new MockNode("html");
const body6 = root6.appendChild(new MockNode("body"));
const next6 = body6.appendChild(new MockNode("div", { id: "__next" }));
const main6 = next6.appendChild(new MockNode("main"));
main6.appendChild(new MockNode("h1", {}, "Health Frontier NYC Hackathon"));
main6.appendChild(
  new MockNode(
    "p",
    {},
    "AI x Health x Bio Hackathon in New York City. Join 100 engineers, founders, researchers, and builders for a 1.5-day hands-on sprint exploring clinical AI, personal health agents, biology, and reliable AI infrastructure with experienced mentors, curated healthcare datasets, technical demos, and technology partners across New York City."
  )
);

const portal6 = body6.appendChild(
  new MockNode("div", {
    class: "lux-modal-backdrop",
    style: { position: "fixed" },
    rect: { width: 520, height: 680 },
  })
);
portal6.appendChild(new MockNode("h2", {}, "Your Info"));
portal6.appendChild(new MockNode("p", {}, "William Volodarsky (bill@williamvolodarsky.com)"));
const form6 = portal6.appendChild(new MockNode("form"));

const lblCompany = form6.appendChild(new MockNode("label", {}, "What company do you work for? *"));
lblCompany.appendChild(new MockNode("input", { type: "text", required: true, value: "" }));

const lblTitle = form6.appendChild(new MockNode("label", {}, "What is your job title? *"));
lblTitle.appendChild(new MockNode("input", { type: "text", required: true, value: "" }));

const lblLinkedin = form6.appendChild(new MockNode("label", {}, "What's your LinkedIn profile? *"));
lblLinkedin.appendChild(
  new MockNode("input", { type: "url", required: true, value: "https://linkedin.com/in/william" })
);

const lblGithub = form6.appendChild(
  new MockNode("label", {}, "What's your Github, Gitlab, Bitbucket or other profile? (N/A if none)")
);
lblGithub.appendChild(new MockNode("input", { type: "text", placeholder: "github.com/username" }));

const lblWhy = form6.appendChild(new MockNode("label", {}, "Why do you want to join?"));
lblWhy.appendChild(
  new MockNode(
    "textarea",
    { required: true, placeholder: "Tell us about your project" },
    "Building local multi-agent systems"
  )
);

const lblLevel = form6.appendChild(new MockNode("label", {}, "Experience Level"));
const selLevel = lblLevel.appendChild(new MockNode("select", { required: true }));
selLevel.appendChild(new MockNode("option", { value: "junior" }, "Junior"));
selLevel.appendChild(new MockNode("option", { value: "senior", selected: true }, "Senior"));
selLevel.appendChild(new MockNode("option", { value: "staff" }, "Staff"));

const lblTerms = form6.appendChild(new MockNode("label"));
lblTerms.appendChild(new MockNode("input", { type: "checkbox", checked: true }));
lblTerms.appendChild(new MockTextNode("Agree to hackathon rules"));

const lblSkills = form6.appendChild(new MockNode("label", {}, "What's your primary skill set? *"));
lblSkills.appendChild(
  new MockNode(
    "div",
    { role: "combobox", "aria-required": "true", "aria-controls": "skills-lb" },
    "Select one or more"
  )
);
const listbox6 = portal6.appendChild(new MockNode("div", { id: "skills-lb", role: "listbox" }));
listbox6.appendChild(new MockNode("div", { role: "option" }, "AI/ML Engineering"));
listbox6.appendChild(new MockNode("div", { role: "option" }, "Full-Stack"));

const lblPlan = form6.appendChild(new MockNode("label", {}, "How do you plan to participate? *"));
lblPlan.appendChild(
  new MockNode("button", { role: "combobox", "aria-haspopup": "listbox", "aria-required": "true" }, "Select an option")
);

global.document = attachDocumentHelpers(root6, "Health Frontier NYC Hackathon · Luma", body6);
const result6 = evalFunc(20000);
if (!result6.markdown.includes("## Active Modal / Dialog")) throw new Error("Test 6 missing Active Modal / Dialog header");
if (!result6.markdown.includes("### Your Info")) throw new Error("Test 6 missing Your Info modal header");
if (!result6.markdown.includes("What company do you work for? *")) throw new Error("Test 6 missing company label");
if (!result6.markdown.includes("What is your job title? *")) throw new Error("Test 6 missing job title label");
if (!result6.markdown.includes("What's your LinkedIn profile? *")) throw new Error("Test 6 missing LinkedIn label");
if (!result6.markdown.includes("https://linkedin.com/in/william")) throw new Error("Test 6 missing typed URL value");
if (!result6.markdown.includes('placeholder="github.com/username"')) throw new Error("Test 6 missing placeholder");
if (!result6.markdown.includes("Building local multi-agent systems")) throw new Error("Test 6 missing textarea value");
if (!result6.markdown.includes('selected="Senior"') || !result6.markdown.includes("Junior | Senior | Staff")) {
  throw new Error("Test 6 missing select value or options");
}
if (!result6.markdown.includes("[x] Agree to hackathon rules")) throw new Error("Test 6 missing checked checkbox");
if (!result6.markdown.includes("Select one or more") || !result6.markdown.includes("AI/ML Engineering | Full-Stack")) {
  throw new Error("Test 6 missing combobox label or controlled options");
}
if (!result6.markdown.includes("Select an option")) throw new Error("Test 6 missing second combobox");
if (!result6.markdown.includes("Join 100 engineers, founders, researchers")) {
  throw new Error("Test 6 missing background event description");
}
if (result6.markdown.includes("- **Sender:**")) {
  throw new Error("Test 6 must NOT mislabel registration modal as chat Sender");
}

// ── Test 7: Form dialog containing `data-testid="error-message"` (must not trigger chat mode) ──
const root7 = new MockNode("html");
const body7 = root7.appendChild(new MockNode("body"));
const main7 = body7.appendChild(new MockNode("main"));
main7.appendChild(new MockNode("p", {}, "Background application overview content that exceeds minimum length thresholds for semantic primary extraction in Nexus Browser Bridge DOM parsing tests."));
const dlg7 = body7.appendChild(new MockNode("div", { role: "dialog", "aria-modal": "true" }));
dlg7.appendChild(new MockNode("h2", {}, "Complete Application"));
dlg7.appendChild(new MockNode("p", { "data-testid": "error-message" }, "Please fix highlighted fields."));
const f7 = dlg7.appendChild(new MockNode("form"));
f7.appendChild(new MockNode("label", {}, "Full Name *")).appendChild(new MockNode("input", { type: "text", required: true }));
f7.appendChild(new MockNode("label", {}, "Email *")).appendChild(new MockNode("input", { type: "email", required: true }));

global.document = attachDocumentHelpers(root7, "Complete Application", body7);
const result7 = evalFunc(20000);
if (!result7.markdown.includes("## Active Modal / Dialog")) throw new Error("Test 7 missing Active Modal / Dialog");
if (result7.markdown.includes("## Active Chat & Floating Overlays") || result7.markdown.includes("- **Sender:**")) {
  throw new Error("Test 7 form dialog with error-message testid was hijacked by chat parser");
}
if (!result7.markdown.includes("Full Name *") || !result7.markdown.includes("Email *")) {
  throw new Error("Test 7 dropped form inputs");
}

// ── Test 8: Truncation budget protection preserves active `aria-modal="true"` form dialog ──
const root8 = new MockNode("html");
const body8 = root8.appendChild(new MockNode("body"));
const main8 = body8.appendChild(new MockNode("main"));
const longFiller = "Detailed background hackathon logistics and partner descriptions. ".repeat(80);
main8.appendChild(new MockNode("p", {}, longFiller));
const dlg8 = body8.appendChild(new MockNode("div", { "aria-modal": "true" }));
dlg8.appendChild(new MockNode("h2", {}, "Registration Questions"));
const f8 = dlg8.appendChild(new MockNode("form"));
f8.appendChild(new MockNode("label", {}, "Target Role *")).appendChild(new MockNode("input", { type: "text", required: true }));

global.document = attachDocumentHelpers(root8, "Long Event Page", body8);
const result8 = evalFunc(1200);
if (!result8.truncated) throw new Error("Test 8 expected truncated === true");
if (!result8.markdown.includes("## Active Modal / Dialog") || !result8.markdown.includes("Target Role *")) {
  throw new Error("Test 8 truncated away active modal form fields");
}

// ── Test 9: Closed opacity:0 modal skipped & password field redacted ──
const root9 = new MockNode("html");
const body9 = root9.appendChild(new MockNode("body"));
const main9 = body9.appendChild(new MockNode("main"));
main9.appendChild(new MockNode("h1", {}, "Account Security"));
const loginForm9 = main9.appendChild(new MockNode("form"));
loginForm9.appendChild(new MockNode("label", {}, "Password")).appendChild(
  new MockNode("input", { type: "password", value: "SuperSecret99!" })
);
main9.appendChild(
  new MockNode(
    "p",
    {},
    "Additional security policy details ensuring the main container passes semantic extraction thresholds cleanly across DOM runs. Two-factor authentication, hardware security keys, session timeouts, and strict password hygiene protect your workspace account against unauthorized access across all connected sessions."
  )
);
const hiddenModal9 = body9.appendChild(
  new MockNode("div", { class: "lux-modal", style: { position: "fixed", opacity: "0" } })
);
hiddenModal9.appendChild(new MockNode("h2", {}, "CLOSED_OPACITY_ZERO_MODAL"));
hiddenModal9.appendChild(new MockNode("p", {}, "This closed modal content must never appear in extracted markdown."));

global.document = attachDocumentHelpers(root9, "Account Security", body9);
const result9 = evalFunc(20000);
if (result9.markdown.includes("CLOSED_OPACITY_ZERO_MODAL")) {
  throw new Error("Test 9 failed to skip opacity:0 closed modal");
}
if (result9.markdown.includes("SuperSecret99!") || !result9.markdown.includes("(redacted)")) {
  throw new Error("Test 9 failed to redact password input value");
}

console.log("All Node.js browser extension DOM tests passed successfully!");
