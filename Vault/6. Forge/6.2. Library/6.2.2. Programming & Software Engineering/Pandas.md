---
aliases: [Pandas, DataFrame, Data Analysis]
tags: [python, library, data-science, feature-engineering]
type: tool
---

**Back to:** [[Table of Contents]]

---

**Pandas** is an open-source data manipulation and analysis library built on top of [[NumPy]]. While NumPy excels at crunching uniform mathematical arrays, Pandas excels at handling heterogeneous, tabular data—much like a SQL table or an Excel spreadsheet.

## Core Data Structures

### 1. The Series
*   A one-dimensional labeled array. You can think of it as a single column in a table. Unlike a standard NumPy array, a Series has an explicit `index` (labels) associated with its values.

### 2. The DataFrame
*   The primary data structure of Pandas. It is a two-dimensional, size-mutable, and potentially heterogeneous tabular data structure with labeled axes (rows and columns). It is essentially a dictionary of `Series` objects sharing the same index.

## Key Capabilities

*   **Data Ingestion:** Easy loading of data from CSV strings, Excel workbooks, SQL databases, JSON blobs, directly into a DataFrame (`pd.read_csv`, `pd.read_sql`).
*   **Data Cleaning:** Handling missing data (using methods like `.fillna()` or `.dropna()`), reshaping tables, and pivoting data.
*   **Data Exploration:** Quick summary statistics (`.describe()`), data types (`.info()`), and filtering/subsetting (`df[df['age'] > 30]`).
*   **Aggregation and Grouping:** Implementing the split-apply-combine paradigm using `.groupby()`. For example, calculating the average salary grouped by department.
*   **Joining/Merging:** Relational database-style joins (inner, outer, left, right) applied directly in memory to DataFrames.

## Pandas in the AI Workflow

Pandas is typically used in the critical *Data Processing and Feature Engineering* phase before machine learning models are trained.

1.  **Exploratory Data Analysis (EDA):** The LLM/Data Scientist uses Pandas to understand the shape, distribution, and missing values in a dataset.
2.  **Feature Engineering:** Creating new columns based on existing ones (e.g., standardizing text columns, calculating deltas, or creating dummy variables from categorical strings) before feeding the data to an algorithm like [[Linear Regression]].
3.  **Agentic Analysis:** In modern workflows, agents generate Pandas code (like in the OpenHands or GPT-4 Code Interpreter environments) to rapidly answer natural language questions about CSV datasets.

## Resources
*   [10 minutes to pandas (Official Guide)](https://pandas.pydata.org/docs/user_guide/10min.html)
