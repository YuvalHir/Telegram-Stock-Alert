# Stock Alert Telegram Bot and Live Summary Generator

This project is a Telegram bot designed for stock market enthusiasts. It offers real-time alerts and visualizations for stock movements while also generating concise summaries of daily live YouTube sessions. The summaries are automatically produced from live transcripts and are delivered to users via Telegram.

## Features

- **Real-Time Stock Alerts:**  
  - Set up alerts based on Simple Moving Average (SMA), target price, or a custom trend line.
  - Receive notifications when specific conditions are met, complete with charts generated using Plotly.

- **Live Summary Generation:**  
  - Fetches transcripts from daily live YouTube videos (focused on stock market updates).
  - Generates concise summaries (in Hebrew) covering key market news, analyst recommendations, major market indicators, and stock recommendations.
  - Uses Google’s Gemini API for generating summary content.

- **User Interaction:**  
  - Interactive commands and inline keyboard options using the Telegram Bot API.
  - Alerts and summaries are delivered with clear formatting, including bullet points and emojis for ease of reading.

## Prerequisites

- **Python Version:** Python 3.9 or higher (due to use of the `zoneinfo` module)
- **APIs and Services:**
  - Telegram Bot API (obtain an API token via [BotFather](https://t.me/BotFather))
  - YouTube Data API (for fetching live video details)
  - Google Gemini API (for transcript summarization)
- **Required Libraries:**  
  - `python-telegram-bot`
  - `yfinance`
  - `pandas`
  - `plotly`
  - `sqlite3` (built-in with Python)
  - `googleapiclient`
  - `youtube_transcript_api`
  - `google` (genai client)
  - `python-dotenv`
  - Other standard libraries such as `datetime`, `asyncio`, and `os`.

## Installation

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/yourusername/stock-alert-telegram-bot.git
   cd stock-alert-telegram-bot
   ```

2. **Create a Virtual Environment:**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies:**

   If a `requirements.txt` file is provided, run:

   ```bash
   pip install -r requirements.txt
   ```

   Otherwise, manually install the necessary packages:

   ```bash
   pip install python-telegram-bot yfinance pandas plotly google-api-python-client youtube_transcript_api python-dotenv
   ```

## Configuration

1. **Environment Variables:**

   Create a `.env` file in the project root (or update the provided `varribles.env` file) with the following keys:

   ```ini
   TELEGRAM_API_TOKEN=your_telegram_api_token
   GEMINI_API_KEY=your_gemini_api_key
   YOUTUBE_API_KEY=your_youtube_api_key
   ```

2. **Directories:**

   The bot will automatically create the following directories if they do not exist:
   - `transcripts` – to store fetched YouTube transcripts.
   - `summaries` – to store generated summaries.

## Usage

1. **Running the Bot:**

   To start the bot, execute:

   ```bash
   python bot.py
   ```

   The bot will begin polling for updates and schedule recurring jobs for alert checks and summary generation based on the local time in Israel.

2. **Interacting with the Bot:**

   - **Commands:**
     - `/start` – Initialize the bot and view the main menu.
     - `/newalert` – Create a new stock alert (choose between SMA, price, or custom line alerts).
     - `/listalerts` – View active alerts.
     - `/menu` – Return to the main menu.

   - **Alert Types:**
     - **SMA Alert:** Receive notifications when a stock’s price moves above or below its simple moving average.
     - **Price Alert:** Trigger an alert when a stock reaches a specified target price.
     - **Custom Line Alert:** Set alerts based on a custom trend line defined by two dates and prices.

   - **Live Summary:**
     - The bot retrieves live YouTube sessions based on defined session times, processes the transcript, and generates a concise summary for stock market investors. The summary is delivered in Hebrew (with company names in English for clarity).

## Code Structure

- **bot.py:**  
  Contains the main bot logic, including alert management, chart generation, and Telegram command handlers.

- **micha_live_summary.py:**  
  Handles the process of retrieving, processing, and summarizing YouTube live transcripts. Uses Google’s Gemini API to generate the summary text.

## Troubleshooting

- Ensure that your API keys in the `.env` file are correct and have the necessary permissions.
- Check that your environment meets the Python version requirement.
- Review log outputs in the console for any error messages that may assist in debugging.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

