#!/bin/bash
# A script to update the TradeTracker Bot from Git and refresh dependencies.

# Navigate to the bot's directory
# IMPORTANT: You may need to change this path to match your setup on the Raspberry Pi
cd /home/pi/tradetracker_bot || exit

echo "--- Pulling latest code from GitHub ---"
git pull origin main

echo "--- Activating virtual environment ---"
# Activate the Python virtual environment
source .venv/bin/activate

echo "--- Updating yfinance and twikit ---"
# Update the key libraries that can have frequent patches
pip install --upgrade yfinance twikit

echo "--- Installing all requirements ---"
# Install any new requirements if requirements.txt has changed
pip install -r requirements.txt

echo "--- TradeTracker Bot update complete ---"