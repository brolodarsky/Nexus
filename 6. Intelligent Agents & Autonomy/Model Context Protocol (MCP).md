---
aliases: [MCP, Model Context Protocol]
tags: [ai-agents, architecture, standards, api]
type: tool
---
# Model Context Protocol (MCP)

The Model Context Protocol (MCP) is an emerging open standard, originally developed by Anthropic, that acts as a universal bridge between Large Language Models (LLMs) and external data sources or tools. It standardizes how AI models securely request, discover, and utilize APIs, databases, and local file systems.

## The Problem MCP Solves

Before MCP, giving an LLM access to external tools (like a local database, a GitHub repo, or a web search API) was a fragmented, brittle process.
*   **The M N Problem:** If there are $M$ different AI frameworks (LangChain, LlamaIndex, OpenAI, Claude Desktop) and $N$ different tools (Slack, Jira, Postgres, GitHub), developers theoretically have to write $M \times N$ different custom integrations.
*   **Lack of Standardization:** Every platform had a slightly different way of defining JSON schemas for [[Function Calling & Structured Outputs]].
*   **Security & Sandbox Issues:** Directly giving an LLM bash access or raw API keys in a python script is extremely risky.

MCP solves this by defining an open standard interface. 
*   If a tool provider (e.g., GitHub, Slack) writes an **MCP Server**, *any* MCP-compatible AI application can instantly connect to those tools securely without bespoke integration.

## How MCP Works: The Client-Server Model

MCP relies on a strict Client-Server architecture. The LLM itself does not speak MCP; the application hosting the LLM speaks MCP.

### 1. MCP Hosts (Clients)
The application running the AI model.
*   *Examples:* Claude Desktop, Cursor, Zed, Sourcegraph Cody, Antigravity.
*   The Host is responsible for managing the connection, deciding when to prompt the LLM, and handling the user interface.

### 2. MCP Clients
The protocol layer *inside* the Host application that maintains a 1:1 connection with a specific MCP server and handles the two-way communication.

### 3. MCP Servers
A lightweight, standalone application that exposes a specific set of capabilities.
*   *Examples:* A `postgres-mcp-server` that exposes read-only SQL queries. A `github-mcp-server` that exposes commands to read PRs and create issues. A `brave-search-mcp` that exposes web search.
*   An MCP Server never knows *why* an LLM is calling it; it simply executes the command it is given and returns the result.

## The Three Primitives of MCP

An MCP Server can expose any combination of three primary capabilities to the Host:

1.  **Resources (URI):** 
    Similar to a GET request in a REST API. It exposes data that the LLM can read but not change.
    *   *Example:* A `file:///` URI to read a local document, or a `db://` URI to read a Postgres table schema. The Host can fetch this data to give the LLM context *before* a conversation even starts.
2.  **Tools (Functions):** 
    Similar to a POST request. These are executable functions that allow the LLM to take action.
    *   *Example:* `execute_sql_query`, `create_github_issue`, `search_tavily`. The server provides the JSON schema describing what arguments are required. The Host handles the [[Function Calling]] loop with the LLM, and the Server executes the actual code.
3.  **Prompts (Templates):**
    Pre-defined prompt templates that users can trigger via the UI. These are parameterized instructions that optionally inject data from resources.
    *   *Example:* A "Debug Local File" prompt that takes a file path as an argument, fetches the file resource, and feeds both the file and a "Please find the bug" instruction to the LLM.

## Why MCP is Crucial for Agents

*   **Security via Isolation:** The LLM and the Host never see the API keys used by the MCP server. If an LLM is compromised via prompt injection, it can only call the specific, scoped tools the MCP server allows (e.g., granting a `postgres-mcp-server` only READ permissions).
*   **Rapid Ecosystem Growth:** Instead of writing an integration for Cursor, and another for LangChain, and another for Claude Desktop, a developer can write one MCP Server and immediately access the entire ecosystem.
*   **Local-First Design:** MCP servers often run locally on the user's machine, allowing cloud-based LLMs to interact with secure local data (like codebases or proprietary databases) without uploading the entire database to the cloud provider.

## Further Resources
*   [Model Context Protocol Official Site](https://modelcontextprotocol.io/)
*   [Introduction to MCP (Anthropic)](https://www.anthropic.com/news/model-context-protocol)


---
**Back to:** [[Table of Contents]]
