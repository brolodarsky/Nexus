---
aliases: [Python, Python 3, Py]
tags: [programming-language, software-engineering, ai-stack]
type: overview
---
# Python

Python is the dominant programming language for Artificial Intelligence, Data Science, and Agentic Workflows. Its rich ecosystem of libraries, readable syntax, and extensive community support make it the standard for building complex software systems interacting with LLMs.

## Core Concepts for AI & Agents

*   **Dynamic Typing:** Variables do not need explicit type declarations, though modern Python heavily uses Type Hinting (e.g., `def calculate(value: int) -> float:`) which is crucial for building robust Agent schemas like with Pydantic.
*   **Object-Oriented Programming (OOP):** Grouping related data and functions into classes. Essential for defining tools and modeling Agent states.
*   **Asynchronous Programming (`async`/`await`):** Crucial for concurrent operations. When an AI agent makes 10 independent API calls across the web, doing it synchronously blocks all other tasks. `asyncio` allows these to run concurrently, drastically speeding up agent workflows.

## Key Virtual Environments & Package Managers
*   `pip`: The default package installer.
*   `venv`: Standard library tool for creating isolated environments.
*   **Poetry** / **uv**: Modern, extremely fast dependence resolution and environment management tools (highly recommended for production ML projects over `pip/requirements.txt`).

## Essential Libraries for AI/ML

### 1. The Core Scientific Stack
*   **[[NumPy]]:** The fundamental package for numerical computation in Python. Provides support for large, multi-dimensional arrays and matrices.
*   **[[Pandas]]:** Data structures and data analysis tools, primarily the `DataFrame`.
*   **Scikit-learn:** Simple and efficient tools for predictive data analysis (e.g., [[Supervised Learning]], SVMs, Random Forests).

### 2. Deep Learning Frameworks
*   **PyTorch:** The industry standard for deep learning research and modern architecture implementations (developed by Meta).
*   **TensorFlow:** (Developed by Google), widely used in enterprise deployments but less popular in modern AI research than PyTorch.

### 3. Agent Frameworks & APIs
*   **LangChain / LlamaIndex:** Orchestration frameworks for connecting LLMs to other sources of data and computation.
*   **Pydantic:** Data validation library. This is the absolute core of [[Function Calling & Structured Outputs]] in modern LLM API interactions.
*   **requests / aiohttp / httpx:** Libraries for making HTTP requests (interacting with external APIs).

## Further Resources

*   [Real Python](https://realpython.com/)
*   [Automate the Boring Stuff with Python](https://automatetheboringstuff.com/)

---
**Back to:** [[Table of Contents]]
