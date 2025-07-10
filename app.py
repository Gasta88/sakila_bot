import streamlit as st
import pandas as pd
import mysql.connector
from utils import (load_kpi_definitions, get_database_schema,
                  query_premsql, execute_sql)

def main():
    st.set_page_config(layout="wide", page_title="Database Query Assistant")

    st.title("Sakila Database Query Assistant")
    st.write("Ask questions about your database in natural language")

    # Connect to database
    try:
        connection = mysql.connector.connect(
            host="localhost",
            user="sakila",
            password="p_ssW0rd",
            database="sakila",
            port=3306
        )
        st.success("Connected to Sakila database")

        # Get database schema
        db_schema = get_database_schema(connection)

        # Load KPI definitions
        kpi_markdown_path = "kpi_definitions.md"
        kpi_definitions = load_kpi_definitions(kpi_markdown_path)

        # Create sidebar with schema visualization
        with st.sidebar:
            st.subheader("Database Schema")
            image_path = "docs/schema.png"
            st.image(image_path)

            # Show KPI definitions
            with st.expander("View KPI Definitions"):
                st.markdown(kpi_definitions)

        # Initialize session state for query history
        if 'query_history' not in st.session_state:
            st.session_state.query_history = []

        # User query section
        col1, col2 = st.columns([3, 1])

        with col1:
            user_query = st.text_area("Enter your question:",
                          value=st.session_state.get('user_query', "Show me the top 5 most profitable movies"),
                          height=100)
        with col2:
            st.write("Example Queries:")
            example_queries = [
                "What are the top 10 most rented films?",
                "Calculate the average revenue per customer",
                "Show me customer retention rate by city",
                "Which actor appeared in the most films?"
            ]

            for i, query in enumerate(example_queries):
                if st.button(f"Example {i+1}", key=f"example_{i}"):
                    st.session_state.user_query = query
                    st.rerun()

        # Execute query button
        if st.button("Run Query", type="primary"):
            with st.spinner("Processing your query..."):
                # Get SQL from LLM
                sql_query, explanation, full_response = query_premsql(
                    user_query, db_schema, kpi_definitions
                )
                # Display the generated SQL
                st.subheader("Generated SQL Query")
                st.code(sql_query, language="sql")

                # Execute the query if SQL was generated
                if sql_query:
                    results = execute_sql(sql_query, connection)

                    # Check if result is error message
                    if isinstance(results, str):
                        st.error(f"Error executing SQL: {results}")
                    else:
                        # Save to history if successful
                        st.session_state.query_history.append({
                            'query': user_query,
                            'sql': sql_query,
                            'timestamp': pd.Timestamp.now()
                        })

                        # Display results in a table
                        st.subheader("Query Results")
                        st.dataframe(results, use_container_width=True)

                        # # Display explanation
                        st.subheader("Explanation")
                        st.markdown(explanation)

                        # Option to download results
                        csv = results.to_csv(index=False)
                        st.download_button(
                            label="Download results as CSV",
                            data=csv,
                            file_name="query_results.csv",
                            mime="text/csv"
                        )
                else:
                    st.error("Could not generate SQL from your query.")

                # # Debug view (collapsible)
                with st.expander("View full LLM response"):
                    st.text(full_response)

        # Display query history
        if st.session_state.query_history:
            st.subheader("Query History")
            history_df = pd.DataFrame(
                [(i['timestamp'].strftime('%H:%M:%S'), i['query'][:50] + "..." if len(i['query']) > 50 else i['query'])
                 for i in st.session_state.query_history],
                columns=["Time", "Query"]
            )

            selected_history = st.selectbox(
                "Select query to reuse:",
                range(len(st.session_state.query_history)),
                format_func=lambda x: f"{history_df['Time'][x]} - {history_df['Query'][x]}"
            )

            if st.button("Reuse Selected Query"):
                st.session_state.user_query = st.session_state.query_history[selected_history]['query']
                st.rerun()

    except Exception as e:
        st.error(f"Error connecting to database: {e}")
        st.info("Make sure the Sakila Docker container is running: `docker start sakila`")

if __name__ == "__main__":
    main()