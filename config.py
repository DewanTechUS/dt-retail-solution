import os
from databricks.sdk.core import Config


databricks_config = Config()

WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID")
INVENTORY_TABLE = os.getenv("INVENTORY_TABLE")
SALES_TABLE = os.getenv("SALES_HISTORY_TABLE")
SETTINGS_TABLE = os.getenv("SETTINGS_TABLE")

SERVER_HOSTNAME = databricks_config.host.replace("https://", "")
HTTP_PATH = f"/sql/1.0/warehouses/{WAREHOUSE_ID}"