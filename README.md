# TradeTracker Bot

**TradeTracker Bot** is a powerful and intelligent Telegram bot designed for stock market enthusiasts and traders. It provides real-time alerts, automated daily summaries from financial news sources, and AI-powered analysis of market commentary.

Our goal is to create a comprehensive, open-source tool that empowers users to stay on top of the market with timely and relevant information. We welcome contributors of all levels to help us build and improve this project!

---

## ✨ Key Features

-   **📈 Customizable Stock Alerts:** Set alerts for specific price targets, SMA (Simple Moving Average) crossovers, or custom trendlines.
-   **📰 Automated Daily Summaries:**
    -   **Pre-Market Briefing:** Get a summary of market-moving news from financial experts on Twitter/X.
    -   **End-of-Day Recap:** Receive a detailed summary of key events and discussions from popular YouTube finance live streams.
-   **🤖 AI-Powered Chat:** Have a conversation with an AI about the transcript of a specific financial YouTube video.
-   **🚀 Automated Deployment:** Includes `systemd` service files for easy, automated deployment and updates on a Linux system like a Raspberry Pi.

---

## 🚀 Getting Started

Follow these steps to get the bot running on your local machine.

### Prerequisites

-   Python 3.10+
-   A Telegram Bot Token
-   API keys for Google (YouTube & Gemini) and a Twitter/X account.

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/YuvalHir/Telegram-Stock-Alert.git /home/yuval/tradetracker_bot
    cd /home/yuval/tradetracker_bot
    ```

2.  **Create a virtual environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install the dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure your environment variables:**
    -   Create a file named `varribles.env` by copying the example: `cp varribles.env.example varribles.env`
    -   Edit `varribles.env` with your details.
    ```env
    # The absolute path to your project directory (e.g., /home/yuval/tradetracker_bot)
    PROJECT_DIR="/home/yuval/tradetracker_bot"

    # --- API Keys & Credentials ---
    TELEGRAM_API_TOKEN="your_telegram_token"
    GEMINI_API_KEY="your_gemini_api_key"
    YOUTUBE_API_KEY="your_youtube_api_key"
    X_USERNAME="your_twitter_username"
    X_EMAIL="your_twitter_email"
    X_PASSWORD="your_twitter_password"
    ```

5.  **Run the bot (for testing):**
    ```bash
    python bot.py
    ```

---
## 🐧 Raspberry Pi Deployment (Automated Startup)

The repository includes service files to automate running the bot on a Linux system with `systemd`.

1.  **Make the update script executable:**
    ```bash
    chmod +x update.sh
    ```
2.  **Link the service files to systemd:**
    ```bash
    sudo ln -s /home/yuval/tradetracker_bot/update-bot.service /etc/systemd/system/update-bot.service
    sudo ln -s /home/yuval/tradetracker_bot/tradetracker.service /etc/systemd/system/tradetracker.service
    ```
3.  **Reload the systemd daemon, enable, and start the services:**
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable update-bot.service
    sudo systemctl enable tradetracker.service
    sudo systemctl start tradetracker.service
    ```
The bot will now start automatically on boot.

---

## 🤝 How to Contribute

We are thrilled you're interested in contributing!

1.  **Fork the repository**.
2.  **Create a new branch** (`git checkout -b feature/your-awesome-feature`).
3.  **Make your changes.**
4.  **Submit a pull request** with a clear description of your changes.

---

## 📜 License

This project is licensed under the MIT License.