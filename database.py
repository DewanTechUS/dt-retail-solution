from databricks import sql

from config import HTTP_PATH, SERVER_HOSTNAME, databricks_config


def get_connection():
    return sql.connect(
        server_hostname=SERVER_HOSTNAME,
        http_path=HTTP_PATH,
        credentials_provider=lambda: databricks_config.authenticate,
    )


def query_all(query, params=None):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, params or [])
            rows = cursor.fetchall()
            columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    finally:
        connection.close()


def query_one(query, params=None):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, params or [])
            return cursor.fetchone()
    finally:
        connection.close()


def execute(query, params=None):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, params or [])
    finally:
        connection.close()
