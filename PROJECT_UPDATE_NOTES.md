# DT Retail POS — Terminal UI Update

This build reformats the project around the approved dark POS terminal design while keeping the existing Databricks backend and tables.

## New POS workflow

### Quick Add Item
1. Enter a price with the large keypad. The value is shown in the large display.
2. Tap **No Tax**, **Low Tax**, or **High Tax** to add the item to the cart immediately.
3. For **Custom Tax**, enter the price, tap Custom Tax, enter the custom tax percentage with the same keypad, then press **APPLY & ADD**.
4. The cart item can be changed with **+ / -**, edited with the pencil button, or removed with the trash button.

The green **ADD ITEM** button is also available if a tax is selected before the price is entered.

### Inventory items
- Scan an exact barcode/SKU and press Enter to add it directly to the cart.
- Search by product name, SKU, barcode, or category.
- Use the inventory suggestion cards to View or Add a product.

### Checkout
- Cash and Card payment buttons are color-coded.
- Cash calculates change due.
- Card can apply the configured card fee.
- Receipt printing remains available after a completed sale.

## Navigation
- POS
- Inventory
- Add Item
- Manage Item
- Sales History
- Settings

The first three are available directly from the top bar. Manage, History, Settings, and Dark/Light mode are under **More**.

## Database
No new database schema is required for this UI update. Existing inventory, sales history, settings, product images, and added-at history remain compatible.
