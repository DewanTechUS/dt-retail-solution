# DT Retail Solutions — Final POS UI

This build uses the final three-column checkout layout while keeping the existing Databricks backend and tables.

## Final POS layout

- **Left:** Sale items, item tax badges, cart editing, subtotal, tax, and total.
- **Center:** Cash, Card, and Print Receipt controls plus cash shortcuts and Change Due.
- **Right:** Quick Add price entry, barcode/SKU/product search, No Tax / Low Tax / High Tax / Custom Tax, number pad, quantity controls, and Add Item.

## Checkout behavior

- There is no separate **Complete Sale** button.
- **Exact / $20 / $50 / $100 / $200** automatically complete a cash sale when the tender is enough.
- Manually entered cash also completes the sale when the committed amount is enough.
- **Card** completes the card sale directly and uses the configured card fee when enabled.
- **Change Due** remains visible after a completed cash sale.
- **Print Receipt** is gray/disabled before payment and becomes green/enabled after a successful sale.

## Quick Add

- Enter manual prices using the physical keyboard or on-screen number pad.
- Choose No Tax, Low Tax, High Tax, or Custom Tax.
- Press **Add Item** to place the manual item in the sale.
- Exact barcode/SKU scans can still add inventory items directly.

## Database

No new database schema is required. Existing inventory, sales history, settings, product images, and added-at history remain compatible.
