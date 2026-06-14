# DT Retail Solution

DT Retail Solution is a portfolio project built with Databricks to demonstrate hands-on experience with retail data analytics, SQL queries, Delta tables, and dashboard reporting.

## Project Overview

This project simulates a simple retail sales environment and uses Databricks to store, query, analyze, and visualize sales data.

## Features

- Creates a retail sales table in Databricks
- Inserts sample product sales data
- Calculates total sales
- Calculates sales by product category
- Calculates total items sold
- Displays sales insights in a Databricks dashboard
- Uses SQL for data analysis and aggregation

## Technologies Used

- Databricks
- Databricks SQL
- Delta Table
- Unity Catalog
- SQL Warehouse
- Databricks Dashboard
- SQL
- Git
- GitHub
- Visual Studio Code

## Main Table

`workspace.default.dt_retail_sales`

The table contains:

- Product
- Category
- Quantity
- Price

## Key SQL Calculations

### Total Sales

```sql
SELECT
    SUM(quantity * price) AS total_sales
FROM workspace.default.dt_retail_sales;