import subprocess
import pandas as pd

# Function to load KPI definitions from markdown
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
        with open(markdown_path, 'r') as file:
            kpi_definitions = file.read()
        return kpi_definitions
    except FileNotFoundError:
        return "KPI definitions file not found. Please create one at " + markdown_path

# Function to query Llama3.2 LLM via Ollama
def query_sqlcoder(user_query, db_schema, kpi_definitions):
    """
    Queries the Llama3.2 LLM via Ollama to generate a SQL query based on the user's natural language query, database schema, and KPI definitions.

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
    tuple
        A tuple containing the generated SQL query, the explanation from the LLM, and the raw response from the LLM.
    """
    
    prompt = f"""
    ### Instructions:
    You are a SQL expert assistant that helps convert natural language queries into SQL.
    Adhere to these rules:
    - **Deliberately go through the question and database schema word by word** to appropriately answer the question
    - **Use Table Aliases** to prevent ambiguity. For example, `SELECT table1.col1, table2.col1 FROM table1 JOIN table2 ON table1.id = table2.id`.
    - When creating a ratio, always cast the numerator as float

    ### Input:
    Convert this question into a valid MySQL query: "{user_query}"
    
    Given the following MySQL database schema:
    {db_schema}

    ### Response:
    Based on your instructions, here is the SQL query I have generated to answer the question `{user_query}`:
    ```sql
    """

    # Call Ollama with Llama3.2 model
    try:
        cmd = ["ollama", "run", "llama3.2", prompt]
        result = subprocess.run(cmd, capture_output=True, text=True)
        print("Result:", result)

        # Extract SQL from the response
        response = result.stdout
        print("Response:", response)
        sql_query = extract_sql_from_response(response)
        print("SQL Query:", sql_query)
        # explanation = extract_explanation_from_response(response)
        # print("Explanation:", explanation)
        print(response)
        return sql_query, response
        # return sql_query, explanation, response
    except Exception as e:
        return "", f"Error calling Llama3.2 via Ollama: {str(e)}", str(e)

# Function to extract SQL from LLM response
def extract_sql_from_response(response):
    """
    Extract SQL from LLM response.

    Look for SQL between markdown code blocks. If there's a specific SQL block with
    triple backticks, extract the SQL. Otherwise, fall back to the first code block.

    Args:
        response (str): The response from the LLM.

    Returns:
        str: The extracted SQL query.
    """
    if "```sql" in response and "```" in response.split("```sql")[1]:
        return response.split("```sql")[1].split("```")[0].strip()
    elif "```" in response:
        # Fallback if no specific SQL tag
        code_blocks = response.split("```")
        if len(code_blocks) > 1:
            return code_blocks[1].strip()
    return ""

# # Function to extract explanation from LLM response
# def extract_explanation_from_response(response):
#     if "Explanation:" in response:
#         explanation = response.split("Explanation:")[1].strip()
#         # Remove any remaining markdown code blocks
#         explanation = explanation.replace("```", "")
#         return explanation
#     # Fallback if no explanation section found
#     if "```" in response:
#         parts = response.split("```")
#         if len(parts) > 2:
#             return parts[2].strip()
#     return response

# Function to execute SQL and return results
def execute_sql(sql_query, connection):
    """
    Executes a SQL query against a database connection and returns the results as a Pandas DataFrame.

    Parameters
    ----------
    sql_query : str
        The SQL query to execute.
    connection : mysql.connector.MySQLConnection
        The database connection to use.

    Returns
    -------
    pd.DataFrame or str
        The results of the query as a Pandas DataFrame, or an error message if the query fails.
    """
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(sql_query)
        results = cursor.fetchall()
        cursor.close()
        return pd.DataFrame(results)
    except Exception as e:
        return str(e)

# Function to get database schema
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

    # Get tables
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()

    schema = []

    # For each table, get columns and their types
    for table in tables:
        table_name = table[0]

        # Get CREATE TABLE DDL statement
        cursor.execute(f"SHOW CREATE TABLE {table_name}")
        create_table = cursor.fetchone()[1]

        # Get foreign keys
        cursor.execute(f"""
            SELECT
                CONSTRAINT_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
            FROM
                INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE
                TABLE_SCHEMA = 'sakila' AND
                TABLE_NAME = '{table_name}' AND
                REFERENCED_TABLE_NAME IS NOT NULL
        """)

        foreign_keys = cursor.fetchall()

        foreign_key_str = ""
        if foreign_keys:
            foreign_key_str = "\n"
            for fk in foreign_keys:
                foreign_key_str += f"  , FOREIGN KEY ({fk[1]}) REFERENCES {fk[2]}({fk[3]})\n"

        schema.append(f"{create_table}{foreign_key_str}")

    cursor.close()
    return "\n".join(schema)
