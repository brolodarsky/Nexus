# Educational & Granular Code Commenting Standards

> Standing instruction for all AI coding agents working across this codebase.

## User Persona & Knowledge Calibration
- **User Knowledge Level**: The user has a solid foundational understanding of core programming concepts (variables, basic functions, conditional control flow, loops, and basic data structures like arrays/lists and objects/dicts).
- **Core Need**: The user values rich, educational, step-by-step code comments that demystify intermediate-to-advanced syntax, language features, framework patterns, and asynchronous or architectural flows without requiring constant context-switching to look up documentation.

## Universal Scope & Language Agnosticism
This rule is strictly **language-agnostic** and applies across **all languages, frameworks, scripts, and queries** across this repository (e.g., Python, TypeScript, JavaScript, SQL, PowerShell/Bash, Rust, CSS, HTML). Whenever writing or editing code in any language, demystify non-trivial syntax, language idioms, and architectural constructs using the directives below.


## Mandatory Commenting Directives

### 1. Signature & Paradigm Breakdowns (Pre-block Annotations)
Whenever introducing or modifying non-trivial functions, classes, interfaces, or type definitions, include an explicit breakdown of keywords, types, and parameters immediately above or beside the block:
- **Generics & Type Parameters** (e.g., `<T>` in TypeScript or `TypeVar`/`Generic[T]` in Python): Explain what the generic placeholder represents, why it is used, and give concrete examples of types that can be passed (e.g., `// <T> is a generic type parameter, meaning this function can handle any data shape (e.g. AgentStatus, VaultEntry)`).
- **Asynchronous Primitives**: Annotate `Promise`, `async`, `await`, coroutines, tasks, and event loops (e.g., `// Promise holds the eventual result of an async operation`, `// await pauses execution until the promise settles`).
- **Types & Interfaces**: State clearly what shape of data is being modeled and where it comes from (e.g., `// Interface describing the shape of API response data returned from the backend`).
- **HTTP, Protocols & Streams**: Explain request options (`RequestInit`, headers, methods), SSE streams, `ReadableStream`, `TextDecoder`, chunk buffering, and cancellation (`AbortController`).
- **Modern Idioms & Operators**: Briefly explain non-obvious syntax (e.g., nullish coalescing `??`, optional chaining `?.`, spread operator `...`, destructuring, decorators, generators, list/dict comprehensions).

### 2. Inline Step-by-Step Logic & "Why" Annotations
- Break down multi-step logic into clear, annotated phases.
- Explain *why* specific intermediate steps or buffers exist (e.g., `// Keep the last incomplete chunk in the buffer so it gets completed on the next stream read`).
- Annotate error handling and guards (e.g., `// Catch and ignore malformed JSON chunks so a single bad packet does not crash the active stream`).

### 3. Tone, Space Efficiency & Craft
- **High Information Density (Minimal Space Footprint)**: Keep comments compact, punchy, and space-efficient. Prefer single-line annotations per concept over multi-line rambling paragraphs.
- **Zero Fluff or Decorative Bloat**: Avoid conversational preamble (e.g., "Now we are going to..."), oversized ASCII banners, or unnecessary empty comment lines. Jump straight to the core definition, mechanism, and example.
- **Pedagogical & Approachable**: Write plain-English, high-signal explanations that demystify the mechanism in minimal characters.
- **Preservation Directive**: NEVER delete, truncate, or simplify existing educational comments during refactors or edits. When updating code, expand comments to match this high-detail standard.

