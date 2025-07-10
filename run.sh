#!/bin/bash

# Check if Docker is running
if ! docker ps | grep -q "sakila"; then
    echo "Starting Sakila database container..."
    docker start sakila || docker run -d -p 3306:3306 --name sakila sakiladb/mysql
fi

# Make sure Ollama is running with PremSQL model
echo "Checking if Ollama has PremSQL model..."
# if ! ollama list | grep -q "prem1b"; then
if ! ollama list | grep -q "sqlcoder"; then
    echo "Downloading PremSQL model..."
    # ollama pull anindya/prem1b-sql-ollama-fp116:latest
    ollama pull sqlcoder:7b
fi

# Start the Streamlit app
echo "Starting Streamlit app..."
streamlit run app.py
