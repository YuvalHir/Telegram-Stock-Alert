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

echo "--- Installing all requirements ---"
pip install -r requirements.txt

echo "--- TradeTracker Bot update complete ---"