#!/bin/bash
# A script to update the TradeTracker Bot from Git and refresh dependencies.

# Load environment variables from the .env file
if [ -f "$(dirname "$0")/varribles.env" ]; then
    export $(cat "$(dirname "$0")/varribles.env" | grep -v '#' | sed 's/\r$//' | awk '/=/ {print $1}')
fi

# Check if PROJECT_DIR is set
if [ -z "$PROJECT_DIR" ]; then
    echo "Error: PROJECT_DIR is not set in varribles.env. Please set it to the absolute path of your project."
    exit 1
fi

echo "--- Navigating to project directory: $PROJECT_DIR ---"
cd "$PROJECT_DIR" || exit

echo "--- Pulling latest code from GitHub ---"
git pull origin main

echo "--- Activating virtual environment ---"
source .venv/bin/activate

echo "--- Updating yfinance and twikit ---"
pip install --upgrade yfinance twikit

# Define the path for the requirements hash file
HASH_FILE=".requirements_hash"
REQUIREMENTS_FILE="requirements.txt"

# --- Check and Install Requirements ---
echo "--- Checking for dependency updates ---"

# Calculate the current hash of the requirements file
CURRENT_HASH=$(sha256sum "$REQUIREMENTS_FILE" | awk '{print $1}')

# Check if the hash file exists and read the old hash
if [ -f "$HASH_FILE" ]; then
    OLD_HASH=$(cat "$HASH_FILE")
else
    OLD_HASH=""
fi

# Compare hashes. If they differ, install requirements.
if [ "$CURRENT_HASH" != "$OLD_HASH" ]; then
    echo "Dependencies have changed. Installing requirements..."
    pip install -r "$REQUIREMENTS_FILE"
    
    # Update the hash file with the new hash
    echo "$CURRENT_HASH" > "$HASH_FILE"
    echo "Requirements updated."
else
    echo "Dependencies are up-to-date. Skipping installation."
fi

echo "--- TradeTracker Bot update complete ---"