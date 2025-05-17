#!/usr/bin/env bash
set -e

PROJECT_DIR="/home/yuval/Telegram-Stock-Alert" # ADJUST IF PATH IS DIFFERENT
VENV_PATH="$PROJECT_DIR/venv/bin/activate"
GIT_BRANCH="main" # Or "master"
BOT_SERVICE_NAME="telegram-stock-bot.service" # The main bot service

echo "$(date): Periodic Update: Navigating to project directory $PROJECT_DIR"
cd "$PROJECT_DIR" || { echo "$(date): Periodic Update: FAILED to cd to $PROJECT_DIR"; exit 1; }

echo "$(date): Periodic Update: Checking network connectivity..."
if ! ping -c 1 -W 1 8.8.8.8 &>/dev/null; then
    echo "$(date): Periodic Update: Network not available. Skipping update check."
    exit 0 # Exit cleanly, timer will run again later
fi

echo "$(date): Periodic Update: Activating virtual environment"
# shellcheck source=/dev/null
source "$VENV_PATH" || { echo "$(date): Periodic Update: FAILED to activate venv"; exit 1; }

echo "$(date): Periodic Update: Fetching remote changes..."
git fetch origin "$GIT_BRANCH"

LOCAL_HEAD=$(git rev-parse HEAD)
REMOTE_HEAD=$(git rev-parse "origin/$GIT_BRANCH")

if [ "$LOCAL_HEAD" == "$REMOTE_HEAD" ]; then
    echo "$(date): Periodic Update: Code is already up-to-date."
else
    echo "$(date): Periodic Update: New code detected. Pulling changes..."
    if git pull origin "$GIT_BRANCH"; then
        echo "$(date): Periodic Update: Git pull successful."
        if [ -f "requirements.txt" ]; then
            echo "$(date): Periodic Update: Installing/updating dependencies..."
            if pip install -r requirements.txt; then
                 echo "$(date): Periodic Update: Dependencies updated."
            else
                echo "$(date): Periodic Update: WARNING - pip install failed during periodic update."
                # Decide if you want to proceed with restart or not. For now, we proceed.
            fi
        fi
        echo "$(date): Periodic Update: Restarting $BOT_SERVICE_NAME to apply updates..."
        # Use systemctl to restart the main bot service
        # Ensure this script has sudo privileges for systemctl if User=yuval doesn't,
        # OR run this service as root (less ideal),
        # OR configure sudoers for yuval to run this specific systemctl command without password.
        # For simplicity here, assuming yuval can restart its own user services or has passwordless sudo for this.
        if systemctl is-active --quiet "$BOT_SERVICE_NAME"; then
            # Sudo might be needed here if yuval can't restart system services
            sudo systemctl restart "$BOT_SERVICE_NAME" 
            echo "$(date): Periodic Update: $BOT_SERVICE_NAME restart command issued."
        else
            echo "$(date): Periodic Update: $BOT_SERVICE_NAME is not active, not attempting restart."
        fi
    else
        echo "$(date): Periodic Update: Git pull failed. Not restarting service."
    fi
fi

echo "$(date): Periodic Update: Deactivating virtual environment"
deactivate

echo "$(date): Periodic Update: Script completed."
exit 0