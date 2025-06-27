#!/bin/bash

# Installation script for TradeTracker Bot

# Define colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print a styled message
print_step() {
    echo ""
    echo -e "${BLUE}--- $1 ---${NC}"
    echo ""
}

# Function to print success message
print_success() {
    echo -e "${GREEN}✔ $1${NC}"
}

# Function to print error message
print_error() {
    echo -e "${RED}✖ $1${NC}"
}

# Function to print info message
print_info() {
    echo -e "${YELLOW}$1${NC}"
}

# --- Banner ---
echo -e "${GREEN}"
echo "-----------------------------------------------------"
echo "  TradeTracker Bot Installation Wizard"
echo "-----------------------------------------------------"
echo -e "${NC}"
print_info "Welcome! This script will guide you through the installation."

# --- Step 1: Check for Git ---
print_step "Checking for Git"
if ! command -v git &> /dev/null
then
    print_error "Git is not installed."
    echo "Please install Git first using your system's package manager or download from https://git-scm.com/downloads."
    echo "Examples:"
    echo "  Debian/Ubuntu: sudo apt-get install git"
    echo "  Fedora: sudo dnf install git"
    echo "  macOS (using Homebrew): brew install git"
    exit 1
fi
print_success "Git is installed."

# --- Step 2 & 3: Assume project is cloned and navigate to project directory ---
# Assuming the script is run from the project root or the project is cloned in the current directory.
# The current workspace directory is c:/Users/hyuva/OneDrive/Documents/tradetracker_bot
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
print_step "Navigating to project directory"
echo "Project directory: $PROJECT_DIR"
cd "$PROJECT_DIR" || { print_error "Failed to navigate to project directory."; exit 1; }
print_success "Successfully navigated to project directory."

# --- Step 4: Create Virtual Environment ---
print_step "Creating Python virtual environment (.venv)"
if [ -d ".venv" ]; then
    print_info "Virtual environment already exists."
else
    python3 -m venv .venv || { print_error "Failed to create virtual environment. Ensure python3 and venv are installed."; exit 1; }
    print_success "Virtual environment created successfully."
fi

# --- Step 5: Activate Virtual Environment ---
print_step "Activating virtual environment"
source .venv/bin/activate || { print_error "Failed to activate virtual environment."; exit 1; }
print_success "Virtual environment activated."

# --- Step 6: Install Dependencies ---
print_step "Installing dependencies from requirements.txt"
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt || { print_error "Failed to install dependencies."; exit 1; }
    print_success "Dependencies installed successfully."
else
    print_error "requirements.txt not found. Cannot install dependencies."
    exit 1
fi

# --- Step 7: Configure Environment Variables ---
print_step "Configuring Environment Variables (varribles.env)"
ENV_FILE="varribles.env"

if [ -f "$ENV_FILE" ]; then
    print_info "$ENV_FILE already exists. Skipping environment variable configuration."
else
    print_info "Please provide the following information to create your $ENV_FILE file."
    print_info "Your current PROJECT_DIR is set to: $PROJECT_DIR"

    # Prompt for each variable
    read -p "$(print_info 'Enter your YOUTUBE_API_KEY: ')" YOUTUBE_API_KEY
    read -p "$(print_info 'Enter your GEMINI_API_KEY: ')" GEMINI_API_KEY
    read -p "$(print_info 'Enter your TELEGRAM_API_TOKEN: ')" TELEGRAM_API_TOKEN
    read -p "$(print_info 'Enter your X (Twitter) Username: ')" x_username
    read -s -p "$(print_info 'Enter your X (Twitter) Password: ')" x_password # -s for silent input
    echo "" # Newline after silent input
    read -p "$(print_info 'Enter your X (Twitter) Email: ')" x_email

    # Write to .env file
    echo "# Environment variables for TradeTracker Bot" > "$ENV_FILE"
    echo "YOUTUBE_API_KEY=$YOUTUBE_API_KEY" >> "$ENV_FILE"
    echo "GEMINI_API_KEY=$GEMINI_API_KEY" >> "$ENV_FILE"
    echo "TELEGRAM_API_TOKEN=$TELEGRAM_API_TOKEN" >> "$ENV_FILE"
    echo "PROJECT_DIR=$PROJECT_DIR" >> "$ENV_FILE"
    echo "x_username=$x_username" >> "$ENV_FILE"
    echo "x_password=$x_password" >> "$ENV_FILE"
    echo "x_email=$x_email" >> "$ENV_FILE"

    print_success "$ENV_FILE created and configured."
fi

# Load environment variables from the .env file for the current script execution
# This is needed to run the bot in the next step
if [ -f "$ENV_FILE" ]; then
    export $(cat "$ENV_FILE" | grep -v '#' | sed 's/\r$//' | awk '/=/ {print $1}')
fi

# --- Step 8: Start the Bot ---
print_step "Starting the TradeTracker Bot"
# Ensure the bot script exists
if [ -f "bot.py" ]; then
    print_info "Starting bot. Press Ctrl+C to stop."
    # Execute the bot script. Use exec to replace the current shell process with the bot process.
    # This means the script will end when the bot stops.
    exec python bot.py || { print_error "Failed to start the bot."; exit 1; }
else
    print_error "bot.py not found. Cannot start the bot."
    exit 1
fi

echo -e "${GREEN}"
echo "-----------------------------------------------------"
echo "  Installation and bot startup complete"
echo "-----------------------------------------------------"
echo -e "${NC}" # This line might not be reached if exec is used