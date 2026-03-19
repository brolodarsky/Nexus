---
aliases: [NumPy, ndarray, Numerical Python]
tags: [python, library, data-science, math]
type: tool
---

**Back to:** [[Table of Contents]]

---

**Numerical Python (NumPy)** is the foundational library for scientific computing in Python. It provides high-performance multidimensional array objects and tools for working with these arrays. Almost all other data science libraries (like [[Pandas]], Scikit-learn, and PyTorch) are built on top of or integrate closely with NumPy.

## Core Concepts

### 1. The `ndarray`
*   The core of NumPy is the $N$-dimensional array object (`ndarray`). Unlike Python's standard `list` (which can contain mixed data types), an `ndarray` is a homogeneous grid of values, all of the *same type*, indexed by a tuple of non-negative integers.
*   **Dimensions (Axes):** In a 2D array (matrix), axis 0 runs downwards along the rows, and axis 1 runs horizontally across the columns.

### 2. Vectorization
*   NumPy heavily utilizes **vectorization**, which means operations are applied to entire arrays rather than iterating through elements one by one using a `for` loop.
*   This push operations down into highly optimized C code under the hood, making array operations orders of magnitude faster than standard Python loops.

### 3. Broadcasting
*   A powerful mechanism that allows NumPy to perform arithmetic operations on arrays of different shapes. NumPy "broadcasts" the smaller array across the larger array so that they have compatible shapes for the operation, without actually creating massive, memory-hogging copies of the data.

## Why NumPy is Essential for AI

*   **Matrix Multiplication:** The fundamental operation in Neural Networks (computing the dot product of inputs and weights) is handled incredibly efficiently by NumPy arrays.
*   **Data Representation:** Images, sounds, and text (via [[Vector Embeddings]]) can all be represented as N-dimensional arrays of numbers.
*   **Memory Efficiency:** Deep learning requires gigabytes of active memory. `ndarrays` are vastly more memory-efficient than standard Python lists.

## Common Operations

*   `np.array([1, 2, 3])`: Create an array from a list.
*   `np.zeros((3, 4))` / `np.ones((2, 2))`: Initialization.
*   `np.reshape()`: Changing the dimensions of an array without changing its data (e.g., converting a 1D vector of length 9 into a 3x3 matrix).
*   `np.dot(A, B)` / `A @ B`: Matrix multiplication.

## Resources
*   [NumPy Official Documentation](https://numpy.org/doc/stable/user/whatisnumpy.html)
