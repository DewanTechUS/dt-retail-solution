import os
import uuid
import streamlit as st
from databricks import sql
from databricks.sdk.core import Config


# -------------------------------------------------
# Databricks connection settings
# -------------------------------------------------

config = Config()

warehouse_id = os.getenv("DATABRICKS_WAREHOUSE_ID")
inventory_table = os.getenv("INVENTORY_TABLE")
sales_table = os.getenv("SALES_HISTORY_TABLE")

server_hostname = config.host.replace("https://", "")
http_path = f"/sql/1.0/warehouses/{warehouse_id}"


def get_connection():
    return sql.connect(
        server_hostname=server_hostname,
        http_path=http_path,
        credentials_provider=lambda: config.authenticate
    )


# -------------------------------------------------
# Page setup
# -------------------------------------------------

st.set_page_config(
    page_title="DT Retail Solution",
    page_icon="🛒",
    layout="wide"
)

st.title("DT Retail Solution")
st.caption("Retail Inventory & Sales Management powered by Databricks")


# -------------------------------------------------
# Get dashboard totals
# -------------------------------------------------

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


# -------------------------------------------------
# Dashboard cards
# -------------------------------------------------

col1, col2, col3, col4 = st.columns(4)

col1.metric("Products", inventory_summary[0])
col2.metric("Units in Stock", inventory_summary[1])
col3.metric("Inventory Value", f"${float(inventory_summary[2]):,.2f}")
col4.metric("Sales Revenue", f"${float(total_revenue):,.2f}")


# -------------------------------------------------
# Tabs
# -------------------------------------------------

inventory_tab, add_tab, sell_tab, manage_tab, history_tab = st.tabs(
    [
        "Inventory",
        "Add Item",
        "Sell Item",
        "Manage Item",
        "Sales History"
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
                product,
                category,
                quantity,
                price,
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

        sku = st.text_input(
            "SKU",
            placeholder="DT-1005"
        )

        product = st.text_input(
            "Product Name",
            placeholder="Coca-Cola"
        )

        category = st.text_input(
            "Category",
            placeholder="Beverages"
        )

        quantity = st.number_input(
            "Quantity",
            min_value=1,
            step=1
        )

        price = st.number_input(
            "Price",
            min_value=0.01,
            step=0.01,
            format="%.2f"
        )

        add_button = st.form_submit_button(
            "Add Item"
        )

    if add_button:

        if not sku or not product or not category:

            st.error("Please complete all fields.")

        else:

            connection = get_connection()

            with connection.cursor() as cursor:

                # Check if SKU already exists
                cursor.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {inventory_table}
                    WHERE sku = ?
                    """,
                    [sku]
                )

                exists = cursor.fetchone()[0]

                if exists:

                    st.error("This SKU already exists.")

                else:

                    cursor.execute(
                        f"""
                        INSERT INTO {inventory_table}
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        [
                            sku,
                            product,
                            category,
                            quantity,
                            price
                        ]
                    )

                    st.success("Item added successfully.")

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
                price
            FROM {inventory_table}
            WHERE quantity > 0
            ORDER BY product
        """)

        products = cursor.fetchall()

    connection.close()

    if products:

        options = {
            f"{row[0]} - {row[1]} (Stock: {row[2]})": row
            for row in products
        }

        selected = st.selectbox(
            "Select Product",
            list(options.keys())
        )

        selected_item = options[selected]

        sku = selected_item[0]
        product = selected_item[1]
        stock = selected_item[2]
        price = selected_item[3]

        st.write(f"Price: ${float(price):.2f}")
        st.write(f"Available Stock: {stock}")

        quantity_sold = st.number_input(
            "Quantity to Sell",
            min_value=1,
            max_value=int(stock),
            step=1
        )

        if st.button("Complete Sale"):

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
                    [quantity_sold, sku]
                )

                # Save sale history
                cursor.execute(
                    f"""
                    INSERT INTO {sales_table}
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

        st.info("No products are currently in stock.")


# =================================================
# MANAGE ITEM
# =================================================

with manage_tab:

    st.subheader("Manage Inventory")

    connection = get_connection()

    with connection.cursor() as cursor:

        cursor.execute(f"""
            SELECT sku, product, price
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
        current_price = float(item[2])


        # -----------------------------------------
        # Change Price
        # -----------------------------------------

        st.write("### Change Price")

        new_price = st.number_input(
            "New Price",
            min_value=0.01,
            value=current_price,
            step=0.01,
            format="%.2f"
        )

        if st.button("Update Price"):

            connection = get_connection()

            with connection.cursor() as cursor:

                cursor.execute(
                    f"""
                    UPDATE {inventory_table}
                    SET price = ?
                    WHERE sku = ?
                    """,
                    [new_price, sku]
                )

            connection.close()

            st.success("Price updated successfully.")

            st.rerun()


        # -----------------------------------------
        # Delete Item
        # -----------------------------------------

        st.divider()

        st.write("### Delete Item")

        confirm_delete = st.checkbox(
            f"I want to delete {product}"
        )

        if st.button(
            "Delete Item",
            type="primary"
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

                st.success("Item deleted successfully.")

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
        columns = [column[0] for column in cursor.description]

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

        st.info("No sales have been recorded yet.")