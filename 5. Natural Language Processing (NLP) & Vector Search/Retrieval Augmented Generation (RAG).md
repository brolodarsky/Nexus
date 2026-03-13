---
aliases: [RAG, Retrieval Augmented Generation, Semantic Search]
tags: [nlp, generative-ai, llms, vector-database]
type: architecture
---
# Retrieval Augmented Generation (RAG)

Retrieval Augmented Generation (RAG) is a technique for enhancing Large Language Models by fetching relevant external data and inserting it into the model's context window before generating a response. It grounds the LLM in specific, up-to-date, or proprietary data that was not present in its original training corpus.

## The Core Concept

LLMs are frozen in time based on their training data. When asked about recent events or private company data, they will hallucinate or fail.
*   **The Problem:** Fine-tuning an entire model on new data is expensive, slow, and doesn't solve the problem of real-time updates or dynamic access control.
*   **The Solution:** Instead of *training* the model to memorize the data, *provide* the data to the model explicitly right before it answers the user's question.

## The Standard RAG Pipeline

A typical RAG pipeline involves three main steps, commonly referred to as "Ingestion," "Retrieval," and "Generation."

### 1. Ingestion (Data Processing)
*   **Parsing:** Extracting text from PDFs, Notion docs, codebases, or websites.
*   **Chunking:** Breaking long documents down into smaller, semantically meaningful pieces (chunks, e.g., 500-1000 tokens). If chunks are too large, the specific information gets lost; if too small, context is lost.
*   **Embedding:** Converting each chunk of text into a [[Vector Embeddings|mathematical vector]] (a list of numbers) that represents its semantic meaning.
*   **Vector Database:** Soring these embeddings (and the original text) in a specialized database like [[Milvus]] or Pinecone for fast similarity search.

### 2. Retrieval 
*   **Query Embedding:** When a user asks a question, their query is converted into a vector using the *exact same embedding model* used during ingestion.
*   **Vector Search:** The system quickly searches the Vector Database for the chunks whose vectors are mathematically closest (most similar) to the query vector.
*   **Context Assembly:** The top `K` most relevant chunks are retrieved.

### 3. Generation
*   **The Prompt:** The retrieved chunks are injected into the context window alongside the user's original question and the system prompt.
    *   *Example Prompt:* "Answer the user's question using ONLY the following context. If the answer is not in the context, say 'I don't know'.\n\nContext:\n[Chunk 1]\n[Chunk 2]\n\nQuestion: [User's Question]"
*   **Response Synthesis:** The LLM reads the context and generates an informed, factual response.

## Advanced RAG Techniques

Basic RAG (Naïve RAG) often fails on complex queries. Advanced techniques include:

*   **Query Transformations (Routing/Rewriting):** Using an LLM to rewrite the user's query to optimize it for vector search (e.g., expanding abbreviations or writing multiple sub-queries).
*   **Semantic Router:** Deciding *which* database or RAG pipeline to use based on the intent of the query.
*   **Re-ranking (Cross-Encoders):** Filtering down a large list of retrieved chunks using a slower, more accurate model (like Cohere Rerank) to ensure only the absolute best context reaches the final LLM pass.
*   **Graph RAG:** Combining traditional vector search with Knowledge Graphs to retrieve information based on relational connections rather than just semantic similarity.

## Popular Tools & Frameworks
*   **[LlamaIndex](https://www.llamaindex.ai/):** The industry standard orchestration framework designed specifically for advanced RAG architectures.
*   **[LangChain](https://python.langchain.com/):** A more general-purpose LLM orchestration framework that includes RAG components.
*   **Embedding Models:** OpenAI (`text-embedding-3-small`), BGE, Cohere.


---
**Back to:** [[Table of Contents]]
