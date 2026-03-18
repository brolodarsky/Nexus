---
aliases: [Calculus, Integration, Derivatives]
tags: [math, optimization, machine-learning]
type: overview
---

---
**Back to:** [[Table of Contents]]
---

Calculus is the mathematical study of continuous change. In the context of AI and Machine Learning, calculus is the engine that allows models to "learn" by iteratively minimizing error. 

## The Two Branches

### 1. Differential Calculus (Differentiation)
This branch concerns the rate of change of a quantity. 
*   **The Derivative:** Represents the instantaneous rate of change of a function. In geometric terms, it is the slope of the tangent line to the curve at a point.
*   **AI Application:** Optimization. If we have a cost function (which measures how "wrong" a model is), the derivative tells us *which direction* and *how fast* to change the model's parameters to reduce the error. This is the core of [[Differentiation & Partial Derivatives]] and Gradient Descent.

### 2. Integral Calculus (Integration)
This branch concerns the accumulation of quantities and the areas under curves.
*   **The Integral:** Represents the area under the curve of a function.
*   **AI Application:** Probability. Calculating probabilities from Continuous [[Probability Distributions]] involves taking the integral of the Probability Density Function (PDF) over a given interval. Also used in computing expectations.

## Calculus in Neural Networks

The learning process in Deep Learning relies entirely on calculus, specifically building a computational graph and applying the **Chain Rule**. 

*   **Forward Pass:** Data moves through the network, and the loss (error) is calculated.
*   **Backpropagation:** The algorithm calculates the partial derivative of the overall loss with respect to every single weight in the network. It uses the chain rule to recursively compute these gradients from the output layer back to the input layer.

## Resources
*   [Essence of Calculus (3Blue1Brown)](https://www.youtube.com/playlist?list=PLZHQObOWTQDMsr9K-rj53DwVRMYO3t5Yr)
