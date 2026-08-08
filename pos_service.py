from config import INVENTORY_TABLE, SALES_TABLE, SETTINGS_TABLE
from database import execute, get_connection, query_all, query_one


def get_settings():
    rows = query_all(
        f"""
        SELECT setting_name, setting_value
        FROM {SETTINGS_TABLE}
        """
    )
    return {row["setting_name"]: float(row["setting_value"]) for row in rows}


def get_dashboard_summary():
    inventory = query_one(
        f"""
        SELECT
            COUNT(*) AS products,
            COALESCE(SUM(quantity), 0) AS units,
            COALESCE(SUM(quantity * price), 0) AS inventory_value
        FROM {INVENTORY_TABLE}
        """
    )

    revenue = query_one(
        f"""
        SELECT COALESCE(SUM(quantity_sold * sale_price), 0)
        FROM {SALES_TABLE}
        """
    )

    return {
        "products": int(inventory[0] or 0),
        "units": int(inventory[1] or 0),
        "inventory_value": float(inventory[2] or 0),
        "revenue": float(revenue[0] or 0),
    }


def search_products(term):
    term = term.strip()
    if not term:
        return []

    return query_all(
        f"""
        SELECT
            sku,
            product,
            category,
            quantity,
            price,
            barcode,
            COALESCE(item_fee, 0) AS item_fee,
            COALESCE(tax_type, 'NONE') AS tax_type,
            COALESCE(custom_tax_rate, 0) AS custom_tax_rate
        FROM {INVENTORY_TABLE}
        WHERE
            LOWER(sku) = LOWER(?)
            OR barcode = ?
            OR LOWER(product) LIKE LOWER(?)
        ORDER BY
            CASE
                WHEN LOWER(sku) = LOWER(?) THEN 1
                WHEN barcode = ? THEN 2
                ELSE 3
            END,
            product
        LIMIT 10
        """,
        [term, term, f"%{term}%", term, term],
    )


def list_inventory():
    return query_all(
        f"""
        SELECT
            sku,
            barcode,
            product,
            category,
            quantity,
            price,
            COALESCE(item_fee, 0) AS item_fee,
            COALESCE(tax_type, 'NONE') AS tax_type,
            COALESCE(custom_tax_rate, 0) AS custom_tax_rate,
            quantity * price AS inventory_value
        FROM {INVENTORY_TABLE}
        ORDER BY product
        """
    )


def add_inventory_item(
    sku,
    barcode,
    product,
    category,
    quantity,
    price,
    item_fee,
    tax_type,
    custom_tax_rate,
):
    sku_count = query_one(
        f"SELECT COUNT(*) FROM {INVENTORY_TABLE} WHERE LOWER(sku) = LOWER(?)",
        [sku],
    )[0]

    if sku_count:
        return False, "That SKU already exists."

    if barcode:
        barcode_count = query_one(
            f"SELECT COUNT(*) FROM {INVENTORY_TABLE} WHERE barcode = ?",
            [barcode],
        )[0]
        if barcode_count:
            return False, "That barcode already exists."

    execute(
        f"""
        INSERT INTO {INVENTORY_TABLE}
        (
            sku,
            product,
            category,
            quantity,
            price,
            barcode,
            item_fee,
            tax_type,
            custom_tax_rate
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            sku,
            product,
            category,
            int(quantity),
            float(price),
            barcode or None,
            float(item_fee),
            tax_type,
            float(custom_tax_rate),
        ],
    )
    return True, "Item added."


def update_inventory_item(
    sku,
    barcode,
    quantity,
    price,
    item_fee,
    tax_type,
    custom_tax_rate,
):
    execute(
        f"""
        UPDATE {INVENTORY_TABLE}
        SET
            barcode = ?,
            quantity = ?,
            price = ?,
            item_fee = ?,
            tax_type = ?,
            custom_tax_rate = ?
        WHERE sku = ?
        """,
        [
            barcode or None,
            int(quantity),
            float(price),
            float(item_fee),
            tax_type,
            float(custom_tax_rate),
            sku,
        ],
    )


def delete_inventory_item(sku):
    execute(f"DELETE FROM {INVENTORY_TABLE} WHERE sku = ?", [sku])


def list_sales():
    return query_all(
        f"""
        SELECT
            sale_id,
            sku,
            product,
            quantity_sold,
            sale_price,
            quantity_sold * sale_price AS line_total,
            sold_at
        FROM {SALES_TABLE}
        ORDER BY sold_at DESC
        """
    )


def update_settings(low_tax, high_tax, card_fee):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            for name, value in [
                ("LOW_TAX", low_tax),
                ("HIGH_TAX", high_tax),
                ("CARD_FEE", card_fee),
            ]:
                cursor.execute(
                    f"""
                    UPDATE {SETTINGS_TABLE}
                    SET setting_value = ?
                    WHERE setting_name = ?
                    """,
                    [float(value), name],
                )
    finally:
        connection.close()


def product_tax_rate(item, tax_override, custom_tax_override, settings):
    if tax_override == "NO TAX":
        return 0.0
    if tax_override == "LOW TAX":
        return settings.get("LOW_TAX", 0.0)
    if tax_override == "HIGH TAX":
        return settings.get("HIGH_TAX", 0.0)
    if tax_override == "CUSTOM TAX":
        return float(custom_tax_override)

    tax_type = (item.get("tax_type") or "NONE").upper()
    if tax_type == "LOW":
        return settings.get("LOW_TAX", 0.0)
    if tax_type == "HIGH":
        return settings.get("HIGH_TAX", 0.0)
    if tax_type == "CUSTOM":
        return float(item.get("custom_tax_rate") or 0.0)
    return 0.0


def calculate_cart_totals(
    cart,
    payment_method,
    tax_override,
    custom_tax_override,
    apply_card_fee,
    settings,
):
    subtotal = 0.0
    fees = 0.0
    tax = 0.0

    for item in cart:
        qty = int(item["quantity"])
        line_base = float(item["price"]) * qty
        line_fee = float(item.get("item_fee", 0.0)) * qty
        rate = product_tax_rate(
            item,
            tax_override,
            custom_tax_override,
            settings,
        )
        line_tax = line_base * rate / 100.0

        subtotal += line_base
        fees += line_fee
        tax += line_tax

    before_card_fee = subtotal + fees + tax
    card_fee = 0.0

    if payment_method == "CARD" and apply_card_fee:
        card_fee = before_card_fee * settings.get("CARD_FEE", 0.0) / 100.0

    return {
        "subtotal": subtotal,
        "fees": fees,
        "tax": tax,
        "card_fee": card_fee,
        "total": before_card_fee + card_fee,
    }


def validate_cart_stock(cart):
    for item in cart:
        if item.get("manual"):
            continue

        current = query_one(
            f"SELECT quantity FROM {INVENTORY_TABLE} WHERE sku = ?",
            [item["sku"]],
        )

        if current is None or int(current[0]) < int(item["quantity"]):
            return False, item["product"]

    return True, None


def complete_sale(cart, receipt_id):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            for item in cart:
                qty = int(item["quantity"])
                price = float(item["price"])

                if not item.get("manual"):
                    cursor.execute(
                        f"""
                        UPDATE {INVENTORY_TABLE}
                        SET quantity = quantity - ?
                        WHERE sku = ?
                        """,
                        [qty, item["sku"]],
                    )

                cursor.execute(
                    f"""
                    INSERT INTO {SALES_TABLE}
                    (
                        sale_id,
                        sku,
                        product,
                        quantity_sold,
                        sale_price,
                        sold_at
                    )
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP())
                    """,
                    [receipt_id, item["sku"], item["product"], qty, price],
                )
    finally:
        connection.close()
