import os
import logging
import zoneinfo
from datetime import time, datetime, timedelta

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

# Load environment variables from .env file
load_dotenv(dotenv_path='varribles.env')
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# --- Core Module Imports ---
from bot_core.database import DatabaseManager
from bot_core.services.stock_service import StockDataService
from bot_core.services.youtube_service import YouTubeService
from bot_core.services.twitter_service import TwitterService
from bot_core.services.ai_service import AIService
from bot_core.utils.cache_manager import CacheManager
from bot_core.managers.summary_manager import SummaryManager
from bot_core.alerts import AlertManager
from devutils.fear_greed_scraper import get_fear_greed_index
from bot_core.utils.market_data_cache import market_cache

# --- Handler Imports ---
from bot_core.handlers.command_handlers import (
    start,
    handle_main_menu,
    list_alerts,
    send_all_graphs_callback,
)
from bot_core.handlers.callback_handlers import (
    handle_list_alerts_callback,
    remove_alert_callback,
    alert_response_handler,
    handle_help_callback,
)
from bot_core.handlers.conversation_handlers import get_conversation_handler
from bot_core.handlers.summary_handlers import (
    summary_menu_callback,
    summary_button_handler,
    summary_text_handler,
    video_selection_callback,
)

# --- Other Service Imports ---
from bot_core import config

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Global In-memory Store ---
user_alerts = {}

# --- Summary Distribution Logic (to be moved later) ---
async def distribute_youtube_summary(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job to distribute the daily YouTube summary."""
    logger.info("Job triggered: Distributing YouTube summary.")
    summary_manager = context.bot_data.get('summary_manager')
    # This assumes you have a way to get relevant user IDs, e.g., from a database.
    # For now, let's say we have a placeholder for a main channel or user.
    main_user_id = context.bot_data.get('main_user_id') # You would need to set this
    if summary_manager and main_user_id:
        summary_text, _ = summary_manager.get_youtube_summary()
        if summary_text:
            await context.bot.send_message(chat_id=main_user_id, text=summary_text, parse_mode="HTML")
        else:
            logger.warning("Could not generate YouTube summary for distribution.")

async def distribute_twitter_recap(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job to distribute the pre-market Twitter recap."""
    logger.info("Job triggered: Distributing pre-market Twitter recap.")
    summary_manager = context.bot_data.get('summary_manager')
    main_user_id = context.bot_data.get('main_user_id')
    if summary_manager and main_user_id:
        recap = await summary_manager.get_daily_twitter_recap(before_market=True)
        if recap:
            await context.bot.send_message(chat_id=main_user_id, text=recap, parse_mode="HTML")
        else:
            logger.warning("Could not generate Twitter recap for distribution.")

async def fetch_and_cache_fear_greed_index(context: ContextTypes.DEFAULT_TYPE):
   """Scheduled job to fetch and cache the Fear & Greed Index."""
   logger.info("Job triggered: Fetching and caching Fear & Greed Index.")
   try:
       # get_fear_greed_index returns (category, value_str)
       category, value_str = get_fear_greed_index()
       fear_greed_data = f"Fear & Greed Index: {category} ({value_str})"
       market_cache.set('fear_greed_index', fear_greed_data)
       logger.info(f"Fetched and cached: {fear_greed_data}")
   except Exception as e:
       logger.error(f"Failed to fetch Fear & Greed Index in background job: {e}")


async def post_init(application: Application):
    """Post-initialization hook to perform async setup."""
    logger.info("Performing post-initialization setup...")
    twitter_service = application.bot_data['twitter_service']
    await twitter_service.login()
    logger.info("Post-initialization setup complete.")

async def fetch_and_cache_fear_greed_index(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job to fetch and cache the Fear & Greed Index."""
    logger.info("Job triggered: Fetching and caching Fear & Greed Index.")
    try:
        # get_fear_greed_index returns (category, value_str)
        category, value_str = get_fear_greed_index()
        fear_greed_data = f"Fear & Greed Index: {category} ({value_str})"
        market_cache.set('fear_greed_index', fear_greed_data)
        logger.info(f"Fetched and cached: {fear_greed_data}")
    except Exception as e:
        logger.error(f"Failed to fetch Fear & Greed Index in background job: {e}")


def main() -> None:
    """Initializes services, sets up handlers, and runs the bot."""
    global user_alerts

    if not config.API_TOKEN:
        logger.critical("TELEGRAM_API_TOKEN environment variable not set.")
        return

    # --- Service & Manager Initialization ---
    db_manager = DatabaseManager(config.DATABASE_PATH)
    stock_service = StockDataService()
    youtube_service = YouTubeService()
    twitter_service = TwitterService()
    ai_service = AIService()
    cache_manager = CacheManager()

    application = ApplicationBuilder().token(config.API_TOKEN).post_init(post_init).build()

    alert_manager = AlertManager(db_manager, stock_service, application.bot, user_alerts)
    summary_manager = SummaryManager(ai_service, youtube_service, twitter_service, cache_manager)

    user_alerts = db_manager.load_alerts()

    # --- Share Services & Managers via bot_data ---
    application.bot_data["db_manager"] = db_manager
    application.bot_data["stock_service"] = stock_service
    application.bot_data["youtube_service"] = youtube_service
    application.bot_data["twitter_service"] = twitter_service
    application.bot_data["ai_service"] = ai_service
    application.bot_data["cache_manager"] = cache_manager
    application.bot_data["user_alerts"] = user_alerts
    application.bot_data["alert_manager"] = alert_manager
    application.bot_data["summary_manager"] = summary_manager
    # You might want to add a main user/channel ID for broadcasts
    # application.bot_data["main_user_id"] = YOUR_MAIN_USER_ID

    # --- Handler Registration ---
    logger.info("Registering handlers...")

    # Core handlers
    application.add_handler(get_conversation_handler())
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", handle_main_menu))
    application.add_handler(CommandHandler("listalerts", list_alerts))

    # Callback handlers for core features
    application.add_handler(CallbackQueryHandler(handle_main_menu, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(handle_list_alerts_callback, pattern="^list_alerts$"))
    application.add_handler(CallbackQueryHandler(handle_help_callback, pattern="^help$"))
    application.add_handler(CallbackQueryHandler(remove_alert_callback, pattern=r"^remove_\d+$"))
    application.add_handler(CallbackQueryHandler(alert_response_handler, pattern=r"^keep_\d+$"))
    application.add_handler(CallbackQueryHandler(send_all_graphs_callback, pattern="^send_all_graphs$"))
    
    # New Summary Feature Handlers
    application.add_handler(CallbackQueryHandler(summary_menu_callback, pattern="^advanced$")) # Replaces 'advanced' menu
    application.add_handler(CallbackQueryHandler(summary_button_handler, pattern=r"^sum_(latest_summary|custom_summary|ai_chat)$"))
    application.add_handler(CallbackQueryHandler(video_selection_callback, pattern=r"^(video_select:|manual_video)"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, summary_text_handler))

    # --- Job Queue Setup ---
    logger.info("Setting up scheduled jobs...")
    application.job_queue.run_repeating(alert_manager.check_alerts, interval=60, first=10)

    # Updated job schedule to use new manager methods
    application.job_queue.run_daily(distribute_twitter_recap, time=config.X_SUMMARY_PRE_MARKET_TIME)
    application.job_queue.run_daily(distribute_youtube_summary, time=config.SUMMARY_POST_CLOSE_TIME)

    # Schedule the Fear & Greed Index fetching job (e.g., every 3 hours)
    # Run once immediately on startup, then repeat every 3 hours
    application.job_queue.run_repeating(fetch_and_cache_fear_greed_index, interval=3 * 3600, first=0)


    # --- Start Polling ---
    logger.info("Bot is starting polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
