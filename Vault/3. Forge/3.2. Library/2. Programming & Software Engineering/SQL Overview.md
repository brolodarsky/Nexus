---
aliases: [SQL, Structured Query Language, Relational Databases]
tags: [data-engineering, databases, programming-language]
type: overview
---

---
**Back to:** [[Table of Contents]]
---

# SQL (Structured Query Language)

**SQL** is the standard domain-specific language used for managing, querying, and updating structured tabular data from a Relational Database Management System (RDBMS). Even in the era of Big Data and NoSQL, SQL remains the absolute bedrock of data engineering.

## Core Concepts & RDBMS Principles

*   **Relational Database:** Stores data in tables consisting of columns (attributes) and rows (records). Tables can be related to one another through primary and foreign keys.
*   **Primary Key:** A column (or set of columns) that uniquely identifies each row in a table.
*   **Foreign Key:** A column in one table that refers to the primary key in another table, establishing a link between the data.
*   **ACID Properties:** The principles ensuring reliable database transactions: 
    *   **A**tomicity (all or nothing)
    *   **C**onsistency (valid states only)
    *   **I**solation (concurrent transactions don't interfere)
    *   **D**urability (saved history).

## Key SQL Commands (CRUD)

SQL commands are generally divided into DDL (Data Definition Language) for defining schemas and DML (Data Manipulation Language) for querying data. The core operations map to CRUD:

*   **Create:** `INSERT INTO table_name (column1) VALUES (value1);`
*   **Read:** The core of data analysis.
    *   `SELECT column1, column2 FROM table_name WHERE condition;`
*   **Update:** `UPDATE table_name SET column1 = value1 WHERE condition;`
*   **Delete:** `DELETE FROM table_name WHERE condition;`

## Advanced Querying

*   **Aggregations & Grouping:** Using functions like `COUNT()`, `SUM()`, `AVG()` combined with the `GROUP BY` clause. (e.g., Finding the average order value per customer ID).
*   **Joins:** Combining rows from two or more tables based on a related column.
    *   `INNER JOIN`: Returns records that have matching values in both tables.
    *   `LEFT (OUTER) JOIN`: Returns all records from the left table, and the matched records from the right table.
*   **CTEs (Common Table Expressions):** Using the `WITH` clause to create temporary result sets that can be referenced within a larger `SELECT` statement, heavily improving the readability of complex queries vs nested subqueries.

## SQL in AI & Agentic Workflows

*   **Text-to-SQL Agents:** A massive subfield of modern AI involves training Language Models or creating Agentic workflows (via frameworks like LangChain) to receive a natural language query, parse the database schema, write a complex SQL query, execute it, and return the answer.
*   **Database Connections:** AI agents connected via the [[Concept - Model Context Protocol (MCP)]] often use Postgres or SQL Server MCPs to scan database schemas securely and read proprietary data into their context windows.
*   **Vector Search Extensions:** The line between relational databases and [[Vector Databases]] is blurring. Extensions like `pgvector` for PostgreSQL allow users to run SQL queries that find records based on semantic vector similarity (e.g., `SELECT * FROM items ORDER BY embedding <-> '[0.1, ...]' LIMIT 5;`).

## Popular RDBMS
*   **PostgreSQL:** Highly advanced open-source database. Extremely popular in modern tech stacks.
*   **MySQL:** Widely used open-source relational database, especially for web applications.
*   **SQLite:** A C-language library that implements a small, fast, self-contained, high-reliability SQL database engine (often running entirely from a single file).

## Resources
*   [W3Schools SQL Tutorial](https://www.w3schools.com/sql/)
*   [PostgreSQL Official Documentation](https://www.postgresql.org/docs/)
