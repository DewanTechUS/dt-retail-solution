-- =========================================================
-- DT RETAIL POS - PRODUCT IMAGE UPGRADE
-- RUN THIS ONCE IN DATABRICKS SQL EDITOR
-- =========================================================

ALTER TABLE workspace.default.dt_retail_inventory
ADD COLUMNS (
    image_data STRING
);

-- Verify the new column exists
SELECT
    sku,
    product,
    image_data
FROM workspace.default.dt_retail_inventory
ORDER BY sku;
