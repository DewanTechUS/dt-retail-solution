import os
import streamlit as st
from databricks import sql
from databricks.sdk.core import Config

config = Config()

warehouse_id = os.getenv("DATABRICKS_WAREHOUSE_ID")
table_name = os.getenv("UC_TABLE_NAME")

server_hostname = config.host.replace("https://", "")
http_path = f"/sql/1.0/warehouses/{warehouse_id}"


def get_connection():
    return sql.connect(
        server_hostname=server_hostname,
        http_path=http_path,
        credentials_provider=lambda: config.authenticate
    )


st.title("DT Retail Solution")


# -------------------------
# Show current totals
# -------------------------

connection = get_connection()

query = f"""
SELECT
    SUM(quantity * price) AS total_sales,
    SUM(quantity) AS total_items
FROM {table_name}
"""

with connection.cursor() as cursor:
    cursor.execute(query)
    result = cursor.fetchone()

connection.close()

col1, col2 = st.columns(2)

col1.metric("Total Sales", f"${result[0]:.2f}")
col2.metric("Total Items Sold", result[1])


# -------------------------
# Add New Item
# -------------------------

st.subheader("Add New Item")

product = st.text_input("Product")
category = st.text_input("Category")
quantity = st.number_input("Quantity", min_value=1, step=1)
price = st.number_input("Price", min_value=0.01, step=0.01)

if st.button("Add Item"):

    connection = get_connection()

    query = f"""
    INSERT INTO {table_name}
    VALUES (?, ?, ?, ?)
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            [product, category, quantity, price]
        )

    connection.close()

    st.success("Item added successfully.")
    st.rerun()