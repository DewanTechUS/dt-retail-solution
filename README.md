# DT Retail Solution

DT Retail Solution is a simple Databricks retail analytics project.

## What it does

- Creates a retail sales table in Databricks
- Inserts sample product sales data
- Calculates total sales
- Calculates sales by category
- Calculates total items sold
- Displays the results in a Databricks dashboard

## Technologies

- Databricks
- Databricks SQL
- Delta Table
- SQL Warehouse
- Databricks Dashboard
- SQL

## Main Table

`workspace.default.dt_retail_sales`

## Key Calculation

Total sales:

```sql
SUM(quantity * price)