---
aliases: [Multi-Agent Systems, MAS, Agent Orchestration]
tags: [ai-agents, architecture, orchestration]
type: architecture
---

**Back to:** [[Table of Contents]]

---

Multi-Agent Systems (MAS) represent the evolution from single, conversational LLMs into distributed problem-solving networks. Instead of one monolithic model trying to do everything, a multi-agent system divides complex tasks among specialized, autonomous "agents" that communicate and collaborate to achieve a goal.

## The Case for Multi-Agent Systems

When a single LLM acts as an autonomous agent (e.g., via a ReAct prompt), it rapidly encounters limitations:
*   **Context Window Pollution:** Putting the system prompt for coding, database querying, web searching, and summarizing into *one* prompt confuses the model and degrades its performance across all tasks.
*   **Tool Overload:** Giving one model 50 different tools (API connections) means it is statistically more likely to hallucinate an argument or choose the wrong tool for the job.
*   **Infinite Loops:** Single agents often get stuck in reasoning loops when they encounter an error they don't know how to fix.

By breaking tasks down into a multi-agent swarm, you can assign specialized roles, specific subsets of tools, and precise system prompts to different models, allowing for much greater reliability in production.

## Core Architectures & Roles

A typical multi-agent architecture usually involves coordination between specialized components.

### 1. The Orchestrator (The Manager)
*   **Role:** The "Boss" agent. It takes the user's initial high-level request, breaks it down into sub-tasks (a plan), and delegates those tasks to subordinate agents. 
*   **Capabilities:** It rarely has tools (like web search) itself. Its only "tool" is routing communication to other agents and synthesizing their final answers for the user.
*   **Example Prompt:** *"You are the Project Manager. Review the user's request, delegate research tasks to the 'Researcher', then send the research to the 'Writer'. Finally, present the Writer's output to the user."*

### 2. Specialized Workers
*   **Role:** The specific agents that actually execute tasks. They have very narrow system prompts and a limited set of tools.
*   *Example: The 'Researcher' Agent.* It only has the "Tavily Web Search" and "Scrape Website" tools. Its system prompt purely focuses on summarizing data neutrally.
*   *Example: The 'Coder' Agent.* It only has local file system read/write access and a bash terminal tool. It cannot search the web.

### 3. Reviewers (The Critics)
*   **Role:** Agents designed purely to critique the work of Worker agents before passing the result back to the Orchestrator. This implements "Reflexion" across multiple models.
*   *Example: Quality Assurance (QA) Agent.* *"Review the Coder's script. Does it meet PEP8 standards? Did it handle exceptions? If no, return the code to the Coder with a list of errors."*

## Popular Frameworks

Building these communication channels from scratch in Python is tedious. Several frameworks exist to orchestrate MAS:

*   **[CrewAI](https://www.crewai.com/):** One of the most popular, accessible frameworks. It uses a "Crew" metaphor where you define *Agents*, assign them *Tasks*, and organize them sequentially or hierarchically. Highly Pythonic and built on top of LangChain tools.
*   **[Microsoft AutoGen](https://microsoft.github.io/autogen/):** A powerful framework focused entirely on conversational agents. It excels at setting up chat rooms where multiple models debate or collaborate (e.g., a simulated chat between a user, an AI programmer, and an AI code reviewer).
*   **[LangGraph](https://langchain-ai.github.io/langgraph/):** A lower-level, highly controllable framework by the LangChain team that treats multi-agent systems as stateful, cyclic graphs. Best for complex, non-linear workflows with strict Human-in-the-Loop requirements.
*   **OpenAI Swarm:** A lightweight, experimental, stateless framework from OpenAI that focuses purely on defining "Routines" and "Handoffs" between agents.

## Design Patterns

*   **Sequential / Waterfall:** Agent A finishes its task completely, then passes the output to Agent B. (E.g., Researcher -> Writer -> Editor).
*   **Hierarchical:** The Orchestrator acts like a router, dynamically sending tasks to workers based on the evolving state of the conversation.
*   **Debate/Consensus:** Multiple agents with different system prompts are given the same problem and must converse until they reach a consensus (often used for high-stakes reasoning or evaluation).

## Further Resources
*   [CrewAI Documentation](https://docs.crewai.com/)
*   [The Landscape of Agentic AI (Sequoia Capital)](https://www.sequoiacap.com/article/ai-agents/)
