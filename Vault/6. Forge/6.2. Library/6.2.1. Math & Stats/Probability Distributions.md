---
aliases: [Probability Distributions, Gaussian, Normal Distribution]
tags: [math, statistics, generative-ai]
type: concept
---

**Back to:** [[Table of Contents]]

---

A **Probability Distribution** is a mathematical function that provides the probabilities of occurrence of different possible outcomes in an experiment. It is a fundamental concept in statistics and machine learning for modeling uncertainty and understanding data generation processes.

## Core Types

### 1. Discrete Distributions
Used when the possible outcomes are countable (e.g., rolling a die, number of emails received). The probability is given by a Probability Mass Function (PMF).

*   **Bernoulli Distribution:** A single trial with exactly two possible outcomes (success/failure, heads/tails).
    *   *AI Use Case:* Modeling binary outcomes, like predicting if a user will click an ad or not. Base for [[Logistic Regression]].
*   **Binomial Distribution:** The number of successes in a fixed number of independent Bernoulli trials.
*   **Poisson Distribution:** The probability of a given number of events occurring in a fixed interval of time or space, assuming events occur independently.

### 2. Continuous Distributions
Used when the possible outcomes can take any value within a range (e.g., height, time to failure). The probability of an exact value is zero; probabilities are calculated over intervals using a Probability Density Function (PDF).

*   **Normal (Gaussian) Distribution:** The classic "bell curve." It is symmetric and defined by its mean ($\mu$) and standard deviation ($\sigma$).
    *   *AI Use Case:* Extremely common. The Central Limit Theorem states that the sum of many independent random variables tends to follow a normal distribution. Many ML models explicitly assume normally distributed errors (like [[Linear Regression]]).
*   **Uniform Distribution:** All outcomes within bounds $a$ and $b$ are equally likely.
    *   *AI Use Case:* Neural network weight initialization often uses a uniform distribution to break symmetry.
*   **Exponential Distribution:** Models the time between events in a Poisson process.

## Importance in Generative AI

Understanding these distributions is critical for Generative AI. Models like Variational Autoencoders (VAEs) and Diffusion Models function by learning the underlying probability distribution of the training data (e.g., images) so they can sample new, highly probable data points from that learned distribution.
