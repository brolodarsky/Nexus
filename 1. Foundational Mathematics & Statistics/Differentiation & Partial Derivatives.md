---
aliases: [Differentiation, Partial Derivatives, Gradients]
tags: [math, optimization, deep-learning]
type: concept
---
# Differentiation & Partial Derivatives

Differentiation is the mathematical procedure used to find a derivative—the rate of change of a function. The derivative of a function $f(x)$ with respect to $x$ is denoted as $f'(x)$ or $\frac{df}{dx}$.

## Core Concepts

*   **The Slope:** The derivative tells you the slope of the function at any given point. If a function models the "cost" or "error" of an AI model, you want to find the point where the slope is zero (the minimum cost).
*   **The Chain Rule:** Arguably the most important rule in calculus for AI. It states how to compute the derivative of a composite function (a function of a function). If $y$ depends on $u$, and $u$ depends on $x$, then $\frac{dy}{dx} = \frac{dy}{du} \cdot \frac{du}{dx}$. This is the exact mechanism of **Backpropagation** in Neural Networks.

## Partial Derivatives

In Machine Learning, cost functions (like MSE in [[Linear Regression]]) are rarely functions of just one variable. Neural networks have millions of variables (weights and biases).

*   **Definition:** A partial derivative is a derivative of a function of *multiple* variables with respect to *one* of those variables, while holding the other variables constant.
*   **Notation:** It is denoted with the symbol $\partial$. The partial derivative of $f(x, y)$ with respect to $x$ is $\frac{\partial f}{\partial x}$.

### The Gradient
While a partial derivative gives the rate of change with respect to one variable, the **Gradient** ($\nabla$) is a vector that groups all the partial derivatives together. 
*   If $f(x, y, z)$ is a cost function, its gradient is the vector: $\nabla f = \left[ \frac{\partial f}{\partial x}, \frac{\partial f}{\partial y}, \frac{\partial f}{\partial z} \right]$.
*   **Geometric Meaning:** The gradient vector at any point points in the direction of the *greatest rate of increase* of the function.
*   **Gradient Descent:** To optimize an ML model, we calculate the gradient of the cost function, and then take a step in the *opposite* direction (the direction of steepest descent) to minimize the error.

---
**Back to:** [[Table of Contents]]
