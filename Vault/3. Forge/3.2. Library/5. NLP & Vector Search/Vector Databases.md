---
aliases: [Vector Databases, Vector Embeddings, Similarity Search]
tags: [nlp, databases, infrastructure]
type: tool
---

---
**Back to:** [[Table of Contents]]
---

# Vector Databases & Embeddings

Vector Databases are specialized databases designed to store, manage, and search large datasets of high-dimensional vectors. They are the foundational infrastructure layer for modern AI applications, enabling semantic search and [[Retrieval Augmented Generation (RAG)]].

## Vector Embeddings Overview

Before understanding the database, you must understand what goes inside it: a Vector Embedding.

*   **The Problem:** LLMs understand mathematics, not words. To compare the meaning of two sentences, they must be converted into a mathematical format.
*   **The Embedding Process:** An AI model (like OpenAI's `text-embedding-3-small` or Hugging Face's `BGE`) reads a chunk of text (or an image) and outputs a list of floating-point numbers.
    *   *Example Output:* `[0.05, -0.12, 0.88, ...]`
*   **High-Dimensional Space:** These vectors usually have hundreds or thousands of dimensions (e.g., 1536 dimensions). Each dimension represents a complex, abstract semantic feature of the text.
*   **Semantic Proximity:** The core rule of embeddings: **Vectors that are closer together in this high-dimensional space represent concepts that are semantically similar.** For example, the vector for "dog" will be mathematically closer to "puppy" than to "car."

## How Vector Databases Work

A traditional relational database (SQL) searches for exact keyword matches. A vector database performs **Similarity Search** based on meaning.

### The Search Process (KNN & ANN)
1.  **Ingestion:** You embed millions of documents into vectors and store them in the database alongside their original text (the metadata).
2.  **Querying:** A user runs a query (e.g., "How do I fix a leaky faucet?"). The system embeds this query into a vector.
3.  **Distance Calculation:** The database mathematically calculates the "distance" between the query vector and every other vector in the database using metrics like **Cosine Similarity** or **Euclidean Distance**.
4.  **Retrieval:** The database returns the $K$-Nearest Neighbors (KNN)—the vectors with the shortest distance to the query vector.

### Approximate Nearest Neighbor (ANN)
Computing the exact distance between a query and *every* vector in a billion-row database is computationally impossible in real-time. Vector Databases solve this using **ANN Algorithms**.
*   These algorithms trade a tiny bit of accuracy for massive speed improvements. 
*   **HNSW (Hierarchical Navigable Small World):** The most common algorithm. It builds a multi-layered graph where nearby vectors are connected, allowing the search to quickly "zoom in" on the relevant neighborhood of vectors without checking every single one.

## Metadata Filtering

A crucial feature of modern vector DBs is combining semantic search with traditional filtering.
*   *Example:* "Find documents talking about 'AI safety' (Semantic Vector Search) BUT only where `date_published > 2023` and `author = 'OpenAI'` (Metadata Filter)."
*   This hybrid approach is essential for accurate, production-grade RAG systems.

## Popular Vector Databases

*   **[Milvus](https://milvus.io/):** Highly scalable, open-source, and cloud-native. Often used for enterprise deployments handling billions of vectors.
*   **Pinecone:** A popular, fully-managed, serverless cloud vector database. Very developer-friendly.
*   **ChromaDB / Qdrant:** Popular choices for local AI development, prototyping, and smaller-scale production applications.
*   **PostgreSQL with `pgvector`:** An extension that adds vector search capabilities directly into standard Postgres, popular for teams wanting to avoid adding a new database technology to their stack.

## Further Resources

*   [What is a Vector Database? (Pinecone)](https://www.pinecone.io/learn/vector-database/)
*   [Milvus Documentation](https://milvus.io/docs)
