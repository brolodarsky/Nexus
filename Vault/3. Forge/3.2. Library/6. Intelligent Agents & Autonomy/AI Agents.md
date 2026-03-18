---
aliases: [AI Agents, Agentic Workflows, Autonomous Agents]
tags: [ai-agents, llms, architecture]
type: concept
---

---
**Back to:** [[Table of Contents]]
---

An **AI Agent** is a system powered by a Large Language Model (LLM) that can autonomously reason through a problem, create a plan, and execute actions using external tools to achieve a predefined goal. Unlike standard conversational AI (chatbots), agents are proactive and capable of altering their environment.

## The Evolution of LLMs

1.  **Standard LLM (e.g., ChatGPT web interface):** You ask a question, the model generates text, the interaction ends.
2.  **RAG System:** The LLM searches a [[Vector Databases|Vector Database]] for documents *before* answering. It is "data-aware" but still reactive.
3.  **Agentic Workflow:** The LLM is given an objective ("Research X, save the summary as a PDF, and email it to Y"). The LLM decides *how* to achieve this, looping through thought processes, API calls, and self-correction until the goal is met.

## The Core Components of an Agent

According to the famous [Reason + Act (ReAct) paper](https://arxiv.org/abs/2210.03629), an agent consists of three main mechanisms loop:

1.  **Thought:** The internal reasoning step. The LLM analyzes the user's prompt or the current state of its environment and decides what to do next. (e.g., *"The user wants to know the weather in Tokyo. I need to use the weather API tool."*)
2.  **Act:** The LLM outputs a structured command, usually via [[Function Calling & Structured Outputs]]. The host environment intercepts this JSON, executes the local code (e.g., hitting the `OpenWeatherMap API`), and captures the result.
3.  **Observe:** The result of the API call is fed back into the LLM's context window. (e.g., *"{temp: 72F}"*).
4.  *(The LLM returns to step 1 to decide if the goal is met or if another tool is needed).*

## Agent Architectures

Beyond basic ReAct loops, complex agents use advanced cognitive architectures.

*   **Plan-and-Solve:** The agent first outputs an explicit, multi-step plan before taking *any* action. Once the plan is finalized, it executes the steps sequentially.
*   **Reflexion:** The agent acts, observes the result, and then explicitly generates a critique of its own performance (*"I failed to find the file because I searched the wrong directory"*). It then updates its internal context and tries again.
*   [[Multi-Agent Systems & Orchestration]]: The most advanced paradigm, where a "Manager" agent delegates discrete tasks to narrowly scoped "Worker" agents (e.g., a Coder, a Reviewer, and a Tester).

## Agent Tools ("Hands")

Agents interact with the world via defined tools.
*   **Web Browsing:** Using tools like Playwright or Puppeteer to navigate the DOM, click buttons, and scrape text.
*   **Bash / CLI Execution:** Running Python scripts, managing files, and compiling code.
*   **APIs:** Connecting to Slack, GitHub, Jira, or proprietary databases. 
    *   *Note:* The emerging standard for organizing these tools universally is the [[Concept - Model Context Protocol (MCP)]].

## Further Resources
*   [IBM: AI Agents Explained](https://www.ibm.com/think/ai-agents)
*   [Sequoia Capital: AI Agents Landscape](https://www.sequoiacap.com/article/ai-agents/)
