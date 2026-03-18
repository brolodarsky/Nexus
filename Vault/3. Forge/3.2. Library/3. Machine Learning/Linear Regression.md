---
aliases: [Linear Regression, OLS, Ordinary Least Squares]
tags: [machine-learning, algorithm, regression]
type: algorithm
---

---
**Back to:** [[Table of Contents]]
---

Linear Regression is arguably the simplest and most widely used algorithm in all of [[Supervised Learning]]. It attempts to model the relationship between a dependent continuous variable and one or more independent variables by fitting a straight line (or an $n$-dimensional plane) to the observed data.

## Core Concepts

*   **The Goal:** Predict a continuous numerical value (e.g., predicting salary based on years of experience).
*   **The Line of Best Fit:** The algorithm's objective is to find the specific straight line that best goes through the middle of the scatterplot of the data points.
*   **The Equation:**
    For **Simple Linear Regression** (one input feature): 
    $y = mx + b$ (or $y = \beta_0 + \beta_1x$)
    *   $y$: The predicted value (dependent variable).
    *   $x$: The input feature (independent variable).
    *   $m$ (or $\beta_1$): The slope or "weight" of the feature.
    *   $b$ (or $\beta_0$): The y-intercept or "bias".

    For **Multiple Linear Regression** (many input features):
    $y = \beta_0 + \beta_1x_1 + \beta_2x_2 + \dots + \beta_nx_n$

## How the Model Learns

1.  **Initialization:** The model starts with random guesses for the weights ($\beta$) and bias ($\beta_0$).
2.  **Cost Function (MSE):** The model calculates how wrong its current line is by using a cost function, typically **Mean Squared Error (MSE)**. The MSE calculates the distance between the actual data points and the predicted line, squares them (so negative distances don't cancel out positive ones), and averages them.
3.  **Optimization (Gradient Descent):** To find the "Best Fit," the model must minimize the MSE. Using [[Calculus Overview]], specifically the derivative of the cost function with respect to the weights, the **Gradient Descent** algorithm takes small steps to update the weights in the direction that lowers the error.
4.  **Convergence:** The weights are continuously updated until the MSE reaches its lowest possible point (the global minimum).

## Assumptions of Linear Regression

Linear regression will only produce valid, reliable results if the underlying data adheres to several strict statistical assumptions:

*   **Linearity:** The relationship between $X$ and $Y$ must actually be linear. (If the data is a parabola, fitting a straight line is useless).
*   **Independence:** The observations must be independent of one another.
*   **Homoscedasticity:** The variance of the error terms (residuals) should be consistent across all values of the independent variables. (A cone-shaped scatterplot violates this).
*   **Normality of Residuals:** The errors between the predictions and actuals should follow a Normal distribution (see [[Probability Distributions]]).

## Python Implementation

Linear Regression is incredibly simple to implement in Python using Scikit-Learn.

```python
from sklearn.linear_model import LinearRegression
import numpy as np

# X must be a 2D array, y is 1D
X = np.array([[10], [20], [30], [40]]) # e.g., square footage
y = np.array([100, 200, 300, 400])     # e.g., house price

model = LinearRegression()
model.fit(X, y)

print(f"Weight (Slope): {model.coef_}")
print(f"Bias (Intercept): {model.intercept_}")

# Predict the price of a 50 sq ft house
prediction = model.predict([[50]])
```

## Further Resources
*   [StatQuest: Linear Regression Explained](https://www.youtube.com/watch?v=nk2CQITm_eo)
