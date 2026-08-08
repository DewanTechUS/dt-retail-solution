import os
import streamlit as st
from databricks import sql
from databricks.sdk.core import Config

# Get Databricks settings
config = Config()

warehouse_id = os.getenv("DATABRICKS_WAREHOUSE_ID")
table_name = os.getenv("UC_TABLE_NAME")

# Databricks SQL connection
server_hostname = config.host.replace("https://", "")
http_path = f"/sql/1.0/warehouses/{warehouse_id}"

connection = sql.connect(
    server_hostname=server_hostname,
    http_path=http_path,
    credentials_provider=lambda: config.authenticate
)

# Run SQL
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

# Show app
st.title("DT Retail Solution")

st.metric("Total Sales", f"${result[0]:.2f}")
st.metric("Total Items Sold", result[1])