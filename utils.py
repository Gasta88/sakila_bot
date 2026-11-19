import os
import subprocess

import pandas as pd
import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

DEFAULT_MAX_ROWS = 1000
DEFAULT_LLM_TIMEOUT = 120

_ALLOWED_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)
_FORBIDDEN_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.TruncateTable,
    exp.Grant,
    exp.Command,
    exp.Into,
    exp.Lock,
    exp.Transaction,
)
_FORBIDDEN_FUNCTIONS = {"load_file", "sleep", "benchmark", "get_lock"}


class SQLValidationError(ValueError):
    """Raised when generated SQL is not a read-only single SELECT statement."""


def resolve_max_rows(max_rows=None):
    """Return the row cap, honouring an explicit value or SAKILA_MAX_ROWS."""
    if max_rows is not None:
        return max_rows
    try:
        return int(os.getenv("SAKILA_MAX_ROWS", DEFAULT_MAX_ROWS))
    except (TypeError, ValueError):
        return DEFAULT_MAX_ROWS


def validate_sql(sql_query, max_rows=None):
    """
    Validate and normalise a generated SQL query.

    Only a single read-only SELECT statement (including WITH and set operations)
    is accepted. Anything that writes, locks, reads files, sleeps or chains
    statements is rejected. A row cap is always enforced.

    Parameters
    ----------
    sql_query : str
        The SQL statement produced by the LLM.
    max_rows : int, optional
        Rows the result is capped at. Defaults to SAKILA_MAX_ROWS or 1000.

    Returns
    -------
    str
        The normalised SQL statement with a LIMIT clause.

    Raises
    ------
    SQLValidationError
        If the statement is missing, unparsable, not a single SELECT, or uses a
        forbidden clause/function.
    """
    if not isinstance(sql_query, str) or not sql_query.strip():
        raise SQLValidationError("no SQL statement was generated")

    try:
        parsed = sqlglot.parse(sql_query, read="mysql")
    except ParseError as exc:
        raise SQLValidationError(f"could not parse SQL: {exc}") from exc

    statements = [statement for statement in parsed if statement is not None]
    if len(statements) != 1:
        raise SQLValidationError("exactly one SQL statement is allowed")

    statement = statements[0]
    if not isinstance(statement, _ALLOWED_ROOTS):
        raise SQLValidationError(
            f"only read-only SELECT queries are allowed, got {type(statement).__name__.upper()}"
        )

    for node in statement.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise SQLValidationError(
                f"forbidden SQL clause: {type(node).__name__.upper()}"
            )
        if isinstance(node, exp.Func):
            if isinstance(node, exp.Anonymous):
                function_name = str(node.this).lower()
            else:
                function_name = node.sql_name().lower()
            if function_name in _FORBIDDEN_FUNCTIONS:
                raise SQLValidationError(f"forbidden SQL function: {function_name}")

    row_cap = resolve_max_rows(max_rows)
    if not _limit_within_cap(statement, row_cap):
        statement = statement.limit(row_cap)

    return statement.sql(dialect="mysql")


def _limit_within_cap(statement, row_cap):
    """Return True when the statement already has an integer LIMIT <= row_cap."""
    limit = statement.args.get("limit")
    if limit is None:
        return False
    if getattr(limit, "offset", None) is not None:
        return False
    value = limit.expression
    if not isinstance(value, exp.Literal) or not value.is_int:
        return False
    try:
        return int(value.this) <= row_cap
    except (TypeError, ValueError):
        return False


def load_kpi_definitions(markdown_path):
    """
    Loads KPI definitions from a markdown file.

    Parameters
    ----------
    markdown_path : str
        The path to the markdown file containing the KPI definitions.

    Returns
    -------
    str
        The KPI definitions as a string of markdown.
    """
    try:
        with open(markdown_path, "r") as file:
            return file.read()
    except FileNotFoundError:
        return "KPI definitions file not found. Please create one at " + markdown_path


def query_sqlcoder(user_query, db_schema, kpi_definitions):
    """
    Query the Llama3.2 LLM via Ollama and extract a SQL statement.

    Parameters
    ----------
    user_query : str
        The natural language query from the user.
    db_schema : str
        The database schema as a string.
    kpi_definitions : str
        The KPI definitions as a string of markdown.

    Returns
    -------
    tuple[str, str]
        Always a two-item tuple: (generated SQL or "" on failure, raw LLM
        response or an error message).
    """
    prompt = (
        "\n"
        "    ### Instructions:\n"
        "    You are a SQL expert assistant that helps convert natural language queries into SQL.\n"
        "    Adhere to these rules:\n"
        "    - **Deliberately go through the question and database schema word by word**"
        " to appropriately answer the question\n"
        "    - **Use Table Aliases** to prevent ambiguity. For example,"
        " `SELECT table1.col1, table2.col1 FROM table1 JOIN table2"
        " ON table1.id = table2.id`.\n"
        "    - When creating a ratio, always cast the numerator as float\n"
        "\n"
        "    ### Input:\n"
        f'    Convert this question into a valid MySQL query: "{user_query}"\n'
        "\n"
        "    Given the following MySQL database schema:\n"
        f"    {db_schema}\n"
        "\n"
        "    ### Response:\n"
        "    Based on your instructions, here is the SQL query I have generated to answer"
        f' the question `{user_query}`:\n'
        "    ```sql\n"
        "    "
    )

    timeout = int(os.getenv("OLLAMA_TIMEOUT", DEFAULT_LLM_TIMEOUT))

    try:
        result = subprocess.run(
            ["ollama", "run", "llama3.2", prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return "", f"Ollama did not respond within {timeout} seconds"
    except Exception as exc:
        return "", f"Error calling Llama3.2 via Ollama: {exc}"

    response = result.stdout
    return extract_sql_from_response(response), response


def extract_sql_from_response(response):
    """
    Extract SQL from an LLM response.

    Look for SQL between markdown code blocks. If there's a specific SQL block
    with triple backticks, extract the SQL. Otherwise, fall back to the first
    code block.

    Args:
        response (str): The response from the LLM.

    Returns:
        str: The extracted SQL query.
    """
    if "```sql" in response and "```" in response.split("```sql")[1]:
        return response.split("```sql")[1].split("```")[0].strip()
    elif "```" in response:
        code_blocks = response.split("```")
        if len(code_blocks) > 1:
            return code_blocks[1].strip()
    return ""


def execute_sql(sql_query, connection, max_rows=None):
    """
    Validate and execute a read-only SQL query.

    Parameters
    ----------
    sql_query : str
        The SQL query to execute.
    connection : mysql.connector.MySQLConnection
        The database connection to use.
    max_rows : int, optional
        Row cap applied to the query. Defaults to SAKILA_MAX_ROWS or 1000.

    Returns
    -------
    pd.DataFrame or str
        The results as a Pandas DataFrame, or an error message when the query is
        rejected or fails.
    """
    try:
        safe_sql = validate_sql(sql_query, max_rows=max_rows)
    except SQLValidationError as exc:
        return f"Query rejected: {exc}"

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(safe_sql)
        results = cursor.fetchall()
        cursor.close()
        return pd.DataFrame(results)
    except Exception as exc:
        return str(exc)


def enforce_read_only_session(connection):
    """
    Best-effort defence in depth: make the MySQL session read-only.

    The SQL allowlist in validate_sql is the primary control; this blocks writes
    at the database level for engines that support read-only transactions.
    """
    try:
        cursor = connection.cursor()
        cursor.execute("SET SESSION TRANSACTION READ ONLY")
        cursor.close()
        return True
    except Exception:
        return False


def get_database_schema(connection):
    """
    Retrieves the schema of the database as a string.

    This function connects to the given database and retrieves the schema
    information for each table, including the CREATE TABLE DDL statements
    and any foreign key constraints.

    Parameters
    ----------
    connection : mysql.connector.MySQLConnection
        The database connection to use.

    Returns
    -------
    str
        A string representation of the database schema, including table
        creation statements and foreign key definitions.
    """
    cursor = connection.cursor()

    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()

    schema = []

    for table in tables:
        table_name = table[0]

        cursor.execute(f"SHOW CREATE TABLE {table_name}")
        create_table = cursor.fetchone()[1]

        cursor.execute(
            f"""
            SELECT
                CONSTRAINT_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
            FROM
                INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE
                TABLE_SCHEMA = 'sakila' AND
                TABLE_NAME = '{table_name}' AND
                REFERENCED_TABLE_NAME IS NOT NULL
        """
        )
        foreign_keys = cursor.fetchall()

        foreign_key_str = ""
        if foreign_keys:
            foreign_key_str = "\n"
            for fk in foreign_keys:
                foreign_key_str += (
                    f"  , FOREIGN KEY ({fk[1]}) REFERENCES {fk[2]}({fk[3]})\n"
                )

        schema.append(f"{create_table}{foreign_key_str}")

    cursor.close()
    return "\n".join(schema)
