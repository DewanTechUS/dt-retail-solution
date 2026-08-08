-- ==========================================================
-- DT RETAIL POS - RECENTLY ADDED INVENTORY HISTORY
-- RUN THIS ONCE
-- ==========================================================

-- Adds a timestamp used by the More page to show when products
-- were added to inventory. This does NOT delete existing data.

ALTER TABLE workspace.default.dt_retail_inventory
ADD COLUMNS (
    added_at TIMESTAMP
);

-- Give existing demo products a timestamp so they also appear
-- in the Recently Added Inventory section.
UPDATE workspace.default.dt_retail_inventory
SET added_at = CURRENT_TIMESTAMP()
WHERE added_at IS NULL;

SELECT
    sku,
    product,
    category,
    quantity,
    price,
    added_at
FROM workspace.default.dt_retail_inventory
ORDER BY added_at DESC;
