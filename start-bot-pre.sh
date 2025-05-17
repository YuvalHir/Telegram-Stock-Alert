#!/usr/bin/env bash
set -e # Exit immediately if a command exits with a non-zero status.

PROJECT_DIR="/home/yuval/Telegram-Stock-Alert" # ADJUST IF PATH IS DIFFERENT
VENV_PATH="$PROJECT_DIR/venv/bin/activate"
GIT_BRANCH="main" # Or "master", or your primary branch name

echo "$(date): Bot Pre-start: Navigating to project directory $PROJECT_DIR"
cd "$PROJECT_DIR" || { echo "$(date): Bot Pre-start: FAILED to cd to $PROJECT_DIR"; exit 1; }

# Simple network check - ping Google's DNS
MAX_RETRIES=5
RETRY_COUNT=0
while ! ping -c 1 -W 1 8.8.8.8 &>/dev/null; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ "$RETRY_COUNT" -ge "$MAX_RETRIES" ]; then
        echo "$(date): Bot Pre-start: Network check failed after $MAX_RETRIES retries. Attempting to proceed with local code."
        # If network is critical for git pull, you might want to exit 1 here
        # but per preference, we proceed if git pull fails later
        break
    fi
    echo "$(date): Bot Pre-start: Network not (yet) available. Retrying in 5 seconds... (Attempt $RETRY_COUNT/$MAX_RETRIES)"
    sleep 5
done
if [ "$RETRY_COUNT" -lt "$MAX_RETRIES" ]; then
    echo "$(date): Bot Pre-start: Network check successful."
fi


echo "$(date): Bot Pre-start: Activating virtual environment"
# shellcheck source=/dev/null
source "$VENV_PATH" || { echo "$(date): Bot Pre-start: FAILED to activate virtual environment at $VENV_PATH"; exit 1; }

echo "$(date): Bot Pre-start: Attempting to pull latest changes from Git (branch: $GIT_BRANCH)..."
# Store current commit hash
OLD_HEAD=$(git rev-parse HEAD 2>/dev/null || echo "initial_clone")

if git pull origin "$GIT_BRANCH"; then
    echo "$(date): Bot Pre-start: Git pull successful."
    NEW_HEAD=$(git rev-parse HEAD 2>/dev/null)
    if [ "$OLD_HEAD" != "$NEW_HEAD" ]; then
        echo "$(date): Bot Pre-start: New code pulled. Checking for updated dependencies..."
        if [ -f "requirements.txt" ]; then
            echo "$(date): Bot Pre-start: Installing/updating dependencies from requirements.txt..."
            if pip install -r requirements.txt; then
                echo "$(date): Bot Pre-start: Dependencies installation/update attempt finished."
            else
                echo "$(date): Bot Pre-start: WARNING - pip install -r requirements.txt failed. Continuing with existing environment."
            fi
        else
            echo "$(date): Bot Pre-start: requirements.txt not found, skipping dependency update check."
        fi
    else
        echo "$(date): Bot Pre-start: No new code pulled from git."
    fi
else
    echo "$(date): Bot Pre-start: WARNING - Git pull failed. Exit code: $?. Proceeding with local code."
    # Log this prominently, but don't exit, as per user preference.
fi

echo "$(date): Bot Pre-start: Deactivating virtual environment (systemd will reactivate for ExecStart)"
deactivate

echo "$(date): Bot Pre-start: Pre-start script completed."
exit 0