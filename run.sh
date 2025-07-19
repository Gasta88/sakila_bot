#!/bin/bash

# Check if Docker is running
if ! docker ps | grep -q "sakila"; then
    echo "Starting Sakila database container..."
    docker start sakila || docker run -d -p 3306:3306 --name sakila sakiladb/mysql
fi

# Make sure Ollama is running with Llama3.2 model
echo "Checking if Ollama has Llama3.2 model..."
if ! ollama list | grep -q "sqlcoder"; then
    echo "Downloading Llama3.2 model..."
    ollama pull llama3.2
fi

# Start the Streamlit app
echo "Starting Streamlit app..."
streamlit run app.py
