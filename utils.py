import subprocess
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt

# Function to load KPI definitions from markdown
def load_kpi_definitions(markdown_path):
    try:
        with open(markdown_path, 'r') as file:
            kpi_definitions = file.read()
        return kpi_definitions
    except FileNotFoundError:
        return "KPI definitions file not found. Please create one at " + markdown_path

# Function to query PremSQL LLM via Ollama
def query_premsql(user_query, db_schema, kpi_definitions):
    # Construct the prompt with database schema and KPI context
    prompt = f"""
    You are a SQL expert assistant that helps convert natural language queries into SQL.

    Given the following MySQL database schema:
    {db_schema}

    And these business KPI definitions:
    {kpi_definitions}

    Convert this question into a valid MySQL query: "{user_query}"

    Respond in this format:
    ```sql
    [YOUR SQL QUERY HERE]
    ```

    Explanation:
    [Explain the SQL query and how it answers the user's question. Mention any calculations or formulas that relate to KPIs]
    """

    # Call Ollama with PremSQL model
    try:
        cmd = ["ollama", "run", "anindya/prem1b-sql-ollama-fp116:latest", prompt]
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Extract SQL from the response
        response = result.stdout
        print("Response:", response)
        sql_query = extract_sql_from_response(response)
        print("SQL Query:", sql_query)
        explanation = extract_explanation_from_response(response)
        print("Explanation:", explanation)
        return sql_query, explanation, response
    except Exception as e:
        return "", f"Error calling PremSQL via Ollama: {str(e)}", str(e)

# Function to extract SQL from LLM response
def extract_sql_from_response(response):
    # Look for SQL between markdown code blocks
    if "```sql" in response and "```" in response.split("```sql")[1]:
        return response.split("```sql")[1].split("```")[0].strip()
    elif "```" in response:
        # Fallback if no specific SQL tag
        code_blocks = response.split("```")
        if len(code_blocks) > 1:
            return code_blocks[1].strip()
    return ""

# Function to extract explanation from LLM response
def extract_explanation_from_response(response):
    if "Explanation:" in response:
        explanation = response.split("Explanation:")[1].strip()
        # Remove any remaining markdown code blocks
        explanation = explanation.replace("```", "")
        return explanation
    # Fallback if no explanation section found
    if "```" in response:
        parts = response.split("```")
        if len(parts) > 2:
            return parts[2].strip()
    return response

# Function to execute SQL and return results
def execute_sql(sql_query, connection):
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
    cursor = connection.cursor()

    # Get tables
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()

    schema = []

    # For each table, get columns and their types
    for table in tables:
        table_name = table[0]
        cursor.execute(f"DESCRIBE {table_name}")
        columns = cursor.fetchall()

        table_schema = f"Table: {table_name}\n"
        table_schema += "Columns:\n"

        for column in columns:
            column_name = column[0]
            column_type = column[1]
            is_nullable = "NULL" if column[2] == "YES" else "NOT NULL"
            key = column[3] if column[3] else ""
            table_schema += f"  - {column_name} ({column_type}) {is_nullable} {key}\n"

        # Get foreign keys
        cursor.execute(f"""
            SELECT
                COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
            FROM
                INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE
                TABLE_SCHEMA = 'sakila' AND
                TABLE_NAME = '{table_name}' AND
                REFERENCED_TABLE_NAME IS NOT NULL
        """)

        foreign_keys = cursor.fetchall()

        if foreign_keys:
            table_schema += "Foreign Keys:\n"
            for fk in foreign_keys:
                table_schema += f"  - {fk[0]} -> {fk[1]}({fk[2]})\n"

        schema.append(table_schema)

    cursor.close()
    return "\n".join(schema)

# Function to visualize schema
def visualize_schema(connection):
    # Get tables and their relationships
    cursor = connection.cursor()

    # Get all tables
    cursor.execute("SHOW TABLES")
    tables = [table[0] for table in cursor.fetchall()]

    # Build a graph structure for visualization
    G = nx.DiGraph()

    # Add tables as nodes
    for table in tables:
        G.add_node(table)

    # Add foreign key relationships as edges
    for table in tables:
        cursor.execute(f"""
            SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = 'sakila'
            AND TABLE_NAME = '{table}'
            AND REFERENCED_TABLE_NAME IS NOT NULL
        """)
        relationships = cursor.fetchall()

        for rel in relationships:
            source_table = rel[0]
            target_table = rel[2]
            G.add_edge(source_table, target_table)

    # Create the visualization
    fig, ax = plt.subplots(figsize=(10, 6))
    pos = nx.spring_layout(G, seed=42)  # For consistent layout
    nx.draw(G, pos, with_labels=True, node_color='skyblue',
            node_size=2000, arrowsize=15, ax=ax, font_size=8)

    # Return the figure for Streamlit
    cursor.close()
    return fig