/**
 * test_markdown_math.js — Node.js regression suite for `MarkdownMessage.tsx` math & currency parsing.
 *
 * Verifies:
 * 1. Digit-prefixed inline LaTeX math (e.g. `$2^{\Omega(n)}$`, `$2n + 1$`, `$0.4$`, `$3$-SAT`) is not escaped as currency.
 * 2. Prose currency amounts (`$41.20`, `$150k`, `$50–$100`, `$1,200.50`, mixed `$50 and $x = 2$`) are escaped cleanly.
 * 3. Inline code spans and display math (`$$...$$`) remain untouched.
 * 4. Installed `katex` version matches `rehype-katex` (`0.16.x`) with no nested version drift (ensuring `\neq` `.rlap > .inner` CSS matches).
 */

const fs = require("fs");
const path = require("path");
const assert = require("assert");
const Module = require("module");
const { pathToFileURL } = require("url");

const repoRoot = path.resolve(__dirname, "..");
const guiDir = path.join(repoRoot, "gui");
const ts = require(path.join(guiDir, "node_modules", "typescript"));

// Transpile MarkdownMessage.tsx in memory with lightweight stubs for React/Next UI imports
const mdSource = fs.readFileSync(path.join(guiDir, "src", "components", "MarkdownMessage.tsx"), "utf8");
const compiled = ts.transpileModule(mdSource, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
    jsx: ts.JsxEmit.React,
  },
}).outputText;

const origLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (["react", "next/link", "react-markdown", "remark-gfm", "remark-math", "rehype-katex", "unified"].includes(request)) {
    const noop = () => null;
    const createElement = (type, props, ...children) => ({
      type,
      props: { ...(props || {}), children: children.length <= 1 ? children[0] : children },
    });
    return {
      __esModule: true,
      default: {
        createElement,
        Children: { toArray: (c) => (Array.isArray(c) ? c : c ? [c] : []) },
        isValidElement: () => false,
      },
      memo: (component) => component,
      useMemo: (factory) => factory(),
      createContext: () => ({}),
      useContext: () => undefined,
    };
  }
  return origLoad.apply(this, arguments);
};

const mod = new Module("MarkdownMessage.js");
mod._compile(compiled, "MarkdownMessage.js");
const { preprocessObsidianMarkdown, MARKDOWN_COMPONENTS } = mod.exports;

(async () => {
  // Verify KaTeX CSS/JS alignment (must both resolve to 0.16.x with no nested rehype-katex override)
  const topKatexPkg = JSON.parse(fs.readFileSync(path.join(guiDir, "node_modules", "katex", "package.json"), "utf8"));
  assert(topKatexPkg.version.startsWith("0.16."), `Expected top-level katex 0.16.x, got ${topKatexPkg.version}`);
  assert(
    !fs.existsSync(path.join(guiDir, "node_modules", "rehype-katex", "node_modules", "katex", "package.json")),
    "Unexpected nested katex inside rehype-katex; CSS/DOM class mismatch risk"
  );

  const { unified } = await import(pathToFileURL(path.join(guiDir, "node_modules", "unified", "index.js")).href);
  const { default: remarkParse } = await import(pathToFileURL(path.join(guiDir, "node_modules", "remark-parse", "index.js")).href);
  const { default: remarkGfm } = await import(pathToFileURL(path.join(guiDir, "node_modules", "remark-gfm", "index.js")).href);
  const { default: remarkMath } = await import(pathToFileURL(path.join(guiDir, "node_modules", "remark-math", "index.js")).href);
  const { default: remarkRehype } = await import(pathToFileURL(path.join(guiDir, "node_modules", "remark-rehype", "index.js")).href);
  const { default: rehypeKatex } = await import(pathToFileURL(path.join(guiDir, "node_modules", "rehype-katex", "index.js")).href);

  const processor = unified()
    .use(remarkParse)
    .use(remarkGfm)
    .use(remarkMath)
    .use(remarkRehype)
    .use(rehypeKatex, { strict: false, throwOnError: false });

  async function renderAst(md) {
    const pre = preprocessObsidianMarkdown(md);
    const tree = await processor.run(processor.parse(pre));
    return { pre, json: JSON.stringify(tree) };
  }

  // 1. Exact ETH / P != NP line from production chat failure
  const ethLine =
    "* While $P \\neq NP$ merely says NP-complete problems (like **3-SAT**) cannot be solved in *polynomial* time ($O(n^k)$), **ETH asserts they cannot even be solved in *subexponential* time**—they strictly require $2^{\\Omega(n)}$ (exponential time, $c^n$ where $c > 1$).";
  const ethRes = await renderAst(ethLine);
  assert(!ethRes.pre.includes("\\$2"), "Digit-prefixed math $2^{\\Omega(n)}$ must not be escaped");
  assert(ethRes.json.includes(`"value":${JSON.stringify("P \\neq NP")}`), "Expected P \\neq NP KaTeX node");
  assert(ethRes.json.includes(`"value":${JSON.stringify("2^{\\Omega(n)}")}`), "Expected 2^{\\Omega(n)} KaTeX node");
  assert(ethRes.json.includes(`"value":${JSON.stringify("c^n")}`), "Expected c^n KaTeX node");
  assert(ethRes.json.includes(`"value":${JSON.stringify("c > 1")}`), "Expected c > 1 KaTeX node");
  assert(ethRes.json.includes('"className":["inner"]'), "Expected KaTeX 0.16 .inner class matching CSS");
  assert(!ethRes.json.includes("katex-inner"), "Unexpected KaTeX 0.19 .katex-inner class");

  // 2. Digit-prefixed inline math variants
  for (const [input, expectedTex] of [
    ["$0.4$", "0.4"],
    ["$100$", "100"],
    ["$3$-SAT", "3"],
    ["$2n + 1$", "2n + 1"],
    ["$2 \\times 3 = 6$", "2 \\times 3 = 6"],
    ["$100 \\text{ ms}$", "100 \\text{ ms}"],
    ["$2_i$", "2_i"],
    ["$2(x + 1)$", "2(x + 1)"],
    ["$100\\%$", "100\\%"],
  ]) {
    const res = await renderAst(input);
    assert(res.json.includes(`"value":${JSON.stringify(expectedTex)}`), `Failed math case: ${input} -> ${res.pre}`);
  }

  // 3. Conversational currency figures (must escape and avoid false math pairing)
  for (const input of [
    "Costs $41.20 today.",
    "Salary is $150k.",
    "Range is $50–$100.",
    "Range is $50 to $100.",
    "Budget $1,200.50 and $2,500.",
    "Costs $50, and $x = 2$.",
    "$50 + $100 = $150",
    "$50-$100",
    "It costs $50 and $2x$.",
  ]) {
    const res = await renderAst(input);
    if (input.includes("$x = 2$")) {
      assert(res.pre.startsWith("Costs \\$50") && res.json.includes('"value":"x = 2"'), `Mixed currency+math failed: ${res.pre}`);
    } else if (input.includes("$2x$")) {
      assert(res.pre.includes("\\$50") && res.json.includes('"value":"2x"'), `Mixed currency+2x failed: ${res.pre}`);
    } else {
      assert(!res.json.includes('"katex"'), `Currency falsely parsed as math: ${input} -> ${res.pre}`);
    }
  }

  // 4. Inline code and display math preservation
  const protectedText = preprocessObsidianMarkdown("Use `$50` in bash and $$2^{\\Omega(n)}$$ in display math.");
  assert(protectedText.includes("`$50`"), `Inline code span was mutated: ${protectedText}`);
  assert(protectedText.includes("$$2^{\\Omega(n)}$$"), `Display math was mutated: ${protectedText}`);

  // 5. Escaped currency `\$` inside inline math (screenshot 1 & real Vault notes)
  const seniorFilterLine = "the **strict $\\ge\\$160\\text{k}$ base-floor senior filter**";
  const seniorFilterRes = await renderAst(seniorFilterLine);
  assert(
    seniorFilterRes.pre.includes("$\\ge{\\char36}160\\text{k}$"),
    `Expected \\$ inside inline math to rewrite to {\\char36}, got: ${seniorFilterRes.pre}`
  );
  assert(seniorFilterRes.json.includes('"katex"'), "Expected KaTeX output for $\\ge\\$160\\text{k}$");
  assert(!seniorFilterRes.json.includes("katex-error"), `Unexpected KaTeX error node: ${seniorFilterRes.json}`);
  assert(!seniorFilterRes.json.includes("#cc0000"), `Unexpected KaTeX error color: ${seniorFilterRes.json}`);
  assert(
    !seniorFilterRes.json.includes('"value":"160\\\\text{k}$'),
    `Trailing math fragment leaked into prose: ${seniorFilterRes.json}`
  );

  for (const input of [
    "**Rate:** \\$60.00/hr on W2 ($\\approx \\$124,800$/year base). Matches the $100K–$130K market target band.",
    "| **Total** | **$\\approx \\mathbf{\\$30,000 – \\$50,000+/year}$** | **$\\approx \\mathbf{\\$30,000 – \\$35,000/year}$** |",
    "$180 \\text{ input tokens} \\times \\$0.075/\\text{M} + 6 \\text{ output tokens} \\times \\$0.30/\\text{M} \\approx \\mathbf{\\$0.0000153}$",
    "$\\text{cost: \\$160k}$",
    "\\(\\ge \\$160\\text{k}\\)",
    "\\( \\ge \\$160\\text{k} \\)",
    "$\\$$",
  ]) {
    const res = await renderAst(input);
    assert(res.json.includes('"katex"'), `Expected KaTeX output for: ${input} (pre=${res.pre})`);
    assert(!res.json.includes("katex-error"), `Unexpected KaTeX error for: ${input} (pre=${res.pre})`);
    assert(!res.json.includes("#cc0000"), `Unexpected KaTeX error color for: ${input} (pre=${res.pre})`);
  }

  // 6. Inline code protection for LaTeX examples vs backticked Obsidian note links
  const codeAndLinks = preprocessObsidianMarkdown(
    "Use `$\\ge \\$160\\text{k}$` and `\\rightarrow` verbatim; see `Gameplan.md`, `[[Tasks|My Tasks]]`, and [[Daily Schedule]]."
  );
  assert(codeAndLinks.includes("`$\\ge \\$160\\text{k}$`"), `Inline code math example was mutated: ${codeAndLinks}`);
  assert(codeAndLinks.includes("`\\rightarrow`"), `Inline code arrow example was mutated: ${codeAndLinks}`);
  assert(codeAndLinks.includes("[Gameplan](#wikilink:Gameplan.md)"), `Backticked .md note link failed: ${codeAndLinks}`);
  assert(codeAndLinks.includes("[My Tasks](#wikilink:Tasks)"), `Backticked wikilink failed: ${codeAndLinks}`);
  assert(codeAndLinks.includes("[Daily Schedule](#wikilink:Daily%20Schedule)"), `Bare wikilink failed: ${codeAndLinks}`);

  // 7. Task-list layout regression guard (screenshots 2 & 3): `li.task-list-item` must NOT use `flex`
  const taskLiEl = MARKDOWN_COMPONENTS.li({ className: "task-list-item", children: "item" });
  const taskLiTokens = String(taskLiEl.props.className || "").split(/\s+/).filter(Boolean);
  assert(taskLiTokens.includes("list-none"), `Expected list-none on task-list-item: ${taskLiEl.props.className}`);
  assert(taskLiTokens.includes("relative"), `Expected relative on task-list-item: ${taskLiEl.props.className}`);
  assert(!taskLiTokens.includes("flex"), `task-list-item must not use flex (splits inline spans into columns): ${taskLiEl.props.className}`);

  const checkboxEl = MARKDOWN_COMPONENTS.input({ type: "checkbox", checked: true });
  const checkboxTokens = String(checkboxEl.props.className || "").split(/\s+/).filter(Boolean);
  assert(checkboxTokens.includes("absolute"), `Expected absolute gutter positioning on task checkbox: ${checkboxEl.props.className}`);

  console.log("test_markdown_math.js: all assertions passed.");
})();
