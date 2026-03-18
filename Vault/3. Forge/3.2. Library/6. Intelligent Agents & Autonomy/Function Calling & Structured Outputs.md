---
aliases: [Function Calling, Structured Outputs, Tool Use]
tags: [ai-agents, llms, api]
type: concept
---

---
**Back to:** [[Table of Contents]]
---

Function calling (or Tool Use) is the mechanism that allows Large Language Models (LLMs) to connect to external tools, APIs, and databases. Instead of just returning text, the model returns a structured JSON object that matches a predefined schema, which your code then uses to execute a classical programming function.

## Core Concepts

*   **The Problem:** LLMs natively only generate text. To have an agent "do" something (like create a file, query a database, or search the web), it needs a way to bridge natural language with deterministic code.
*   **The Solution:** You provide the LLM with a list of "Tools" (function definitions). The LLM decides *if* a tool should be used based on the user's prompt, and if so, what arguments to pass to it.
*   **Structured Outputs:** When the LLM decides to use a tool, it is forced to reply in a strict JSON format (Structured Output) that exactly matches the parameters you defined.

## How It Works (The Lifecycle)

1.  **Definition:** The developer defines a function in their codebase (e.g., `get_weather(location: string)`).
2.  **Schema Generation:** The function is converted into a JSON Schema that describes its purpose and parameters.
3.  **Prompting:** The user asks a question: *"What's the weather in Seattle?"* The system prompt includes both the user's question AND the JSON Schema of available tools.
4.  **Model Decision:** The LLM recognizes it cannot answer the question on its own, but sees `get_weather` in its tool list.
5.  **Output:** The LLM outputs a JSON string: `{"name": "get_weather", "arguments": {"location": "Seattle, WA"}}`.
6.  **Execution (Local):** Your local code intercepts this JSON, executes the actual `get_weather` Python function, and gets the result (e.g., `72F`).
7.  **Final Synthesis:** Your code passes the result (`72F`) back to the LLM, which then generates the final natural language response: *"It is currently 72 degrees in Seattle."*

## Best Practices for Agent Tools

*   **Descriptive Naming:** The function name and description must be extremely clear. The LLM relies almost entirely on the `description` string to know when to use the tool.
*   **Simplicity:** Tools should do one specific thing. Instead of `manage_database(action, table, query)`, use `read_from_users_table(user_id)` and `write_to_users_table(data)`.
*   **Error Handling:** If a tool fails (e.g., a 404 API error), the local code should catch the error and pass the error message back to the LLM so the LLM can try an alternative approach or inform the user.

## Frameworks and Implementations

*   **OpenAI API:** Native support via the `tools` parameter in Chat Completions.
*   **Pydantic:** Often used in Python to guarantee that the JSON returned by the LLM strictly conforms to the expected data types.
*   [[Concept - Model Context Protocol (MCP)]]: An emerging standard for defining these tools uniformly across different model providers.

## Further Resources
*   [OpenAI Guide: Function Calling](https://platform.openai.com/docs/guides/function-calling)
*   [Anthropic Tool Use Documentation](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)
