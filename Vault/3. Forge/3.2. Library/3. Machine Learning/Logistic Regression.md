---
aliases: [Logistic Regression, Sigmoid Function, Log-Loss]
tags: [machine-learning, algorithm, classification]
type: algorithm
---

---
**Back to:** [[Table of Contents]]
---

Despite its name containing the word "regression," **Logistic Regression** is almost exclusively used for **Classification** tasks in [[Supervised Learning]]. Rather than fitting a continuous straight line like [[Linear Regression]], Logistic Regression fits an "S-shaped" curve to calculate the probability that an observation belongs to a specific category.

## Core Concepts

*   **The Goal:** Predict a categorical or discrete outcome (most commonly Binary: Spam/Not Spam, Pass/Fail, Malignant/Benign).
*   **The Underlying Problem with Linear Regression for Classification:** If you use a straight line ($y = mx + b$) to predict probabilities (0 to 1), the line will eventually extend past 1 on the top and below 0 on the bottom. Probabilities cannot be negative or greater than 100%.
*   **The Solution (The Sigmoid Function):** Logistic Regression takes the output of a standard linear equation ($z = \beta_0 + \beta_1x$) and passes it through the **Sigmoid (or Logistic) Function**:

    $$ \sigma(z) = \frac{1}{1 + e^{-z}} $$

    This mathematical function takes *any* real number and squashes it into a value strictly between 0 and 1.

## Interpreting the Output

*   **Probabilities:** The output of the Sigmoid function is the probability that the given observation belongs to the positive class (Class 1).
    *   *Example:* If $\sigma(z) = 0.85$, there is an 85% probability the email is Spam.
*   **The Decision Boundary (Threshold):** To make a final "Spam" or "Not Spam" decision, we set a threshold (usually $0.5$).
    *   If $\sigma(z) \ge 0.5$, predict Class 1 (Spam).
    *   If $\sigma(z) < 0.5$, predict Class 0 (Not Spam).
    *   *Note:* The threshold can be adjusted based on the business use-case depending on whether False Positives or False Negatives are more dangerous.

## Log-Odds (Logit)

Behind the scenes, Logistic Regression models the *log-odds* of an event occurring as a linear combination of the independent variables. 
$$ \ln\left(\frac{p}{1-p}\right) = \beta_0 + \beta_1x_1 + \beta_2x_2 + \dots $$
Where $\frac{p}{1-p}$ is the Odds Ratio. This logarithmic transformation is what allows the algorithm to perform linear classification on fundamentally non-linear probability curves.

## How the Model Learns (Log-Loss)

*   Unlike Linear Regression, which minimizes Mean Squared Error (MSE), Logistic Regression minimizes a cost function called **Log-Loss** (or Binary Cross-Entropy).
*   Log-Loss heavily penalizes the model if it is highly confident in a wrong answer (e.g., predicting a 99% chance of Spam when the email was actually Not Spam).
*   Like Linear Regression, the weights are optimized using [[Calculus Overview]] and Gradient Descent.

## Implementation Details

*   **Multiclass:** While inherently binary, Logistic Regression can handle multiclass classification (e.g., sorting images into Cat / Dog / Bird) using the **One-vs-Rest (OvR)** or **Softmax** approach.
*   **Python:** Extensively implemented in Scikit-Learn via `from sklearn.linear_model import LogisticRegression`.

## Further Resources

*   [StatQuest: Logistic Regression Explained](https://www.youtube.com/watch?v=yIYKR4sgzI8)
