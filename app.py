import os
import uuid
import streamlit as st
from databricks import sql
from databricks.sdk.core import Config


# =================================================
# DATABRICKS CONNECTION
# =================================================

config = Config()

warehouse_id = os.getenv("DATABRICKS_WAREHOUSE_ID")
inventory_table = os.getenv("INVENTORY_TABLE")
sales_table = os.getenv("SALES_HISTORY_TABLE")
settings_table = os.getenv("SETTINGS_TABLE")

server_hostname = config.host.replace("https://", "")
http_path = f"/sql/1.0/warehouses/{warehouse_id}"


def get_connection():
    return sql.connect(
        server_hostname=server_hostname,
        http_path=http_path,
        credentials_provider=lambda: config.authenticate
    )


# =================================================
# PAGE SETUP
# =================================================

st.set_page_config(
    page_title="DT Retail Solution",
    page_icon="🛒",
    layout="wide"
)

st.title("DT Retail Solution")
st.caption("Retail Inventory & Sales Management powered by Databricks")


# =================================================
# DASHBOARD TOTALS
# =================================================

connection = get_connection()

with connection.cursor() as cursor:

    cursor.execute(f"""
        SELECT
            COUNT(*) AS products,
            COALESCE(SUM(quantity), 0) AS units,
            COALESCE(SUM(quantity * price), 0) AS inventory_value
        FROM {inventory_table}
    """)

    inventory_summary = cursor.fetchone()

    cursor.execute(f"""
        SELECT
            COALESCE(SUM(quantity_sold * sale_price), 0)
        FROM {sales_table}
    """)

    total_revenue = cursor.fetchone()[0]

connection.close()


col1, col2, col3, col4 = st.columns(4)

col1.metric("Products", inventory_summary[0])
col2.metric("Units in Stock", inventory_summary[1])
col3.metric(
    "Inventory Value",
    f"${float(inventory_summary[2]):,.2f}"
)
col4.metric(
    "Sales Revenue",
    f"${float(total_revenue):,.2f}"
)


# =================================================
# TABS
# =================================================

(
    inventory_tab,
    add_tab,
    sell_tab,
    manage_tab,
    history_tab,
    settings_tab
) = st.tabs(
    [
        "Inventory",
        "Add Item",
        "Sell Item",
        "Manage Item",
        "Sales History",
        "Settings"
    ]
)


# =================================================
# INVENTORY
# =================================================

with inventory_tab:

    st.subheader("Current Inventory")

    connection = get_connection()

    with connection.cursor() as cursor:

        cursor.execute(f"""
            SELECT
                sku,
                barcode,
                product,
                category,
                quantity,
                price,
                item_fee,
                tax_type,
                custom_tax_rate,
                quantity * price AS total_value
            FROM {inventory_table}
            ORDER BY sku
        """)

        rows = cursor.fetchall()
        columns = [column[0] for column in cursor.description]

    connection.close()

    inventory_data = [
        dict(zip(columns, row))
        for row in rows
    ]

    st.dataframe(
        inventory_data,
        use_container_width=True
    )


# =================================================
# ADD ITEM
# =================================================

with add_tab:

    st.subheader("Add New Item")

    with st.form("add_item_form"):

        col1, col2 = st.columns(2)

        with col1:

            sku = st.text_input(
                "SKU",
                placeholder="DT-1005"
            )

            barcode = st.text_input(
                "Barcode",
                placeholder="100000000005"
            )

            product = st.text_input(
                "Product Name",
                placeholder="Coca-Cola"
            )

            category = st.text_input(
                "Category",
                placeholder="Beverages"
            )

        with col2:

            quantity = st.number_input(
                "Quantity",
                min_value=0,
                step=1
            )

            price = st.number_input(
                "Price",
                min_value=0.01,
                step=0.01,
                format="%.2f"
            )

            item_fee = st.number_input(
                "Item Fee",
                min_value=0.00,
                step=0.01,
                format="%.2f"
            )

            tax_type = st.selectbox(
                "Tax Type",
                [
                    "NONE",
                    "LOW",
                    "HIGH",
                    "CUSTOM"
                ]
            )

        custom_tax_rate = 0.00

        if tax_type == "CUSTOM":
            custom_tax_rate = st.number_input(
                "Custom Tax %",
                min_value=0.00,
                step=0.10,
                format="%.2f"
            )

        add_button = st.form_submit_button(
            "Add Item"
        )

    if add_button:

        sku = sku.strip().upper()
        product = product.strip()
        category = category.strip()
        barcode = barcode.strip()

        if not sku or not product or not category:

            st.error(
                "SKU, product name, and category are required."
            )

        else:

            connection = get_connection()

            with connection.cursor() as cursor:

                cursor.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {inventory_table}
                    WHERE sku = ?
                    """,
                    [sku]
                )

                sku_exists = cursor.fetchone()[0]

                if sku_exists:

                    st.error("This SKU already exists.")

                else:

                    if barcode:

                        cursor.execute(
                            f"""
                            SELECT COUNT(*)
                            FROM {inventory_table}
                            WHERE barcode = ?
                            """,
                            [barcode]
                        )

                        barcode_exists = cursor.fetchone()[0]

                    else:

                        barcode_exists = 0

                    if barcode_exists:

                        st.error(
                            "This barcode already exists."
                        )

                    else:

                        cursor.execute(
                            f"""
                            INSERT INTO {inventory_table}
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
                                quantity,
                                price,
                                barcode if barcode else None,
                                item_fee,
                                tax_type,
                                custom_tax_rate
                            ]
                        )

                        st.success(
                            "Item added successfully."
                        )

            connection.close()

            st.rerun()


# =================================================
# SELL ITEM
# =================================================

with sell_tab:

    st.subheader("Sell Item")

    connection = get_connection()

    with connection.cursor() as cursor:

        cursor.execute(f"""
            SELECT
                sku,
                product,
                quantity,
                price,
                barcode
            FROM {inventory_table}
            WHERE quantity > 0
            ORDER BY product
        """)

        products = cursor.fetchall()

    connection.close()

    if products:

        options = {
            f"{row[0]} - {row[1]} | Stock: {row[2]}": row
            for row in products
        }

        selected = st.selectbox(
            "Select Product",
            list(options.keys())
        )

        selected_item = options[selected]

        sku = selected_item[0]
        product = selected_item[1]
        stock = int(selected_item[2])
        price = float(selected_item[3])
        barcode = selected_item[4]

        info1, info2, info3 = st.columns(3)

        info1.metric("Price", f"${price:.2f}")
        info2.metric("Available Stock", stock)
        info3.write(
            f"**Barcode:** {barcode or 'Not assigned'}"
        )

        quantity_sold = st.number_input(
            "Quantity to Sell",
            min_value=1,
            max_value=stock,
            step=1
        )

        sale_total = quantity_sold * price

        st.metric(
            "Sale Total",
            f"${sale_total:,.2f}"
        )

        if st.button(
            "Complete Sale",
            type="primary"
        ):

            sale_id = str(uuid.uuid4())[:8].upper()

            connection = get_connection()

            with connection.cursor() as cursor:

                # Reduce inventory
                cursor.execute(
                    f"""
                    UPDATE {inventory_table}
                    SET quantity = quantity - ?
                    WHERE sku = ?
                    """,
                    [
                        quantity_sold,
                        sku
                    ]
                )

                # Record sale
                # Column names are specified so this also works
                # if your sales table has extra receipt fields.
                cursor.execute(
                    f"""
                    INSERT INTO {sales_table}
                    (
                        sale_id,
                        sku,
                        product,
                        quantity_sold,
                        sale_price,
                        sold_at
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, CURRENT_TIMESTAMP()
                    )
                    """,
                    [
                        sale_id,
                        sku,
                        product,
                        quantity_sold,
                        price
                    ]
                )

            connection.close()

            st.success(
                f"Sale completed. Sale ID: {sale_id}"
            )

            st.rerun()

    else:

        st.info(
            "No products are currently in stock."
        )


# =================================================
# MANAGE ITEM
# =================================================

with manage_tab:

    st.subheader("Manage Inventory")

    connection = get_connection()

    with connection.cursor() as cursor:

        cursor.execute(f"""
            SELECT
                sku,
                product,
                quantity,
                price,
                item_fee,
                tax_type,
                custom_tax_rate,
                barcode
            FROM {inventory_table}
            ORDER BY product
        """)

        products = cursor.fetchall()

    connection.close()

    if products:

        options = {
            f"{row[0]} - {row[1]}": row
            for row in products
        }

        selected = st.selectbox(
            "Select Item",
            list(options.keys()),
            key="manage_item"
        )

        item = options[selected]

        sku = item[0]
        product = item[1]
        current_quantity = int(item[2])
        current_price = float(item[3])
        current_fee = float(item[4] or 0)
        current_tax_type = item[5] or "NONE"
        current_custom_tax = float(item[6] or 0)
        current_barcode = item[7] or ""

        st.write(f"### Edit {product}")

        new_barcode = st.text_input(
            "Barcode",
            value=current_barcode
        )

        new_quantity = st.number_input(
            "Stock Quantity",
            min_value=0,
            value=current_quantity,
            step=1
        )

        new_price = st.number_input(
            "Price",
            min_value=0.01,
            value=current_price,
            step=0.01,
            format="%.2f"
        )

        new_fee = st.number_input(
            "Item Fee",
            min_value=0.00,
            value=current_fee,
            step=0.01,
            format="%.2f"
        )

        tax_options = [
            "NONE",
            "LOW",
            "HIGH",
            "CUSTOM"
        ]

        tax_index = (
            tax_options.index(current_tax_type)
            if current_tax_type in tax_options
            else 0
        )

        new_tax_type = st.selectbox(
            "Tax Type",
            tax_options,
            index=tax_index
        )

        new_custom_tax = 0.00

        if new_tax_type == "CUSTOM":

            new_custom_tax = st.number_input(
                "Custom Tax %",
                min_value=0.00,
                value=current_custom_tax,
                step=0.10,
                format="%.2f"
            )

        if st.button(
            "Save Item Changes"
        ):

            connection = get_connection()

            with connection.cursor() as cursor:

                cursor.execute(
                    f"""
                    UPDATE {inventory_table}
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
                        new_barcode,
                        new_quantity,
                        new_price,
                        new_fee,
                        new_tax_type,
                        new_custom_tax,
                        sku
                    ]
                )

            connection.close()

            st.success(
                "Item updated successfully."
            )

            st.rerun()


        # -----------------------------------------
        # DELETE ITEM
        # -----------------------------------------

        st.divider()

        st.write("### Delete Item")

        st.warning(
            "Deleting an item removes it from inventory."
        )

        confirm_delete = st.checkbox(
            f"I confirm that I want to delete {product}"
        )

        if st.button(
            "Delete Item"
        ):

            if not confirm_delete:

                st.warning(
                    "Please confirm before deleting."
                )

            else:

                connection = get_connection()

                with connection.cursor() as cursor:

                    cursor.execute(
                        f"""
                        DELETE FROM {inventory_table}
                        WHERE sku = ?
                        """,
                        [sku]
                    )

                connection.close()

                st.success(
                    "Item deleted successfully."
                )

                st.rerun()


# =================================================
# SALES HISTORY
# =================================================

with history_tab:

    st.subheader("Sales History")

    connection = get_connection()

    with connection.cursor() as cursor:

        cursor.execute(f"""
            SELECT
                sale_id,
                sku,
                product,
                quantity_sold,
                sale_price,
                quantity_sold * sale_price AS total,
                sold_at
            FROM {sales_table}
            ORDER BY sold_at DESC
        """)

        rows = cursor.fetchall()
        columns = [
            column[0]
            for column in cursor.description
        ]

    connection.close()

    sales_data = [
        dict(zip(columns, row))
        for row in rows
    ]

    if sales_data:

        st.dataframe(
            sales_data,
            use_container_width=True
        )

    else:

        st.info(
            "No sales have been recorded yet."
        )


# =================================================
# SETTINGS
# =================================================

with settings_tab:

    st.subheader("POS Settings")

    st.caption(
        "Configure tax rates and card fee."
    )

    connection = get_connection()

    with connection.cursor() as cursor:

        cursor.execute(f"""
            SELECT
                setting_name,
                setting_value
            FROM {settings_table}
        """)

        rows = cursor.fetchall()

    connection.close()

    settings = {
        row[0]: float(row[1])
        for row in rows
    }

    col1, col2, col3 = st.columns(3)

    with col1:

        low_tax = st.number_input(
            "Low Tax %",
            min_value=0.00,
            value=settings.get(
                "LOW_TAX",
                0.00
            ),
            step=0.10,
            format="%.2f"
        )

    with col2:

        high_tax = st.number_input(
            "High Tax %",
            min_value=0.00,
            value=settings.get(
                "HIGH_TAX",
                0.00
            ),
            step=0.10,
            format="%.2f"
        )

    with col3:

        card_fee = st.number_input(
            "Card Fee %",
            min_value=0.00,
            value=settings.get(
                "CARD_FEE",
                0.00
            ),
            step=0.10,
            format="%.2f"
        )

    if st.button(
        "Save Settings",
        type="primary"
    ):

        connection = get_connection()

        with connection.cursor() as cursor:

            cursor.execute(
                f"""
                UPDATE {settings_table}
                SET setting_value = ?
                WHERE setting_name = 'LOW_TAX'
                """,
                [low_tax]
            )

            cursor.execute(
                f"""
                UPDATE {settings_table}
                SET setting_value = ?
                WHERE setting_name = 'HIGH_TAX'
                """,
                [high_tax]
            )

            cursor.execute(
                f"""
                UPDATE {settings_table}
                SET setting_value = ?
                WHERE setting_name = 'CARD_FEE'
                """,
                [card_fee]
            )

        connection.close()

        st.success(
            "POS settings saved successfully."
        )

        st.rerun()