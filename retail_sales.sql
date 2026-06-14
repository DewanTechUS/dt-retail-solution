/*
DT Retail Solution
Simple Databricks retail analytics project

CREATE TABLE
= Make the table

INSERT INTO
= Put data inside

SELECT *
= Show the data

SUM(quantity * price)
= Calculate total sales

GROUP BY category
= Calculate sales separately for each category
*/


-- Step 1: Create the retail sales table

CREATE OR REPLACE TABLE workspace.default.dt_retail_sales (
    product STRING,
    category STRING,
    quantity INT,
    price DOUBLE
);


-- Step 2: Add sample sales data

INSERT INTO workspace.default.dt_retail_sales VALUES
('Coffee', 'Beverages', 3, 3.50),
('Chips', 'Snacks', 2, 2.50),
('Sandwich', 'Food', 4, 6.50),
('Batteries', 'Household', 1, 7.99);


-- Step 3: Show all data

SELECT *
FROM workspace.default.dt_retail_sales;


-- Step 4: Calculate total sales

SELECT
    SUM(quantity * price) AS total_sales
FROM workspace.default.dt_retail_sales;


-- Step 5: Calculate sales by category

SELECT
    category,
    SUM(quantity * price) AS sales
FROM workspace.default.dt_retail_sales
GROUP BY category;


-- Step 6: Calculate total items sold

SELECT
    SUM(quantity) AS total_items
FROM workspace.default.dt_retail_sales;