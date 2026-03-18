---
aliases: [Linear Algebra, Vectors, Matrices]
tags: [math, machine-learning, embeddings]
type: overview
---

---
**Back to:** [[Table of Contents]]
---

[[Linear Algebra]] is a branch of mathematics concerning **vector spaces** and **linear mappings** between such spaces. It is a fundamental tool for AI and Machine Learning, allowing for the modeling and solving of systems of linear equations.

## Key Concepts

### Vectors
*   **Definition**: A **vector** is an object with both **magnitude** and **direction**. Represented as an array of numbers (components).
*   **AI Applications**:
    *   Representing data points as feature vectors.
    *   [[Vector Embeddings]] in NLP.

### Matrices
*   **Definition**: A rectangular array of numbers arranged in rows and columns ($m \times n$).
*   **AI Applications**:
    *   Representing and solving systems of linear equations.
    *   Storing and transforming image pixels in Computer Vision.
    *   Weights in Neural Networks.

### Determinants
*   **Definition**: A scalar value computed from the elements of a square matrix. A non-zero determinant means the matrix is **invertible**.
*   **Applications**: Important for understanding the properties of transformations (whether they collapse space).

### Eigenvalues and Eigenvectors
*   **Definition**: For a square matrix $A$, an **eigenvector** $v$ satisfies $Av = \lambda v$, where $\lambda$ is the **eigenvalue**.
*   **AI Applications**:
    *   Principal Component Analysis (PCA) for dimensionality reduction.

## Essential Formulas

*   **Dot Product**: $u \cdot v = u_1v_1 + u_2v_2 + ... + u_nv_n$. Extremely important for calculating cosine similarity in [[Vector Databases]].
*   **Matrix Multiplication**: $C_{ij} = \sum_{k=1}^{n} A_{ik} B_{kj}$. The core operation underlying all deep learning models.

## Resources
*   [Essence of Linear Algebra (3Blue1Brown)](https://www.youtube.com/playlist?list=PLZHQObOWTQDPD3MizzM2xVFitgF8hE_ab)
*   [Khan Academy Linear Algebra](https://www.khanacademy.org/math/linear-algebra)
