#!/usr/bin/env bash
set -euo pipefail

MODEL="llama3.2"

# Check if the Sakila container is running; start or create it if needed.
if ! docker ps --format '{{.Names}}' | grep -qx "sakila"; then
    if docker ps -a --format '{{.Names}}' | grep -qx "sakila"; then
        echo "Starting existing Sakila container..."
        docker start sakila
    else
        echo "Creating Sakila database container..."
        docker run -d -p 3306:3306 --name sakila sakiladb/mysql
    fi
fi

# Make sure Ollama has the configured model available.
echo "Checking if Ollama has ${MODEL}..."
if ! ollama list | awk 'NR > 1 {print $1}' | grep -Eq "^${MODEL}(:.*)?$"; then
    echo "Downloading ${MODEL} model..."
    ollama pull "${MODEL}"
fi

echo "Starting Streamlit app..."
streamlit run app.py
