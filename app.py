import os

import mysql.connector
import pandas as pd
import streamlit as st

from utils import (
    enforce_read_only_session,
    execute_sql,
    get_database_schema,
    load_kpi_definitions,
    query_sqlcoder,
)


def database_config():
    """Build the MySQL connection settings from the environment with demo defaults."""
    return {
        "host": os.getenv("SAKILA_DB_HOST", "localhost"),
        "port": int(os.getenv("SAKILA_DB_PORT", "3306")),
        "user": os.getenv("SAKILA_DB_USER", "sakila"),
        "password": os.getenv("SAKILA_DB_PASSWORD", "p_ssW0rd"),
        "database": os.getenv("SAKILA_DB_NAME", "sakila"),
    }


def connect_to_database():
    """Open the Sakila connection or report a connection-specific error."""
    try:
        connection = mysql.connector.connect(**database_config())
    except Exception as exc:
        st.error(f"Error connecting to database: {exc}")
        st.info("Make sure the Sakila Docker container is running: `docker start sakila`")
        return None

    enforce_read_only_session(connection)
    return connection


def render_sidebar(db_schema, kpi_definitions):
    with st.sidebar:
        st.subheader("Database Schema")
        st.image("docs/schema.png")
        with st.expander("View KPI Definitions"):
            st.markdown(kpi_definitions)
        with st.expander("View Schema DDL"):
            st.code(db_schema, language="sql")


def handle_query(user_query, db_schema, kpi_definitions, connection):
    """Generate, validate and run one natural-language query."""
    sql_query, full_response = query_sqlcoder(user_query, db_schema, kpi_definitions)

    if not sql_query:
        st.error("Could not generate SQL from your query.")
        with st.expander("View full LLM response"):
            st.text(full_response)
        return

    st.subheader("Generated SQL Query")
    st.code(sql_query, language="sql")

    results = execute_sql(sql_query, connection)
    if isinstance(results, str):
        st.error(f"Error executing SQL: {results}")
    else:
        st.session_state.query_history.append(
            {
                "query": user_query,
                "sql": sql_query,
                "timestamp": pd.Timestamp.now(),
            }
        )
        st.subheader("Query Results")
        st.dataframe(results, width="stretch")
        st.download_button(
            label="Download results as CSV",
            data=results.to_csv(index=False),
            file_name="query_results.csv",
            mime="text/csv",
        )

    with st.expander("View full LLM response"):
        st.text(full_response)


def render_query_history():
    if not st.session_state.query_history:
        return

    st.subheader("Query History")
    history_df = pd.DataFrame(
        [
            (
                item["timestamp"].strftime("%H:%M:%S"),
                item["query"][:50] + "..." if len(item["query"]) > 50 else item["query"],
            )
            for item in st.session_state.query_history
        ],
        columns=["Time", "Query"],
    )

    selected_history = st.selectbox(
        "Select query to reuse:",
        range(len(st.session_state.query_history)),
        format_func=lambda x: f"{history_df['Time'][x]} - {history_df['Query'][x]}",
    )

    if st.button("Reuse Selected Query"):
        st.session_state.user_query = st.session_state.query_history[selected_history]["query"]
        st.rerun()


def main():
    st.set_page_config(layout="wide", page_title="Database Query Assistant")
    st.title("Sakila Database Query Assistant")
    st.write("Ask questions about your database in natural language")

    connection = connect_to_database()
    if connection is None:
        return

    st.success("Connected to Sakila database")

    try:
        db_schema = get_database_schema(connection)
        kpi_definitions = load_kpi_definitions("kpi_definitions.md")
        render_sidebar(db_schema, kpi_definitions)

        if "query_history" not in st.session_state:
            st.session_state.query_history = []

        col1, col2 = st.columns([3, 1])
        with col1:
            user_query = st.text_area(
                "Enter your question:",
                value=st.session_state.get(
                    "user_query", "Show me the top 5 most profitable movies"
                ),
                height=100,
            )
        with col2:
            st.write("Example Queries:")
            example_queries = [
                "What are the top 10 most rented films?",
                "Calculate the average revenue per customer",
                "Show me customer retention rate by city",
                "Which actor appeared in the most films?",
            ]
            for i, query in enumerate(example_queries):
                if st.button(f"Example {i + 1}", key=f"example_{i}"):
                    st.session_state.user_query = query
                    st.rerun()

        if st.button("Run Query", type="primary"):
            with st.spinner("Processing your query..."):
                handle_query(user_query, db_schema, kpi_definitions, connection)

        render_query_history()
    finally:
        connection.close()


if __name__ == "__main__":
    main()
