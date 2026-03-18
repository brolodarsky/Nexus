---
aliases: [Supervised Learning, Predictive Modeling]
tags: [machine-learning, concepts]
type: overview
---

**Back to:** [[Table of Contents]]

---

Supervised learning is a subfield of machine learning where an algorithm learns from a labeled dataset. The model observes pairs of input data (features) and corresponding correct outputs (labels), and learns the mathematical mapping between them. 

## The Core Concept

*   **The Teacher Analogy:** The algorithm learns by observing a dataset with known answers, much like a student learns with the help of a teacher providing the correct solutions.
*   **The Goal (Generalization):** Provide the algorithm with enough high-quality, labeled examples so that it can accurately predict the label for *new, unseen data*.
*   *(Contrast with Unsupervised Learning: Learning from unlabeled data to find hidden categories or patterns, like customer segmentation via K-Means clustering).*

## Key Terminology

*   **Features ($X$):** The input variables. Also known as independent variables or predictors. (e.g., Square footage of a house, number of bedrooms).
*   **Labels ($Y$):** The correct output answers. Also known as dependent variables or targets. (e.g., The actual sale price of the house).
*   **Model:** The mathematical representation that learns the relationship.
*   **Training/Inference:** "Training" is the process of adjusting the model's parameters to fit the labeled data. "Inference" is using the trained model to make predictions on new data.

## The Two Main Types of Supervised Learning

### 1. Regression
*   **Definition:** Predicting a **continuous** numerical output variable.
*   *Example:* Predicting stock prices, temperature, or the sale price of a home.
*   **Common Algorithms:** 
    *   [[Linear Regression]]
    *   Polynomial Regression
    *   Support Vector Regression (SVR)
    *   Random Forest Regressor
*   **Evaluation Metrics:** Mean Squared Error (MSE), Root Mean Squared Error (RMSE), Mean Absolute Error (MAE), $R^2$ Score.

### 2. Classification
*   **Definition:** Predicting a **discrete** categorical output variable (class labels).
*   *Example:* Identifying whether an email is "Spam" or "Not Spam" (Binary). Identifying an image as a "Cat", "Dog", or "Car" (Multi-class).
*   **Common Algorithms:**
    *   [[Logistic Regression]]
    *   Support Vector Machines (SVM)
    *   K-Nearest Neighbors (KNN Classifier)
    *   Decision Trees & Random Forest Classifier
*   **Evaluation Metrics:** Accuracy, Precision, Recall, F1-Score, ROC/AUC Curves.

## The Supervised Learning Workflow

1.  **Data Collection & Labeling:** The most expensive step; gathering data and having humans or systems apply consistent labels.
2.  **Data Preprocessing:** Cleaning missing values, standardizing numerical [[NumPy]] arrays, and encoding categorical variables.
3.  **Data Splitting:** Dividing the dataset into:
    *   **Training Set:** (e.g., 80%) Used to train the model properties.
    *   **Validation Set:** (e.g., 10%) Used for hyperparameter tuning to prevent overfitting.
    *   **Test Set:** (e.g., 10%) Hidden entirely until final deployment to evaluate real-world generalization.
4.  **Model Selection & Training:** Choosing the appropriate algorithm and letting it learn from the Training Set using an optimizer like Gradient Descent.
5.  **Evaluation:** Measuring the performance against the Validation/Test sets.
6.  **Deployment:** Using the model in production.

## Key Challenges

*   **Overfitting (High Variance):** Learning the specific noise in the training data rather than the underlying pattern. The model performs perfectly on the training set but fails spectacularly on new data.
*   **Underfitting (High Bias):** An overly simple model that cannot capture the complexity of the data at all. Performed poorly on both training and test sets.
*   **Data Imbalance:** Having 99% "Not Spam" and 1% "Spam" labels. This will trick a naive model into trivially predicting "Not Spam" every time and achieving 99% accuracy while failing its true purpose entirely.

## Further Resources

*   [Machine Learning Glossary (Google)](https://developers.google.com/machine-learning/glossary)
