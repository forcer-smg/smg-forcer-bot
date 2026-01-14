# -*- coding: utf-8 -*-
"""
SMG-Forcer Telegram Bot with Subscription System
Integrates SMG-Forcer AI into Telegram with subscriptions, payments, and referrals
"""

import os
import sys
import logging
import asyncio
import time
from typing import Dict
from pathlib import Path
from datetime import datetime, time as dt_time
from dotenv import load_dotenv, set_key
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.helpers import escape_markdown as tg_escape_markdown
from telegram.error import BadRequest

# Import modules
from HacxGPT import Config, HacxBrain
# Use hybrid database - auto-detects SQLite or PostgreSQL based on DATABASE_URL
try:
    from database_hybrid import Database
except ImportError:
    # Fallback to SQLite if hybrid not available
    from database import Database
from oxapay import OxaPay, PLANS, get_plan_info
# Dashboard features imported lazily to avoid circular dependency

# Import new upgrade modules
try:
    from background_processor import get_background_processor, BackgroundProcessor
    BACKGROUND_PROCESSOR_AVAILABLE = True
except ImportError:
    BACKGROUND_PROCESSOR_AVAILABLE = False
    logger.warning("background_processor not available")

try:
    from multi_model_manager import get_model_manager, MultiModelManager
    MULTI_MODEL_AVAILABLE = True
except ImportError:
    MULTI_MODEL_AVAILABLE = False
    logger.warning("multi_model_manager not available")

try:
    from approval_manager import get_approval_manager, ApprovalManager, ActionType, ApprovalStatus
    APPROVAL_MANAGER_AVAILABLE = True
except ImportError:
    APPROVAL_MANAGER_AVAILABLE = False
    logger.warning("approval_manager not available")

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(dotenv_path=Config.ENV_FILE)

# Global variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Mode constants
MODES = {
    'plan': '📋 Plan',
    'ask': '❓ Ask', 
    'debug': '🐛 Debug',
    'auto': '⚡ Auto'
}
DEFAULT_MODE = 'auto'

# Multi-DeepSeek API keys
def get_deepseek_api_keys():
    """Get all DeepSeek API keys from environment"""
    keys = []
    for key_name in Config.DEEPSEEK_API_KEYS:
        key = os.getenv(key_name)
        if key:
            keys.append(key)
    return keys

DEEPSEEK_API_KEYS = get_deepseek_api_keys()

# Initialize database and payment
db = Database()
oxapay = OxaPay()

# Store user sessions (user_id -> HacxBrain instance)
# Thread-safe session management for concurrent users
import threading
user_sessions: Dict[int, HacxBrain] = {}
user_sessions_lock = threading.Lock()  # Lock for thread-safe access

# Per-user rate limiting (user_id -> last_update_time)
user_rate_limits: Dict[int, float] = {}
user_rate_limits_lock = threading.Lock()

# Message edit tracking (for safe_edit_message_text)
_message_edit_cache: Dict[str, str] = {}  # message_id -> content
_message_edit_times: Dict[str, float] = {}  # message_id -> last_edit_time
_message_edit_failures: Dict[str, int] = {}  # message_id -> consecutive_failures
_message_edit_lock = asyncio.Lock()  # Async lock for concurrent edits
_edit_in_progress: Dict[str, bool] = {}  # message_id -> is_editing

# Message edit rate limiting and failure tracking
_message_edit_cache: Dict[str, str] = {}  # message_id -> content
_message_edit_times: Dict[str, float] = {}  # message_id -> last_edit_time
_message_edit_failures: Dict[str, int] = {}  # message_id -> consecutive_failures
_message_edit_lock = asyncio.Lock()  # Async lock for concurrent edits
_edit_in_progress: Dict[str, bool] = {}  # message_id -> is_editing

# Concurrency management for 500+ users
try:
    from concurrency_manager import get_concurrency_manager, ConcurrencyManager
    CONCURRENCY_MANAGER_AVAILABLE = True
    concurrency_manager = get_concurrency_manager(max_concurrent=500)
except ImportError:
    CONCURRENCY_MANAGER_AVAILABLE = False
    concurrency_manager = None
    logger.warning("concurrency_manager not available")

# Secure memory management
try:
    from secure_memory_manager import get_secure_memory_manager, SecureMemoryManager
    from memory_cleanup_service import get_cleanup_service, MemoryCleanupService
    SECURE_MEMORY_AVAILABLE = True
    secure_memory = get_secure_memory_manager(retention_days=3)
    cleanup_service = get_cleanup_service(secure_memory, cleanup_interval=3600)
except ImportError:
    SECURE_MEMORY_AVAILABLE = False
    secure_memory = None
    cleanup_service = None
    logger.warning("secure_memory_manager not available")

# Global application instance (set in main())
bot_application = None

# Helper function to execute database queries (handles both SQLite and PostgreSQL)
def execute_db_query(conn, query, params):
    """Execute a database query with proper syntax for SQLite or PostgreSQL"""
    try:
        from psycopg2.extras import RealDictCursor
        # PostgreSQL
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        # Replace ? with %s for PostgreSQL
        pg_query = query.replace('?', '%s')
        cursor.execute(pg_query, params)
        return cursor
    except (ImportError, AttributeError):
        # SQLite
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor

# Support contact
SUPPORT_CONTACT_URL = "https://t.me/Lesstalk420"

# Channel for updates (users must join to use the bot)
REQUIRED_CHANNEL = "@credhounddb"  # Channel username with @
REQUIRED_CHANNEL_URL = "https://t.me/credhounddb"


def get_support_button_row():
    """Reusable support button row for inline keyboards."""
    return [InlineKeyboardButton("📞 Contact Support", url=SUPPORT_CONTACT_URL)]


def get_user_mode(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Get user's current mode from context or database"""
    mode_key = f'user_mode_{user_id}'
    if context and context.user_data and mode_key in context.user_data:
        return context.user_data[mode_key]
    # Fallback to database
    mode = db.get_user_mode(user_id)
    if context and context.user_data:
        context.user_data[mode_key] = mode
    return mode


def set_user_mode(user_id: int, mode: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Set user's mode in both context and database"""
    if mode not in MODES:
        logger.warning(f"Invalid mode: {mode}, defaulting to 'auto'")
        mode = DEFAULT_MODE
    mode_key = f'user_mode_{user_id}'
    if context and context.user_data:
        context.user_data[mode_key] = mode
    return db.set_user_mode(user_id, mode)


def create_mode_keyboard(user_id: int, context: ContextTypes.DEFAULT_TYPE, additional_buttons=None):
    """Create inline keyboard with mode buttons + optional additional buttons"""
    current_mode = get_user_mode(user_id, context)
    
    # Create mode buttons row
    mode_buttons = []
    for mode_key, mode_label in MODES.items():
        # Highlight active mode
        if mode_key == current_mode:
            button_text = f"✅ {mode_label}"
        else:
            button_text = mode_label
        mode_buttons.append(InlineKeyboardButton(button_text, callback_data=f"mode_switch_{mode_key}"))
    
    keyboard = [mode_buttons]
    
    # Add additional buttons if provided
    if additional_buttons:
        if isinstance(additional_buttons, list):
            keyboard.extend(additional_buttons)
        else:
            keyboard.append(additional_buttons)
    
    return InlineKeyboardMarkup(keyboard)


def get_reply_markup_with_mode(user_id: int, context: ContextTypes.DEFAULT_TYPE, additional_buttons=None):
    """Get reply markup with mode keyboard + optional additional buttons"""
    return create_mode_keyboard(user_id, context, additional_buttons)


def ensure_mode_keyboard_at_bottom(user_id: int, context: ContextTypes.DEFAULT_TYPE, existing_keyboard=None):
    """Ensure mode keyboard is always at the bottom of any keyboard (like Cursor)
    
    Args:
        user_id: Telegram user ID
        context: Bot context
        existing_keyboard: Optional existing InlineKeyboardMarkup to append mode buttons to
    
    Returns:
        InlineKeyboardMarkup with mode buttons always at the bottom
    """
    # Get mode keyboard
    mode_keyboard = create_mode_keyboard(user_id, context)
    mode_buttons_row = mode_keyboard.inline_keyboard[0]  # Mode buttons are first row
    
    if existing_keyboard:
        # Check if mode buttons already exist (to avoid duplicates)
        existing_rows = existing_keyboard.inline_keyboard
        # Check if last row already has mode buttons
        if existing_rows and len(existing_rows) > 0:
            last_row = existing_rows[-1]
            # Check if any button in last row is a mode button
            has_mode_buttons = any(
                btn.callback_data and btn.callback_data.startswith("mode_switch_")
                for btn in last_row
            )
            if has_mode_buttons:
                # Mode buttons already exist, return existing keyboard
                return existing_keyboard
        
        # Append mode buttons as last row
        # Convert existing_rows to list if it's a tuple
        existing_rows_list = list(existing_rows) if isinstance(existing_rows, tuple) else existing_rows
        combined_rows = existing_rows_list + [mode_buttons_row]
        return InlineKeyboardMarkup(combined_rows)
    
    # No existing keyboard, return just mode keyboard
    return mode_keyboard


def create_scan_results_keyboard(scan_id: str, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    """Create interactive keyboard for scan results"""
    keyboard = []
    
    # Main sections
    keyboard.append([
        InlineKeyboardButton("📊 Summary", callback_data=f"scan_results_summary_{scan_id}"),
        InlineKeyboardButton("🔍 Vulnerabilities", callback_data=f"scan_results_vulns_{scan_id}")
    ])
    keyboard.append([
        InlineKeyboardButton("💥 Exploits", callback_data=f"scan_results_exploits_{scan_id}"),
        InlineKeyboardButton("🛠️ Tools Used", callback_data=f"scan_results_tools_{scan_id}")
    ])
    keyboard.append([
        InlineKeyboardButton("📋 Full Report", callback_data=f"scan_results_full_{scan_id}"),
        InlineKeyboardButton("💾 Download", callback_data=f"scan_results_download_{scan_id}")
    ])
    
    # Add mode keyboard at bottom
    return ensure_mode_keyboard_at_bottom(user_id, context, InlineKeyboardMarkup(keyboard))


async def check_channel_membership(bot, user_id: int, channel: str) -> bool:
    """Check if user is a member of the required channel"""
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        # User is a member if status is 'member', 'administrator', 'creator', or 'restricted'
        return member.status in ['member', 'administrator', 'creator', 'restricted']
    except Exception as e:
        # If we can't check (e.g., bot not admin in channel), log and allow access
        logger.warning(f"Could not check channel membership for user {user_id}: {e}")
        # Return True to allow access if check fails (fail open)
        return True


def get_join_channel_message() -> tuple:
    """Get the join channel message and keyboard"""
    message = """
╔═══════════════════════════════════════╗
║     📢 JOIN CHANNEL REQUIRED 📢        ║
╚═══════════════════════════════════════╝

To use this bot, you must join our channel for updates:

🔔 **Cred Hound DB**
Get the latest updates and announcements!

📋 **Steps:**
1. Click the button below to join
2. Come back and use /start again

Thank you for your support! 🙏
    """
    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=REQUIRED_CHANNEL_URL)],
        [InlineKeyboardButton("✅ I've Joined", callback_data="check_channel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    return message, reply_markup


def escape_markdown(text: str) -> str:
    """Escape special Markdown characters to prevent parsing errors."""
    # Use Telegram's built-in escape function for reliability
    return tg_escape_markdown(text, version=2)


async def safe_reply_text(update: Update, text: str, parse_mode: str = 'Markdown', **kwargs):
    """Safely send a message with Markdown, falling back to plain text if parsing fails."""
    try:
        await update.message.reply_text(text, parse_mode=parse_mode, **kwargs)
    except BadRequest as e:
        # Handle Markdown parsing errors specifically
        if 'parse' in str(e).lower() or 'entity' in str(e).lower():
            # Markdown parsing failed, try with escaped text
            try:
                escaped_text = escape_markdown(text)
                await update.message.reply_text(escaped_text, parse_mode=parse_mode, **kwargs)
            except Exception:
                # If escaping also fails, send as plain text
                await update.message.reply_text(text, parse_mode=None, **kwargs)
        else:
            # Re-raise if it's a different BadRequest error
            raise


# Message edit rate limiting and failure tracking (replaces old _message_content_cache)
# These are defined at module level after the lock initialization

async def safe_edit_message_text(query, text: str, parse_mode: str = 'Markdown', max_retries: int = 0, min_edit_interval: float = 10.0, **kwargs):
    """
    Safely edit a message with Markdown, falling back to plain text if parsing fails.
    Includes content caching, length checks, rate limiting, and retry logic with backoff.
    
    Args:
        query: Query object (CallbackQuery or Update)
        text: Text to send
        parse_mode: Parse mode (default: 'Markdown')
        max_retries: Maximum retry attempts (default: 0, no retries)
        min_edit_interval: Minimum seconds between edits for same message (default: 10.0, increased)
        **kwargs: Additional arguments for edit_message_text
    """
    # Get rate limiter
    try:
        from telegram_rate_limiter import get_telegram_rate_limiter
        rate_limiter = get_telegram_rate_limiter()
    except ImportError:
        rate_limiter = None
    
    # Get message ID for caching
    message_id = None
    chat_id = None
    if hasattr(query, 'message') and query.message:
        message_id = f"{query.message.chat.id}_{query.message.message_id}"
        chat_id = query.message.chat.id
    elif hasattr(query, 'effective_message') and query.effective_message:
        message_id = f"{query.effective_message.chat.id}_{query.effective_message.message_id}"
        chat_id = query.effective_message.chat.id
    
    # Early exit if no message ID
    if not message_id:
        logger.warning("safe_edit_message_text: No message ID found, skipping edit")
        return
    
    # Use async lock to prevent concurrent edits
    async with _message_edit_lock:
        # Check if content is unchanged
        if message_id in _message_edit_cache:
            if _message_edit_cache[message_id] == text:
                return  # Skip unchanged edit
        
        # Check if edit is already in progress for this message
        if message_id in _edit_in_progress and _edit_in_progress[message_id]:
            logger.debug(f"Edit already in progress for {message_id}, skipping")
            return
        
        # Rate limiting: Check if we've edited this message too recently
        if message_id in _message_edit_times:
            time_since_last_edit = time.time() - _message_edit_times[message_id]
            if time_since_last_edit < min_edit_interval:
                # Too soon to edit - skip this edit
                logger.debug(f"Too soon to edit {message_id} ({time_since_last_edit:.1f}s < {min_edit_interval}s)")
                return
        
        # Check if this message has too many consecutive failures
        if message_id in _message_edit_failures:
            if _message_edit_failures[message_id] >= 1:  # Stop after 1 failure (400 errors are permanent)
                # Too many failures - stop trying to edit
                logger.debug(f"Message {message_id} has {_message_edit_failures[message_id]} failures, skipping edit")
                return
        
        # Mark as in progress
        _edit_in_progress[message_id] = True
    
        # Check message length (Telegram limit is 4096 chars)
        if len(text) > 4000:
            # Truncate and add indicator
            text = text[:4000] + "\n\n... (message truncated)"
        
        # Check rate limiter before attempting edit
        if rate_limiter:
            if not rate_limiter.can_send_message():
                # Rate limit hit - skip edit
                logger.debug(f"Skipping edit due to rate limit")
                _edit_in_progress[message_id] = False
                return
        
        # Wait if rate limiter says we need to
        if rate_limiter:
            await rate_limiter.wait_if_needed()
        
        try:
            await query.edit_message_text(text, parse_mode=parse_mode, **kwargs)
            
            # Record successful send in rate limiter
            if rate_limiter:
                rate_limiter.record_message_sent()
            
            # Cache successful edit
            _message_edit_cache[message_id] = text
            _message_edit_times[message_id] = time.time()
            _message_edit_failures[message_id] = 0  # Reset failure count on success
            _edit_in_progress[message_id] = False
            return
            
        except BadRequest as e:
            error_str = str(e).lower()
            
            # Handle 400 Bad Request errors - DO NOT RETRY (these are permanent errors)
            if '400' in error_str or 'bad request' in error_str:
                logger.warning(f"400 Bad Request on edit_message_text - stopping edits for this message: {e}")
                # Mark as failed and stop trying (don't send new message, just stop)
                _message_edit_failures[message_id] = 999  # Mark as permanently failed
                _edit_in_progress[message_id] = False
                return
            
            # Handle 429 rate limit errors
            if '429' in error_str or 'too many requests' in error_str or 'rate limit' in error_str:
                logger.warning(f"Rate limit hit on edit_message_text")
                if rate_limiter:
                    # Extract retry_after if available
                    retry_after = None
                    if 'retry_after' in error_str:
                        import re
                        match = re.search(r'retry_after[:\s]+(\d+)', error_str)
                        if match:
                            retry_after = int(match.group(1))
                    rate_limiter.handle_rate_limit(retry_after)
                
                # Mark as failed and stop trying
                _message_edit_failures[message_id] = (_message_edit_failures.get(message_id, 0) + 1)
                _edit_in_progress[message_id] = False
                return
            
            # Handle other errors
            logger.warning(f"Error editing message: {e}")
            _message_edit_failures[message_id] = (_message_edit_failures.get(message_id, 0) + 1)
            _edit_in_progress[message_id] = False
            return
            
        except Exception as e:
            # Handle any other unexpected errors
            logger.error(f"Unexpected error in safe_edit_message_text: {e}", exc_info=True)
            if message_id:
                _message_edit_failures[message_id] = (_message_edit_failures.get(message_id, 0) + 1)
                _edit_in_progress[message_id] = False
            return
            if 'message is not modified' in error_str:
                # Content unchanged - cache and return
                if message_id:
                    with _message_edit_lock:
                        _message_edit_cache[message_id] = text
                        _message_edit_times[message_id] = time.time()
                return
            
            if 'message to edit not found' in error_str or 'message can\'t be edited' in error_str:
                # Message can't be edited - send new message instead
                try:
                    if hasattr(query, 'message') and query.message:
                        await query.message.reply_text(text[:4000], parse_mode=parse_mode, **kwargs)
                    elif hasattr(query, 'effective_message') and query.effective_message:
                        await query.effective_message.reply_text(text[:4000], parse_mode=parse_mode, **kwargs)
                    if message_id:
                        with _message_edit_lock:
                            _message_edit_failures[message_id] = 0  # Reset on successful send
                except Exception:
                    pass
                return
            
            # Handle Markdown parsing errors
            if 'parse' in error_str or 'entity' in error_str:
                # Try with escaped text
                try:
                    escaped_text = tg_escape_markdown(text, version=2)
                    await query.edit_message_text(escaped_text, parse_mode=parse_mode, **kwargs)
                    if message_id:
                        with _message_edit_lock:
                            _message_edit_cache[message_id] = text
                            _message_edit_times[message_id] = time.time()
                            _message_edit_failures[message_id] = 0
                    return
                except Exception:
                    # If escaping also fails, try plain text
                    try:
                        await query.edit_message_text(text[:4000], parse_mode=None, **kwargs)
                        if message_id:
                            with _message_edit_lock:
                                _message_edit_cache[message_id] = text
                                _message_edit_times[message_id] = time.time()
                                _message_edit_failures[message_id] = 0
                        return
                    except Exception:
                        pass
            
            # Increment failure count
            if message_id:
                with _message_edit_lock:
                    _message_edit_failures[message_id] = _message_edit_failures.get(message_id, 0) + 1
            
            # Stop immediately - don't retry (prevents API spam)
            # Send new message instead of editing
            logger.warning(f"Edit failed, sending new message instead: {e}")
            try:
                if hasattr(query, 'message') and query.message:
                    await query.message.reply_text(text[:4000], parse_mode=parse_mode, **kwargs)
                elif hasattr(query, 'effective_message') and query.effective_message:
                    await query.effective_message.reply_text(text[:4000], parse_mode=parse_mode, **kwargs)
                if rate_limiter:
                    rate_limiter.record_message_sent()
                if message_id:
                    with _message_edit_lock:
                        _message_edit_failures[message_id] = 0  # Reset on successful send
            except Exception as send_error:
                logger.warning(f"Failed to send message after edit failure: {send_error}")
            return
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 0.1
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Error editing message after {max_retries} attempts: {e}")
    
    # If all retries failed, log but don't raise
    if last_error:
        logger.warning(f"Could not edit message after {max_retries} attempts: {last_error}")


class TelegramUI:
    """Dummy UI class for Telegram bot (HacxBrain requires UI parameter)"""
    def show_msg(self, title: str, content: str, color: str = "white"):
        pass


def get_user_brain(user_id: int) -> HacxBrain:
    """Get or create HacxBrain instance for a user (thread-safe)"""
    # Thread-safe access to user sessions
    with user_sessions_lock:
        if user_id in user_sessions:
            return user_sessions[user_id]
        
        # Create new session if not exists
        if not DEEPSEEK_API_KEYS:
            logger.error("No DeepSeek API keys found! Please set at least SMG-Forcer-API in .hacx file")
            if os.getenv("PRODUCTION_MODE") == "true":
                logger.error("Production mode: Exiting due to missing API keys")
                sys.exit(1)
            raise ValueError("No DeepSeek API keys configured. Contact admin.")
        
        ui = TelegramUI()
        # Pass all API keys for multi-key rotation
        user_sessions[user_id] = HacxBrain(DEEPSEEK_API_KEYS, ui)
        logger.info(f"Created new session for user {user_id} with {len(DEEPSEEK_API_KEYS)} DeepSeek API keys")
        return user_sessions[user_id]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    try:
        user_id = update.effective_user.id
        username = update.effective_user.username
        first_name = update.effective_user.first_name
        
        # Get or create user
        user = db.get_or_create_user(user_id, username, first_name)
        
        # Check for referral code
        referral_code = None
        if context.args:
            referral_code = context.args[0]
            if referral_code.startswith('ref_'):
                referral_code = referral_code[4:]
                db.use_referral_code(user_id, referral_code)
        
        # Get usage stats
        stats = db.get_user_usage_stats(user_id)
        if not stats:
            # Fallback stats if database returns None
            stats = {
                'plan_type': 'free',
                'remaining': 3,
                'requests_limit': 3,
                'today_usage': 0
            }
        
        # Ensure all required keys exist
        plan_type = stats.get('plan_type', 'free')
        remaining = stats.get('remaining', 0)
        requests_limit = stats.get('requests_limit', 3)
        today_usage = stats.get('today_usage', 0)
        is_admin_user = stats.get('is_admin', False)
        
        # Format for display
        if is_admin_user or requests_limit == float('inf'):
            plan_display = "ADMIN"
            requests_display = "Unlimited"
            today_display = f"{today_usage} (Tracked)"
        else:
            plan_display = plan_type.upper()
            requests_display = f"{remaining}/{requests_limit}"
            today_display = f"{today_usage}/3"
        
        welcome_message = f"""
╔═══════════════════════════════════════╗
║   🔥 SMG-FORCER AI FRAMEWORK 🔥      ║
╚═══════════════════════════════════════╝

┌─ SYSTEM STATUS ─────────────────────┐
│ STATUS: ✅ ACTIVE                    │
│ PROTOCOL: FORCE ENABLED              │
│ MODE: UNRESTRICTED                   │
└──────────────────────────────────────┘

┌─ YOUR ACCOUNT ──────────────────────┐
│ Plan Type: `{plan_display:<20}` │
│ Requests: `{requests_display:<20}` │
│ Today: `{today_display:<22}` │
└──────────────────────────────────────┘
        """
        
        # Show expiration for upgraded users
        if stats.get('is_premium') and 'end_date' in stats:
            from datetime import datetime, timezone
            try:
                end_date_str = stats['end_date']
                if isinstance(end_date_str, str):
                    if 'Z' in end_date_str or '+' in end_date_str:
                        end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                    else:
                        end_date = datetime.strptime(end_date_str, '%Y-%m-%d %H:%M:%S')
                else:
                    end_date = end_date_str
                
                now = datetime.now(timezone.utc) if end_date.tzinfo else datetime.now()
                if end_date.tzinfo:
                    now = datetime.now(timezone.utc)
                else:
                    now = datetime.now()
                
                time_remaining = end_date - now
                
                if time_remaining.total_seconds() > 0:
                    days = time_remaining.days
                    hours, remainder = divmod(time_remaining.seconds, 3600)
                    minutes, _ = divmod(remainder, 60)
                    
                    if days > 0:
                        time_left = f"{days}d {hours}h {minutes}m"
                    elif hours > 0:
                        time_left = f"{hours}h {minutes}m"
                    else:
                        time_left = f"{minutes}m"
                    
                    welcome_message += f"\n┌─ UPGRADE EXPIRES ────────────────────┐\n"
                    welcome_message += f"│ Expires: `{end_date.strftime('%Y-%m-%d %H:%M'):<22}` │\n"
                    welcome_message += f"│ Time Left: `{time_left:<21}` │\n"
                    welcome_message += f"└──────────────────────────────────────┘"
            except:
                pass
        
        welcome_message += "\n\n💬 *Ready to chat!* Just send a message.\n\n📢 Join our channel for updates: https://t.me/credhounddb\n\n📊 Use the buttons below to manage your account."
        
        # Main menu keyboard with mode buttons
        menu_buttons = [
            [
                InlineKeyboardButton("📊 My Status", callback_data="menu_status"),
                InlineKeyboardButton("💎 Plans", callback_data="menu_plans")
            ],
            [
                InlineKeyboardButton("🎁 Referral", callback_data="menu_referral"),
                InlineKeyboardButton("🆕 New Chat", callback_data="menu_new")
            ],
            [
                InlineKeyboardButton("🖥️ Dashboard", callback_data="dashboard_menu"),
                InlineKeyboardButton("❓ Help", callback_data="menu_help")
            ],
            [
                InlineKeyboardButton("💳 Subscribe", callback_data="menu_subscribe")
            ]
        ]
        menu_buttons.append(get_support_button_row())
        # Create reply markup with mode keyboard + menu buttons
        reply_markup = create_mode_keyboard(user_id, context, menu_buttons)
        
        try:
            await update.message.reply_text(welcome_message, parse_mode='Markdown', reply_markup=reply_markup)
        except Exception as parse_error:
            # Fallback to plain text if Markdown parsing fails
            logger.warning(f"Markdown parse error, using plain text: {parse_error}")
            welcome_message_plain = welcome_message.replace('*', '').replace('_', '')
            await update.message.reply_text(welcome_message_plain, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in start command: {e}", exc_info=True)
        try:
            error_msg = (
                f"❌ Error occurred while starting the bot\n\n"
                f"Please try again or contact support.\n\n"
                f"Error: {str(e)}"
            )
            await update.message.reply_text(error_msg)
        except:
            logger.error("Failed to send error message to user")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """
╔═══════════════════════════════════════╗
║        📖 COMMAND REFERENCE           ║
╚═══════════════════════════════════════╝

┌─ BASIC COMMANDS ────────────────────┐
│ /start  → Initialize system          │
│ /help   → Show this reference        │
│ /new    → Reset conversation         │
│ /status → Check account status       │
└──────────────────────────────────────┘

┌─ SUBSCRIPTION ───────────────────────┐
│ /plans      → View all plans         │
│ /subscribe  → Purchase subscription   │
└──────────────────────────────────────┘

┌─ REFERRAL SYSTEM ────────────────────┐
│ /referral  → Get your referral code  │
│             Earn 20 free requests!    │
└──────────────────────────────────────┘

┌─ USAGE ──────────────────────────────┐
│ Just send any message to chat!       │
│                                       │
│ Free: 3 requests (one-time)          │
│ Premium: Unlimited requests           │
└──────────────────────────────────────┘
    """
    
    # Help menu keyboard
    keyboard = [
        [
            InlineKeyboardButton("💎 View Plans", callback_data="menu_plans"),
            InlineKeyboardButton("📊 My Status", callback_data="menu_status")
        ],
        [
            InlineKeyboardButton("🎁 Referral Code", callback_data="menu_referral"),
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
        ]
    ]
    keyboard.append(get_support_button_row())
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(help_text, parse_mode='Markdown', reply_markup=reply_markup)


async def plans_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show subscription plans"""
    plans_text = """
╔═══════════════════════════════════════╗
║      💎 SUBSCRIPTION PLANS 💎         ║
╚═══════════════════════════════════════╝

┌─ 🆓 FREE TIER ───────────────────────┐
│ • Requests: 3 (one-time, no refresh) │
│ • Expiration: Never                  │
│ • Perfect for testing                 │
│ • Price: FREE                         │
└──────────────────────────────────────┘

┌─ 🧪 TEST PLAN - $15 ─────────────────┐
│ • Requests: 100 total                │
│ • Duration: 7 days                  │
│ • Great for trying features          │
│ • Price: $15 USD                     │
└──────────────────────────────────────┘

┌─ ⭐ PREMIUM PLAN - $100 ──────────────┐
│ • Requests: 1,500 total              │
│ • Duration: 30 days                 │
│ • Best value for power users         │
│ • Price: $100 USD                    │
└──────────────────────────────────────┘

💳 Use `/subscribe <plan>` to purchase
    """
    
    keyboard = [
        [
            InlineKeyboardButton("🧪 Test Plan - $15", callback_data="plan_test"),
            InlineKeyboardButton("⭐ Premium - $100", callback_data="plan_premium")
        ],
        [
            InlineKeyboardButton("📊 My Status", callback_data="menu_status"),
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(plans_text, parse_mode='Markdown', reply_markup=reply_markup)


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /subscribe command"""
    if not context.args:
        await plans_command(update, context)
        return
    
    plan_type = context.args[0].lower()
    if plan_type not in PLANS:
        await update.message.reply_text(
            "❌ Invalid plan. Use `/plans` to see available plans.",
            parse_mode='Markdown'
        )
        return
    
    user_id = update.effective_user.id
    plan = PLANS[plan_type]
    
    # Create payment with dynamic webhook URL (Railway or local)
    # Get webhook URL from environment (Railway provides RAILWAY_PUBLIC_DOMAIN)
    railway_static = os.getenv('RAILWAY_STATIC_URL')
    railway_domain = os.getenv('RAILWAY_PUBLIC_DOMAIN')
    
    if railway_static:
        callback_url = f"{railway_static}/webhook/oxapay"
    elif railway_domain:
        callback_url = f"https://{railway_domain}/webhook/oxapay"
    else:
        # Fallback for local development (use ngrok or similar)
        callback_url = os.getenv('WEBHOOK_URL', 'https://your-domain.com/webhook/oxapay')
        logger.warning(f"Using fallback webhook URL: {callback_url}. Set RAILWAY_PUBLIC_DOMAIN or WEBHOOK_URL for production.")
    
    payment_result = oxapay.create_subscription_payment(user_id, plan_type, callback_url)
    
    if not payment_result['success']:
        await update.message.reply_text(
            f"❌ *Payment Error:* {payment_result.get('error', 'Unknown error')}",
            parse_mode='Markdown'
        )
        return
    
    # Save payment to database
    db.create_payment(
        user_id=user_id,
        plan_type=plan_type,
        amount=plan['price'],
        oxapay_invoice_id=payment_result['invoice_id']
    )
    
    payment_text = f"""
╔═══════════════════════════════════════╗
║       💳 PAYMENT CREATED 💳            ║
╚═══════════════════════════════════════╝

┌─ PLAN DETAILS ───────────────────────┐
│ Plan: `{plan['name']:<27}` │
│ Price: `${plan['price']:<26}` │
│ Requests: `{plan['requests']:<23}` │
│ Duration: `{plan['duration_days']} days` │
└──────────────────────────────────────┘

┌─ PAYMENT INFO ────────────────────────┐
│ Payment ID:                           │
│ `{payment_result['invoice_id']}`      │
└──────────────────────────────────────┘

💳 Click below to complete payment
    """
    
    keyboard = [
        [InlineKeyboardButton("💳 Pay with Crypto", url=payment_result['invoice_url'])],
        [
            InlineKeyboardButton("🔄 Check Payment", callback_data=f"check_payment_{payment_result['invoice_id']}"),
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        payment_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    logger.info(f"Button callback received: {data} from user {user_id}")
    
    # Handle interactive pause callbacks (Phase 3)
    if data.startswith("pause_"):
        try:
            # Find the correct pause_id by checking all pending pauses
            pause_id = None
            matching_key = None
            
            # Look for pending pause in context
            for key in list(context.user_data.keys()):
                if key.startswith('pending_pause_') and isinstance(context.user_data[key], dict):
                    pause_data = context.user_data[key]
                    stored_question_type = pause_data.get('question_type', '')
                    
                    # Match based on question type in callback data
                    # e.g., "pause_yes_resources" matches "has_resources"
                    if stored_question_type and stored_question_type in data:
                        pause_id = pause_data.get('pause_id')
                        matching_key = key
                        break
            
            if pause_id:
                # Store response directly in context for pause_and_ask_user to pick up
                # The pause_and_ask_user is polling context, not the handler instance
                if 'pending_pause_responses' not in context.user_data:
                    context.user_data['pending_pause_responses'] = {}
                context.user_data['pending_pause_responses'][pause_id] = data
                
                # Also try to use the handler if available (for compatibility)
                try:
                    from interactive_pause_handler import InteractivePauseHandler
                    pause_handler = InteractivePauseHandler()
                    pause_handler.handle_user_response(pause_id, data)
                except:
                    pass  # Fallback to context storage
                
                await query.answer("✅ Response recorded!", show_alert=False)
                logger.info(f"Successfully stored pause response: {data} for pause_id: {pause_id}")
            else:
                # Store response in context for later retrieval (fallback)
                if 'pending_pause_responses' not in context.user_data:
                    context.user_data['pending_pause_responses'] = {}
                # Try to match by question type
                if 'has_resources' in data:
                    # Find any pending resource pause
                    for key in list(context.user_data.keys()):
                        if key.startswith('pending_pause_') and isinstance(context.user_data[key], dict):
                            pause_data = context.user_data[key]
                            if pause_data.get('question_type') == 'has_resources':
                                pause_id = pause_data.get('pause_id')
                                context.user_data['pending_pause_responses'][pause_id] = data
                                await query.answer("✅ Response recorded!", show_alert=False)
                                logger.info(f"Matched resource pause by type: {pause_id}")
                                return
                
                context.user_data['pending_pause_responses'][data] = True
                await query.answer("✅ Response recorded!", show_alert=False)
                logger.warning(f"No pause_id found for callback: {data}, stored in context")
        except Exception as e:
            logger.error(f"Error handling pause callback: {e}", exc_info=True)
            await query.answer("❌ Error processing response", show_alert=True)
        return
    
    # Handle preference callbacks (Phase 5)
    if data.startswith("pref_"):
        try:
            if data == "pref_yes_personal":
                await query.answer("Please send your methods/resources", show_alert=False)
                await query.message.reply_text(
                    "📚 **Personal Methods/Resources**\n\n"
                    "Please send me your methods/resources and I'll learn and apply them.\n\n"
                    "You can send:\n"
                    "- Text descriptions\n"
                    "- Code files\n"
                    "- Configuration files\n"
                    "- Any relevant resources",
                    parse_mode='Markdown'
                )
                # Store in context
                if hasattr(context, 'user_data'):
                    context.user_data[f'waiting_personal_methods_{user_id}'] = True
            elif data == "pref_retry":
                await query.answer("Retrying with different approach...", show_alert=False)
                # Trigger retry logic
            elif data == "pref_accept":
                await query.answer("Accepting current results", show_alert=False)
        except Exception as e:
            logger.error(f"Error handling preference callback: {e}")
        return
    
    # Handle plan approval callbacks (Explicit Planning Phase - Cursor-style)
    if data.startswith("execute_plan_") or data.startswith("cancel_plan_"):
        try:
            # Parse callback data: execute_plan_{user_id}_{plan_id} or cancel_plan_{user_id}_{plan_id}
            parts = data.split("_")
            if len(parts) >= 4:
                action = parts[0]  # "execute" or "cancel"
                user_id_from_data = int(parts[2])
                plan_id = "_".join(parts[3:])  # plan_id might contain underscores
                
                if user_id_from_data == user_id:
                    plan_key = f'plan_approval_pending_{plan_id}'
                    
                    if action == "execute":
                        # User approved plan - trigger execution immediately
                        if hasattr(context, 'user_data') and plan_key in context.user_data:
                            plan_info = context.user_data[plan_key]
                            original_message = plan_info.get('message', '')
                            
                            # Mark plan as approved
                            context.user_data['plan_approved'] = True
                            context.user_data['approved_plan_id'] = plan_id
                            context.user_data['approved_plan_data'] = plan_info
                            context.user_data['waiting_plan_approval'] = False
                            context.user_data['execute_approved_plan'] = True
                            
                            await query.answer("✅ Plan approved! Executing...", show_alert=False)
                            await query.message.reply_text(
                                "✅ **Plan Approved**\n\nExecuting plan now...",
                                parse_mode='Markdown'
                            )
                            
                            # Trigger execution directly by calling handle_with_streaming with approved plan
                            try:
                                from desktop_ai_handler import DesktopAIHandler
                                from brain import get_brain
                                import os
                                
                                # Get workspace root
                                workspace = os.getenv('WORKSPACE_ROOT', os.getcwd())
                                
                                # Create handler instance
                                brain = get_brain()
                                handler = DesktopAIHandler(brain, workspace_root=workspace, user_id=user_id)
                                
                                # Set approved plan flag in context
                                context.user_data['execute_approved_plan'] = True
                                context.user_data['approved_plan_message'] = original_message
                                
                                # Create a synthetic update for execution
                                # We'll use the query's message as the base
                                class SyntheticUpdate:
                                    def __init__(self, original_query):
                                        self.effective_user = original_query.from_user
                                        self.effective_chat = original_query.message.chat
                                        self.message = type('Message', (), {
                                            'text': original_message,
                                            'reply_text': original_query.message.reply_text,
                                            'reply_document': original_query.message.reply_document,
                                            'chat': original_query.message.chat,
                                            'from_user': original_query.from_user
                                        })()
                                
                                synthetic_update = SyntheticUpdate(query)
                                
                                # Call handle_with_streaming with approved plan flag set
                                logger.info(f"Triggering execution for approved plan {plan_id}")
                                import asyncio
                                asyncio.create_task(
                                    handler.handle_with_streaming(original_message, synthetic_update, context)
                                )
                                
                            except Exception as e:
                                logger.error(f"Error triggering plan execution: {e}", exc_info=True)
                                # Fallback: set flag and inform user to send message
                                await query.message.reply_text(
                                    "⚠️ **Execution Trigger Error**\n\n"
                                    "Please send your message again to execute the approved plan.",
                                    parse_mode='Markdown'
                                )
                        else:
                            await query.answer("❌ Plan not found or expired", show_alert=True)
                    elif action == "cancel":
                        # User cancelled plan
                        if hasattr(context, 'user_data'):
                            if plan_key in context.user_data:
                                del context.user_data[plan_key]
                            context.user_data['plan_cancelled'] = True
                            context.user_data['waiting_plan_approval'] = False
                        
                        await query.answer("❌ Plan cancelled", show_alert=True)
                        await query.message.reply_text(
                            "❌ **Plan Cancelled**\n\nExecution aborted.",
                            parse_mode='Markdown'
                        )
                        logger.info(f"Plan {plan_id} cancelled by user {user_id}")
        except Exception as e:
            logger.error(f"Error handling plan approval callback: {e}", exc_info=True)
            await query.answer("❌ Error processing plan approval", show_alert=True)
        return
    
    # Handle task continuation callbacks (Phase 1)
    if data.startswith("continue_task_") or data.startswith("stop_task_"):
        user_id_from_data = int(data.split("_")[-1])
        if user_id_from_data == user_id:
            if "continue" in data:
                await query.answer("Continuing task...", show_alert=False)
                # Task will continue automatically
            else:
                await query.answer("Stopping task...", show_alert=True)
                # Mark task as stopped
                if hasattr(context, 'user_data'):
                    context.user_data[f'task_stopped_{user_id}'] = True
        return
    
    # Handle mode switching
    if data.startswith("mode_switch_"):
        mode = data.replace("mode_switch_", "")
        if mode in MODES:
            set_user_mode(user_id, mode, context)
            mode_label = MODES[mode]
            await query.answer(f"Mode switched to {mode_label}", show_alert=False)
            
            # Update the keyboard on the current message
            try:
                current_text = query.message.text or query.message.caption or ""
                # Get additional buttons if they exist
                additional_buttons = None
                if query.message.reply_markup and query.message.reply_markup.inline_keyboard:
                    # Preserve existing buttons (skip mode row if it exists)
                    existing_keyboard = query.message.reply_markup.inline_keyboard
                    # Filter out mode buttons row (first row if it has mode buttons)
                    if existing_keyboard and len(existing_keyboard) > 0:
                        first_row = existing_keyboard[0]
                        if first_row and any(btn.callback_data and btn.callback_data.startswith("mode_switch_") for btn in first_row):
                            # Keep all rows except the first (mode buttons) row
                            additional_buttons = existing_keyboard[1:] if len(existing_keyboard) > 1 else []
                        else:
                            # No mode buttons found, keep all rows
                            additional_buttons = existing_keyboard
                
                # Ensure additional_buttons is a list of lists (list of rows)
                if additional_buttons is not None and len(additional_buttons) > 0:
                    # Verify it's a list of lists
                    if not isinstance(additional_buttons[0], list):
                        additional_buttons = [additional_buttons] if additional_buttons else []
                
                reply_markup = create_mode_keyboard(user_id, context, additional_buttons)
                await query.edit_message_reply_markup(reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Error updating mode keyboard: {e}", exc_info=True)
        return
    
    # Handle scan results callbacks
    if data.startswith("scan_results_"):
        result_type = data.replace("scan_results_", "").split("_", 1)
        if len(result_type) == 2:
            section = result_type[0]  # summary, vulns, exploits, tools, full, download
            scan_id = result_type[1]
            
            # Get scan results from context
            scan_key = f'scan_results_{scan_id}'
            if context.user_data and scan_key in context.user_data:
                scan_data = context.user_data[scan_key]
                formatted_sections = scan_data.get('formatted_sections', {})
                target_url = scan_data.get('target', 'Unknown')
                
                try:
                    if section == 'summary':
                        text = formatted_sections.get('summary', 'Summary not available')
                        await query.answer("Showing summary...")
                    elif section == 'vulns':
                        text = formatted_sections.get('vulnerabilities', 'Vulnerabilities section not available')
                        await query.answer("Showing vulnerabilities...")
                    elif section == 'exploits':
                        text = formatted_sections.get('exploits', 'Exploits section not available')
                        await query.answer("Showing exploits...")
                    elif section == 'tools':
                        text = formatted_sections.get('tools', 'Tools section not available')
                        await query.answer("Showing tools...")
                    elif section == 'full':
                        text = formatted_sections.get('full_report', 'Full report not available')
                        # Split if too long
                        if len(text) > 4000:
                            chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
                            for i, chunk in enumerate(chunks):
                                if i == 0:
                                    await query.edit_message_text(chunk[:4000], parse_mode='Markdown')
                                else:
                                    await query.message.reply_text(chunk[:4000], parse_mode='Markdown')
                            return
                        await query.answer("Showing full report...")
                    elif section == 'download':
                        report_path = scan_data.get('report_path')
                        if report_path and Path(report_path).exists():
                            try:
                                with open(report_path, 'rb') as f:
                                    await query.message.reply_document(
                                        document=f,
                                        filename=Path(report_path).name,
                                        caption=f"📄 **Scan Report**\n\nTarget: {target_url}"
                                    )
                                await query.answer("Report sent!")
                                return
                            except Exception as e:
                                logger.error(f"Error sending report file: {e}")
                                await query.answer("Error sending report file", show_alert=True)
                                return
                        else:
                            await query.answer("Report file not available", show_alert=True)
                            return
                    else:
                        await query.answer("Unknown section", show_alert=True)
                        return
                    
                    # Get keyboard for this section
                    keyboard = create_scan_results_keyboard(scan_id, user_id, context)
                    
                    # Edit message with section content
                    if len(text) > 4000:
                        # Split into chunks
                        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
                        for i, chunk in enumerate(chunks):
                            chunk_keyboard = keyboard if i == len(chunks) - 1 else None
                            if i == 0:
                                await query.edit_message_text(chunk[:4000], parse_mode='Markdown', reply_markup=chunk_keyboard)
                            else:
                                await query.message.reply_text(chunk[:4000], parse_mode='Markdown', reply_markup=chunk_keyboard)
                    else:
                        await query.edit_message_text(text[:4000], parse_mode='Markdown', reply_markup=keyboard)
                except Exception as e:
                    logger.error(f"Error handling scan result callback: {e}", exc_info=True)
                    await query.answer(f"Error: {str(e)[:50]}", show_alert=True)
            else:
                await query.answer("Scan results not found or expired", show_alert=True)
        return
    
    # Handle plan approval/cancellation
    if data.startswith("approve_plan_"):
        message_id = data.replace("approve_plan_", "")
        pending_key = f'pending_plan_{user_id}'
        if context.user_data and pending_key in context.user_data:
            plan_data = context.user_data[pending_key]
            original_message = plan_data.get('original_message')
            # Proceed with execution
            await query.answer("✅ Plan approved! Executing...", show_alert=False)
            await query.edit_message_text(
                f"✅ **Plan Approved**\n\nExecuting plan...\n\n{plan_data.get('plan_text', '')[:3000]}",
                parse_mode='Markdown',
                reply_markup=create_mode_keyboard(user_id, context)
            )
            # Trigger execution (this will be handled by the main flow)
            context.user_data[f'approved_plan_{message_id}'] = True
            del context.user_data[pending_key]
        else:
            await query.answer("❌ Plan not found or expired", show_alert=True)
        return
    
    if data.startswith("cancel_plan_"):
        message_id = data.replace("cancel_plan_", "")
        pending_key = f'pending_plan_{user_id}'
        if context.user_data and pending_key in context.user_data:
            del context.user_data[pending_key]
        await query.answer("❌ Plan cancelled", show_alert=False)
        await query.edit_message_text(
            "❌ **Plan Cancelled**\n\nExecution stopped.",
            parse_mode='Markdown',
            reply_markup=create_mode_keyboard(user_id, context)
        )
        return
    
    # Don't answer immediately - let each handler answer with appropriate message
    # This allows error alerts to be shown properly
    
    # Handle enhancement callbacks
    if data.startswith("enhance_") or data == "analyze_code":
        await handle_enhancement_request(query, data, user_id, context)
        return
    
    # Handle dashboard callbacks FIRST (lazy import to avoid circular dependency)
    if data.startswith("dashboard_") or data.startswith("admin_") or \
       data.startswith("terminal_") or data.startswith("toolkit_") or \
       data.startswith("extensions_") or data.startswith("git_") or \
       data.startswith("settings_") or data.startswith("fix_") or \
       data.startswith("bulk_duration_") or data.startswith("bulk_confirm_"):
        from dashboard_features import handle_dashboard_callback
        await handle_dashboard_callback(query, data, user_id)
        return
    
    # Menu navigation
    # Answer callback for menu items (no alert needed)
    if data in ["menu_home", "menu_status", "menu_plans", "menu_referral", "menu_new", "menu_help", "menu_subscribe"]:
        try:
            await query.answer()
        except:
            pass
    
    if data == "menu_home":
        # Get user stats
        stats = db.get_user_usage_stats(user_id)
        plan_type = stats.get('plan_type', 'free')
        remaining = stats.get('remaining', 0)
        requests_limit = stats.get('requests_limit', 3)
        today_usage = stats.get('today_usage', 0)
        is_admin_user = stats.get('is_admin', False)
        
        # Format for display
        if is_admin_user or requests_limit == float('inf'):
            plan_display = "ADMIN"
            requests_display = "Unlimited"
            today_display = f"{today_usage} (Tracked)"
        else:
            plan_display = plan_type.upper()
            requests_display = f"{remaining}/{requests_limit}"
            today_display = f"{today_usage}/3"
        
        welcome_message = f"""
╔═══════════════════════════════════════╗
║   🔥 SMG-FORCER AI FRAMEWORK 🔥      ║
╚═══════════════════════════════════════╝

┌─ SYSTEM STATUS ─────────────────────┐
│ STATUS: ✅ ACTIVE                    │
│ PROTOCOL: FORCE ENABLED              │
│ MODE: UNRESTRICTED                   │
└──────────────────────────────────────┘

┌─ YOUR ACCOUNT ──────────────────────┐
│ Plan Type: `{plan_display:<20}` │
│ Requests: `{requests_display:<20}` │
│ Today: `{today_display:<22}` │
└──────────────────────────────────────┘
        """
        
        # Show expiration for upgraded users
        if stats.get('is_premium') and 'end_date' in stats:
            from datetime import datetime, timezone
            try:
                end_date_str = stats['end_date']
                if isinstance(end_date_str, str):
                    if 'Z' in end_date_str or '+' in end_date_str:
                        end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                    else:
                        end_date = datetime.strptime(end_date_str, '%Y-%m-%d %H:%M:%S')
                else:
                    end_date = end_date_str
                
                now = datetime.now(timezone.utc) if end_date.tzinfo else datetime.now()
                if end_date.tzinfo:
                    now = datetime.now(timezone.utc)
                else:
                    now = datetime.now()
                
                time_remaining = end_date - now
                
                if time_remaining.total_seconds() > 0:
                    days = time_remaining.days
                    hours, remainder = divmod(time_remaining.seconds, 3600)
                    minutes, _ = divmod(remainder, 60)
                    
                    if days > 0:
                        time_left = f"{days}d {hours}h {minutes}m"
                    elif hours > 0:
                        time_left = f"{hours}h {minutes}m"
                    else:
                        time_left = f"{minutes}m"
                    
                    welcome_message += f"\n┌─ UPGRADE EXPIRES ────────────────────┐\n"
                    welcome_message += f"│ Expires: `{end_date.strftime('%Y-%m-%d %H:%M'):<22}` │\n"
                    welcome_message += f"│ Time Left: `{time_left:<21}` │\n"
                    welcome_message += f"└──────────────────────────────────────┘"
            except:
                pass
        
        welcome_message += "\n\n💬 *Ready to chat!* Just send a message."
        keyboard = [
            [
                InlineKeyboardButton("📊 My Status", callback_data="menu_status"),
                InlineKeyboardButton("💎 Plans", callback_data="menu_plans")
            ],
            [
                InlineKeyboardButton("🎁 Referral", callback_data="menu_referral"),
                InlineKeyboardButton("🆕 New Chat", callback_data="menu_new")
            ],
            [
                InlineKeyboardButton("🖥️ Dashboard", callback_data="dashboard_menu"),
                InlineKeyboardButton("❓ Help", callback_data="menu_help")
            ],
            [
                InlineKeyboardButton("💳 Subscribe", callback_data="menu_subscribe")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(welcome_message, parse_mode='Markdown', reply_markup=reply_markup)
        return
    
    elif data == "menu_status":
        stats = db.get_user_usage_stats(user_id)
        plan_type = stats.get('plan_type', 'free')
        status = stats.get('status', 'active')
        requests_used = stats.get('requests_used', 0)
        requests_limit = stats.get('requests_limit', 4)
        remaining = stats.get('remaining', 0)
        today_usage = stats.get('today_usage', 0)
        is_admin_user = stats.get('is_admin', False)
        
        # Format for display
        if is_admin_user or requests_limit == float('inf'):
            limit_display = "Unlimited"
            remaining_display = "Unlimited"
            plan_display = "ADMIN" if is_admin_user else plan_type.upper()
        else:
            limit_display = f"{requests_used}/{requests_limit}"
            remaining_display = str(remaining)
            plan_display = plan_type.upper()
        
        status_text = f"""
╔═══════════════════════════════════════╗
║        📊 ACCOUNT STATUS 📊           ║
╚═══════════════════════════════════════╝

┌─ SUBSCRIPTION INFO ──────────────────┐
│ Plan: `{plan_display:<25}` │
│ Status: `{status.upper():<23}` │
└──────────────────────────────────────┘

┌─ USAGE STATISTICS ───────────────────┐
│ Used: `{limit_display:<25}` │
│ Remaining: `{remaining_display:<22}` │
│ Today: `{today_usage}` requests        │
└──────────────────────────────────────┘
        """
        
        # Always show expiration for premium/temp plans
        if stats.get('is_premium') and 'end_date' in stats:
            from datetime import datetime, timezone
            try:
                # Parse end_date (handle different formats)
                end_date_str = stats['end_date']
                if isinstance(end_date_str, str):
                    # Try parsing with timezone
                    if 'Z' in end_date_str or '+' in end_date_str:
                        end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                    else:
                        # SQLite datetime format
                        end_date = datetime.strptime(end_date_str, '%Y-%m-%d %H:%M:%S')
                else:
                    end_date = end_date_str
                
                # Calculate time remaining
                now = datetime.now(timezone.utc) if end_date.tzinfo else datetime.now()
                if end_date.tzinfo:
                    now = datetime.now(timezone.utc)
                else:
                    now = datetime.now()
                
                time_remaining = end_date - now
                
                if time_remaining.total_seconds() > 0:
                    # Format time remaining
                    days = time_remaining.days
                    hours, remainder = divmod(time_remaining.seconds, 3600)
                    minutes, _ = divmod(remainder, 60)
                    
                    if days > 0:
                        time_left = f"{days}d {hours}h {minutes}m"
                    elif hours > 0:
                        time_left = f"{hours}h {minutes}m"
                    else:
                        time_left = f"{minutes}m"
                    
                    status_text += f"\n┌─ EXPIRATION INFO ─────────────────────┐\n"
                    status_text += f"│ Expires: `{end_date.strftime('%Y-%m-%d %H:%M'):<22}` │\n"
                    status_text += f"│ Time Left: `{time_left:<21}` │\n"
                    status_text += f"└──────────────────────────────────────┘"
                else:
                    # Already expired
                    status_text += f"\n┌─ EXPIRATION INFO ─────────────────────┐\n"
                    status_text += f"│ Status: `EXPIRED`                      │\n"
                    status_text += f"│ Expired: `{end_date.strftime('%Y-%m-%d %H:%M'):<22}` │\n"
                    status_text += f"└──────────────────────────────────────┘"
            except Exception as e:
                # Fallback if date parsing fails
                status_text += f"\n┌─ EXPIRATION INFO ─────────────────────┐\n"
                status_text += f"│ Expires: `{str(stats['end_date']):<22}` │\n"
                status_text += f"└──────────────────────────────────────┘"
        
        keyboard = []
        if not stats['is_premium']:
            keyboard.append([InlineKeyboardButton("💎 Upgrade Now", callback_data="menu_plans")])
        keyboard.append([
            InlineKeyboardButton("🆕 New Chat", callback_data="menu_new"),
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(status_text, parse_mode='Markdown', reply_markup=reply_markup)
        return
    
    elif data == "menu_plans":
        plans_text = """
╔═══════════════════════════════════════╗
║      💎 SUBSCRIPTION PLANS 💎         ║
╚═══════════════════════════════════════╝

┌─ 🆓 FREE TIER ───────────────────────┐
│ • Requests: 3 (one-time, no refresh) │
│ • Expiration: Never                  │
│ • Perfect for testing                 │
│ • Price: FREE                         │
└──────────────────────────────────────┘

┌─ 🧪 TEST PLAN - $15 ─────────────────┐
│ • Requests: 100 total                │
│ • Duration: 7 days                   │
│ • Great for trying features           │
│ • Price: $15 USD                      │
└──────────────────────────────────────┘

┌─ ⭐ PREMIUM PLAN - $100 ──────────────┐
│ • Requests: 1,500 total             │
│ • Duration: 30 days                 │
│ • Best value for power users         │
│ • Price: $100 USD                    │
└──────────────────────────────────────┘

💳 Use `/subscribe <plan>` to purchase
        """
        keyboard = [
            [
                InlineKeyboardButton("🧪 Test Plan - $15", callback_data="plan_test"),
                InlineKeyboardButton("⭐ Premium - $100", callback_data="plan_premium")
            ],
            [
                InlineKeyboardButton("📊 My Status", callback_data="menu_status"),
                InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(plans_text, parse_mode='Markdown', reply_markup=reply_markup)
        return
    
    elif data == "menu_referral":
        referral_code = db.get_referral_code(user_id)
        ref_stats = db.get_referral_stats(user_id)
        bot_username = context.bot.username if hasattr(context.bot, 'username') else "your_bot"
        referral_link = f"https://t.me/{bot_username}?start=ref_{referral_code}"
        
        total_refs = ref_stats.get('total_referrals', 0)
        earned = total_refs * 20
        
        referral_text = f"""
╔═══════════════════════════════════════╗
║      🎁 REFERRAL PROGRAM 🎁           ║
╚═══════════════════════════════════════╝

┌─ YOUR REFERRAL CODE ─────────────────┐
│ `{referral_code}`                     │
└──────────────────────────────────────┘

┌─ YOUR STATISTICS ────────────────────┐
│ Total Referrals: `{total_refs:<18}` │
│ Free Requests Earned: `{earned:<12}` │
└──────────────────────────────────────┘

┌─ HOW IT WORKS ────────────────────────┐
│ 1. Share your referral link          │
│ 2. When someone subscribes →         │
│    You get 20 FREE requests!          │
│ 3. Rewards added automatically       │
│ 4. Unlimited referrals = Unlimited!   │
└──────────────────────────────────────┘
        """
        keyboard = [
            [InlineKeyboardButton("📤 Share Referral Link", url=f"https://t.me/share/url?url={referral_link}&text=Join%20SMG-Forcer%20AI%20Bot!")],
            [
                InlineKeyboardButton("📋 Copy Code", callback_data=f"copy_code_{referral_code}"),
                InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(referral_text, parse_mode='Markdown', reply_markup=reply_markup)
        return
    
    elif data == "menu_new":
        if user_id in user_sessions:
            user_sessions[user_id].reset()
        await query.answer("✅ Memory wiped. New session started!", show_alert=True)
        return
    
    elif data == "menu_help":
        help_text = """
╔═══════════════════════════════════════╗
║        📖 COMMAND REFERENCE           ║
╚═══════════════════════════════════════╝

┌─ BASIC COMMANDS ────────────────────┐
│ /start  → Initialize system          │
│ /help   → Show this reference        │
│ /new    → Reset conversation         │
│ /status → Check account status       │
└──────────────────────────────────────┘

┌─ SUBSCRIPTION ───────────────────────┐
│ /plans      → View all plans         │
│ /subscribe  → Purchase subscription   │
└──────────────────────────────────────┘

┌─ REFERRAL SYSTEM ────────────────────┐
│ /referral  → Get your referral code  │
│             Earn 20 free requests!    │
└──────────────────────────────────────┘

┌─ USAGE ──────────────────────────────┐
│ Just send any message to chat!       │
│                                       │
│ Free: 3 requests (one-time)          │
│ Premium: Unlimited requests           │
└──────────────────────────────────────┘
        """
        keyboard = [
            [
                InlineKeyboardButton("💎 View Plans", callback_data="menu_plans"),
                InlineKeyboardButton("📊 My Status", callback_data="menu_status")
            ],
            [
                InlineKeyboardButton("🎁 Referral Code", callback_data="menu_referral"),
                InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
            ]
        ]
        keyboard.append(get_support_button_row())
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(help_text, parse_mode='Markdown', reply_markup=reply_markup)
        return
    
    elif data == "menu_subscribe":
        await query.answer("Redirecting to plans...")
        # Trigger plans menu
        plans_text = """
╔═══════════════════════════════════════╗
║      💎 SUBSCRIPTION PLANS 💎         ║
╚═══════════════════════════════════════╝

┌─ 🆓 FREE TIER ───────────────────────┐
│ • Requests: 3 (one-time, no refresh) │
│ • Expiration: Never                  │
│ • Perfect for testing                 │
│ • Price: FREE                         │
└──────────────────────────────────────┘

┌─ 🧪 TEST PLAN - $15 ─────────────────┐
│ • Requests: 100 total                │
│ • Duration: 7 days                   │
│ • Great for trying features           │
│ • Price: $15 USD                      │
└──────────────────────────────────────┘

┌─ ⭐ PREMIUM PLAN - $100 ──────────────┐
│ • Requests: 1,500 total             │
│ • Duration: 30 days                 │
│ • Best value for power users         │
│ • Price: $100 USD                    │
└──────────────────────────────────────┘

💳 Use `/subscribe <plan>` to purchase
        """
        keyboard = [
            [
                InlineKeyboardButton("🧪 Test Plan - $15", callback_data="plan_test"),
                InlineKeyboardButton("⭐ Premium - $100", callback_data="plan_premium")
            ],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(plans_text, parse_mode='Markdown', reply_markup=reply_markup)
        return
    
    elif data.startswith("copy_code_"):
        code = data.replace("copy_code_", "")
        await query.answer(f"Referral code: {code}\n\nShare this code with friends!", show_alert=True)
        return
    
    elif data.startswith("check_payment_"):
        invoice_id = data.replace("check_payment_", "")
        
        # First check if payment exists in database
        conn = db.get_connection()
        cursor = execute_db_query(conn, """
            SELECT status, plan_type, amount 
            FROM payments 
            WHERE oxapay_invoice_id = ?
        """, (invoice_id,))
        payment_record = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not payment_record:
            # Payment record doesn't exist - user needs to create payment first
            await query.answer(
                "⚠️ Please pay before you check status. Create a payment first using /subscribe or /plans.",
                show_alert=True
            )
            return
        
        # Verify payment with OxaPay
        payment_status = oxapay.verify_payment(invoice_id)
        
        if payment_status['success']:
            if payment_status['paid']:
                # Payment completed - check if subscription was activated
                # Try to complete payment in database (idempotent)
                result = db.complete_payment(invoice_id)
                
                if result:
                    await query.answer(
                        "✅ Payment completed! Your subscription has been activated. Check /status to see your new plan!",
                        show_alert=True
                    )
                    # Update the message to show success
                    await query.edit_message_text(
                        "╔═══════════════════════════════════════╗\n"
                        "║   ✅ PAYMENT COMPLETED ✅             ║\n"
                        "╚═══════════════════════════════════════╝\n\n"
                        "Your subscription has been activated successfully!\n\n"
                        "Use /status to check your new plan.",
                        parse_mode='Markdown'
                    )
                else:
                    await query.answer(
                        "✅ Payment completed! Subscription activation in progress...",
                        show_alert=True
                    )
            else:
                # Payment not yet completed
                status_msg = payment_status.get('status', 'pending')
                await query.answer(
                    "⚠️ Please pay before you check status. Complete the payment first, then check again.",
                    show_alert=True
                )
        else:
            error_msg = payment_status.get('error', 'Unknown error')
            await query.answer(
                f"❌ Error checking payment: {error_msg}",
                show_alert=True
            )
        return
    
    # Plan selection
    if data.startswith("plan_"):
        plan_type = data.split("_")[1]
        
        plan = PLANS[plan_type]
        # Get webhook URL from environment (Railway or local)
        railway_static = os.getenv('RAILWAY_STATIC_URL')
        railway_domain = os.getenv('RAILWAY_PUBLIC_DOMAIN')
        
        if railway_static:
            callback_url = f"{railway_static}/webhook/oxapay"
        elif railway_domain:
            callback_url = f"https://{railway_domain}/webhook/oxapay"
        else:
            # Fallback for local development
            callback_url = os.getenv('WEBHOOK_URL', 'https://your-domain.com/webhook/oxapay')
            logger.warning(f"Using fallback webhook URL: {callback_url}. Set RAILWAY_PUBLIC_DOMAIN or WEBHOOK_URL for production.")
        
        payment_result = oxapay.create_subscription_payment(user_id, plan_type, callback_url)
        
        if not payment_result['success']:
            await query.answer(f"❌ Error: {payment_result.get('error')}", show_alert=True)
            return
        
        db.create_payment(
            user_id=user_id,
            plan_type=plan_type,
            amount=plan['price'],
            oxapay_invoice_id=payment_result['invoice_id']
        )
        
        payment_text = f"""
╔═══════════════════════════════════════╗
║       💳 PAYMENT CREATED 💳            ║
╚═══════════════════════════════════════╝

┌─ PLAN DETAILS ───────────────────────┐
│ Plan: `{plan['name']:<27}` │
│ Price: `${plan['price']:<26}` │
│ Requests: `{plan['requests']:<23}` │
│ Duration: `{plan['duration_days']} days` │
└──────────────────────────────────────┘

┌─ PAYMENT INFO ────────────────────────┐
│ Payment ID:                           │
│ `{payment_result['invoice_id']}`      │
└──────────────────────────────────────┘

💳 Click below to complete payment
        """
        
        keyboard = [
            [InlineKeyboardButton("💳 Pay with Crypto", url=payment_result['invoice_url'])],
            [
                InlineKeyboardButton("🔄 Check Payment", callback_data=f"check_payment_{payment_result['invoice_id']}"),
                InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            payment_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return
    
    # Admin menu callbacks
    if data == "admin_upgrade_menu":
        if not db.is_admin(user_id):
            await query.answer("❌ Access Denied", show_alert=True)
            return
        
        upgrade_text = """
╔═══════════════════════════════════════╗
║     🔧 MANUAL USER UPGRADE 🔧         ║
╚═══════════════════════════════════════╝

┌─ UPGRADE OPTIONS ─────────────────────┐
│ 1. Click "View Users"                  │
│ 2. Select a user to upgrade            │
│ 3. Choose duration (10min/1day/7days)  │
└──────────────────────────────────────┘

┌─ DURATION OPTIONS ────────────────────┐
│ • 10 minutes - Quick test             │
│ • 1 day - Short-term access           │
│ • 7 days - Extended access            │
└──────────────────────────────────────┘

Or use command: /admin_upgrade USER_ID DURATION
        """
        
        keyboard = [
            [
                InlineKeyboardButton("👥 View Users", callback_data="admin_users")
            ],
            [
                InlineKeyboardButton("📋 Upgrade Help", callback_data="admin_upgrade_help")
            ],
            [
                InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard"),
                InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(upgrade_text, parse_mode='Markdown', reply_markup=reply_markup)
        return
    
    elif data == "admin_upgrade_help":
        if not db.is_admin(user_id):
            await query.answer("❌ Access Denied", show_alert=True)
            return
        
        help_text = """
╔═══════════════════════════════════════╗
║     📖 UPGRADE COMMAND HELP 📖         ║
╚═══════════════════════════════════════╝

┌─ COMMAND USAGE ───────────────────────┐
│ /admin_upgrade USER_ID DURATION       │
└──────────────────────────────────────┘

┌─ DURATION OPTIONS ────────────────────┐
│ • 10min - 10 minutes                 │
│ • 1day  - 1 day                      │
│ • 7days - 7 days                     │
└──────────────────────────────────────┘

┌─ EXAMPLES ────────────────────────────┐
│ /admin_upgrade 123456789 10min        │
│ /admin_upgrade 123456789 1day         │
│ /admin_upgrade 123456789 7days        │
└──────────────────────────────────────┘

┌─ BUTTON METHOD ───────────────────────┐
│ 1. Go to "View Users"                 │
│ 2. Click upgrade button next to user  │
│ 3. Choose duration (10min/1day/7days)  │
└──────────────────────────────────────┘
        """
        
        keyboard = [
            [
                InlineKeyboardButton("👥 View Users", callback_data="admin_users"),
                InlineKeyboardButton("🔧 Upgrade Menu", callback_data="admin_upgrade_menu")
            ],
            [
                InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard"),
                InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(help_text, parse_mode='Markdown', reply_markup=reply_markup)
        return
    
    elif data == "admin_users":
        if not db.is_admin(user_id):
            await query.answer("❌ Access Denied", show_alert=True)
            return
        
        # Get all users (increase limit to show more)
        users = db.get_all_users(limit=100)
        if not users:
            await query.answer("No users found", show_alert=True)
            return
        
        # Get total user count for accurate display
        stats = db.get_dashboard_stats()
        total_users = stats['total_users']
        displayed_count = len(users)
        
        users_text = "╔═══════════════════════════════════════╗\n"
        users_text += "║        👥 USER LIST 👥                 ║\n"
        users_text += "╚═══════════════════════════════════════╝\n\n"
        users_text += f"Total Users: {total_users}\n"
        users_text += f"Showing {displayed_count} of {total_users} users:\n\n"
        users_text += "Click on a user to upgrade them:\n\n"
        
        keyboard_rows = []
        # Show all users in text (list all, not just first 50)
        for user in users:  # Show ALL users in the text
            target_user_id = user['user_id']
            user_name = user.get('first_name', 'N/A') or f"User {target_user_id}"
            # Escape user name to prevent Markdown parsing errors
            user_name_escaped = escape_markdown(str(user_name))
            # Use code formatting for ID (already escaped by escape_markdown)
            users_text += f"• {user_name_escaped} (ID: {target_user_id})\n"
        
        # But only create buttons for first 50 (Telegram button limit)
        for user in users[:50]:  # Telegram has button limits, so show first 50
            target_user_id = user['user_id']
            user_name = user.get('first_name', 'N/A') or f"User {target_user_id}"
            
            # Add buttons for each user: View Status and Upgrade
            keyboard_rows.append([
                InlineKeyboardButton(
                    f"📊 Status {user_name[:12]}", 
                    callback_data=f"view_user_status_{target_user_id}"
                ),
                InlineKeyboardButton(
                    f"🔧 Upgrade", 
                    callback_data=f"select_user_{target_user_id}"
                )
            ])
        
        keyboard_rows.append([
            InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard"),
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
        ])
        reply_markup = InlineKeyboardMarkup(keyboard_rows)
        await safe_edit_message_text(query, users_text, parse_mode='Markdown', reply_markup=reply_markup)
        return
    
    # Handle view user status
    elif data.startswith("view_user_status_"):
        if not db.is_admin(user_id):
            await query.answer("❌ Access Denied", show_alert=True)
            return
        
        try:
            # Parse user ID
            target_user_id = int(data.replace("view_user_status_", ""))
            
            # Get user info
            conn = db.get_connection()
            cursor = execute_db_query(conn, "SELECT * FROM users WHERE user_id = ?", (target_user_id,))
            user = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if not user:
                await query.answer("❌ User not found", show_alert=True)
                return
            
            user = dict(user)
            user_name = user.get('first_name', 'N/A') or f"User {target_user_id}"
            # Escape user name to prevent Markdown parsing errors
            user_name_escaped = escape_markdown(str(user_name))
            
            # Get user stats
            stats = db.get_user_usage_stats(target_user_id)
            
            # Format plan type
            plan_type = stats.get('plan_type', 'free')
            if plan_type == 'free':
                plan_display = "🆓 FREE"
            elif plan_type.startswith('Temp'):
                plan_display = f"⏱️ {plan_type.upper()}"
            elif stats.get('is_admin'):
                plan_display = "👑 ADMIN"
            else:
                plan_display = f"💎 {plan_type.upper()}"
            
            # Format requests
            requests_limit = stats.get('requests_limit', 0)
            requests_used = stats.get('requests_used', 0)
            remaining = stats.get('remaining', 0)
            
            if requests_limit == float('inf') or requests_limit >= 999999:
                requests_display = "♾️ UNLIMITED"
                remaining_display = "♾️ UNLIMITED"
            else:
                requests_display = f"{requests_used}/{requests_limit}"
                remaining_display = f"{remaining}"
            
            # Format expiration
            end_date = stats.get('end_date')
            if end_date:
                try:
                    from datetime import datetime
                    if isinstance(end_date, str):
                        if 'Z' in end_date or '+' in end_date:
                            exp_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                        else:
                            exp_date = datetime.strptime(end_date, '%Y-%m-%d %H:%M:%S')
                    else:
                        exp_date = end_date
                    
                    now = datetime.now()
                    if exp_date.tzinfo:
                        now = datetime.now(exp_date.tzinfo)
                    
                    time_left = exp_date - now
                    if time_left.total_seconds() <= 0:
                        expires_display = "❌ EXPIRED"
                        time_left_display = "Expired"
                    else:
                        days = time_left.days
                        hours, remainder = divmod(time_left.seconds, 3600)
                        minutes, _ = divmod(remainder, 60)
                        
                        expires_display = exp_date.strftime('%Y-%m-%d %H:%M')
                        if days > 0:
                            time_left_display = f"{days}d {hours}h {minutes}m"
                        elif hours > 0:
                            time_left_display = f"{hours}h {minutes}m"
                        else:
                            time_left_display = f"{minutes}m"
                except:
                    expires_display = str(end_date)
                    time_left_display = "N/A"
            else:
                expires_display = "Never"
                time_left_display = "N/A"
            
            # Today's usage
            today_usage = stats.get('today_usage', 0)
            
            # Check if admin
            is_admin_user = stats.get('is_admin', False)
            admin_note = "\n│ Status: 👑 ADMIN (Unlimited Access)" if is_admin_user else ""
            
            # Check if user is blocked
            is_blocked = db.is_blocked(target_user_id)
            blocked_status = "\n│ Status: 🚫 BLOCKED" if is_blocked else ""
            
            status_text = f"""
╔═══════════════════════════════════════╗
║     📊 USER STATUS & PLAN 📊          ║
╚═══════════════════════════════════════╝

┌─ USER INFO ───────────────────────────┐
│ Name: {user_name_escaped:<27} │
│ User ID: {target_user_id}             │{admin_note}{blocked_status}
└──────────────────────────────────────┘

┌─ SUBSCRIPTION DETAILS ────────────────┐
│ Plan Type: {plan_display:<23} │
│ Requests Used: {requests_display:<19} │
│ Remaining: {remaining_display:<23} │
│ Today's Usage: {today_usage:<20} │
│ Expires: {expires_display:<24} │
│ Time Left: {time_left_display:<23} │
└──────────────────────────────────────┘
            """
            
            # Check if user is blocked
            is_blocked = db.is_blocked(target_user_id)
            block_button_text = "🔓 Unblock User" if is_blocked else "🚫 Block User"
            block_callback = f"unblock_user_{target_user_id}" if is_blocked else f"block_user_{target_user_id}"
            
            # Build keyboard - always show downgrade unless it's an admin
            keyboard = []
            
            # Upgrade and Downgrade buttons (don't show downgrade for admins)
            if not is_admin_user:
                keyboard.append([
                    InlineKeyboardButton("🔧 Upgrade User", callback_data=f"select_user_{target_user_id}"),
                    InlineKeyboardButton("⬇️ Downgrade User", callback_data=f"downgrade_user_{target_user_id}")
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton("🔧 Upgrade User", callback_data=f"select_user_{target_user_id}")
                ])
            
            # Block/Unblock button (don't show for admins)
            if not is_admin_user:
                keyboard.append([
                    InlineKeyboardButton(block_button_text, callback_data=block_callback)
                ])
            
            # Navigation buttons
            keyboard.append([
                InlineKeyboardButton("👥 Back to Users", callback_data="admin_users"),
                InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard")
            ])
            keyboard.append([
                InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
            ])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Answer callback to prevent timeout
            try:
                await query.answer()
            except:
                pass
            
            try:
                await safe_edit_message_text(query, status_text, parse_mode='Markdown', reply_markup=reply_markup)
            except Exception as edit_error:
                logger.error(f"Error editing message in view_user_status: {edit_error}", exc_info=True)
                # Try to send as new message if edit fails
                try:
                    await query.message.reply_text(status_text, parse_mode=None, reply_markup=reply_markup)
                except:
                    pass
            
        except ValueError:
            await query.answer("❌ Invalid user ID", show_alert=True)
        except Exception as e:
            logger.error(f"Error viewing user status: {e}", exc_info=True)
            await query.answer(f"❌ Error: {str(e)}", show_alert=True)
        return
    
    # Handle user selection for upgrade
    elif data.startswith("select_user_"):
        if not db.is_admin(user_id):
            await query.answer("❌ Access Denied", show_alert=True)
            return
        
        # Parse user ID
        target_user_id = int(data.replace("select_user_", ""))
        
        # Get user info
        conn = db.get_connection()
        try:
            from psycopg2.extras import RealDictCursor
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            # Use PostgreSQL syntax (%s) instead of SQLite (?)
            cursor.execute("SELECT * FROM users WHERE user_id = %s", (target_user_id,))
        except (ImportError, AttributeError):
            # Fallback for SQLite
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (target_user_id,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not user:
            await query.answer("❌ User not found", show_alert=True)
            return
        
        user = dict(user)  # Convert Row to dict
        user_name = user.get('first_name', 'N/A') or f"User {target_user_id}"
        
        # Show duration selection
        duration_text = f"""
╔═══════════════════════════════════════╗
║     🔧 UPGRADE USER 🔧                ║
╚═══════════════════════════════════════╝

┌─ SELECTED USER ──────────────────────┐
│ Name: {user_name:<27} │
│ User ID: `{target_user_id}`          │
└──────────────────────────────────────┘

┌─ SELECT DURATION ────────────────────┐
│ Choose upgrade duration:             │
│                                       │
│ • 10 minutes - Quick test            │
│ • 1 day - Short-term access          │
│ • 7 days - Extended access           │
└──────────────────────────────────────┘
        """
        
        keyboard = [
            [
                InlineKeyboardButton("⏱️ 10 Minutes", callback_data=f"select_duration_{target_user_id}_10min"),
                InlineKeyboardButton("📅 1 Day", callback_data=f"select_duration_{target_user_id}_1day")
            ],
            [
                InlineKeyboardButton("📆 7 Days", callback_data=f"select_duration_{target_user_id}_7days")
            ],
            [
                InlineKeyboardButton("👥 Back to Users", callback_data="admin_users"),
                InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(duration_text, parse_mode='Markdown', reply_markup=reply_markup)
        return
    
    # Handle duration selection - show request count options
    elif data.startswith("select_duration_"):
        if not db.is_admin(user_id):
            await query.answer("❌ Access Denied", show_alert=True)
            return
        
        # Parse: select_duration_USERID_DURATION or select_duration_USERID_DURATION_free
        parts = data.split("_")
        if len(parts) < 4:
            await query.answer("❌ Invalid request", show_alert=True)
            return
        
        is_free_upgrade = len(parts) > 4 and parts[4] == "free"
        
        try:
            target_user_id = int(parts[2])
            duration = parts[3]  # 10min, 1day, or 7days
            
            # Parse duration
            if duration == "10min":
                duration_minutes = 10
                duration_days = None
                duration_text = "10 minutes"
            elif duration == "1day":
                duration_minutes = None
                duration_days = 1
                duration_text = "1 day"
            elif duration == "7days":
                duration_minutes = None
                duration_days = 7
                duration_text = "7 days"
            else:
                await query.answer("❌ Invalid duration", show_alert=True)
                return
            
            # Get user info
            conn = db.get_connection()
            cursor = execute_db_query(conn, "SELECT * FROM users WHERE user_id = ?", (target_user_id,))
            user = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if not user:
                await query.answer("❌ User not found", show_alert=True)
                return
            
            user = dict(user)
            user_name = user.get('first_name', 'N/A') or f"User {target_user_id}"
            
            # Show request count selection (with free upgrade indicator)
            if is_free_upgrade:
                requests_text = f"""
╔═══════════════════════════════════════╗
║   🎁 FREE UPGRADE - SELECT REQUESTS 🎁  ║
╚═══════════════════════════════════════╝

┌─ USER INFO ──────────────────────────┐
│ Name: {user_name:<27} │
│ User ID: `{target_user_id}`          │
│ Duration: {duration_text}            │
│ Type: 🎁 FREE (Downtime Compensation) │
└──────────────────────────────────────┘

┌─ SELECT REQUEST COUNT ────────────────┐
│ Choose number of requests:            │
│                                       │
│ • 50 - Small compensation            │
│ • 100 - Medium compensation          │
│ • 500 - High compensation            │
│ • 1000 - Very high compensation      │
│ • Unlimited - No limit               │
└──────────────────────────────────────┘
                """
                free_suffix = "_free"
            else:
                requests_text = f"""
╔═══════════════════════════════════════╗
║     🔧 SELECT REQUEST COUNT 🔧         ║
╚═══════════════════════════════════════╝

┌─ USER INFO ──────────────────────────┐
│ Name: {user_name:<27} │
│ User ID: `{target_user_id}`          │
│ Duration: {duration_text}            │
└──────────────────────────────────────┘

┌─ SELECT REQUEST COUNT ────────────────┐
│ Choose number of requests:            │
│                                       │
│ • 50 - Small test                    │
│ • 100 - Medium usage                 │
│ • 500 - High usage                   │
│ • 1000 - Very high usage             │
│ • Unlimited - No limit               │
└──────────────────────────────────────┘
                """
                free_suffix = ""
            
            keyboard = [
                [
                    InlineKeyboardButton("50 Requests", callback_data=f"upgrade_{target_user_id}_{duration}_50{free_suffix}"),
                    InlineKeyboardButton("100 Requests", callback_data=f"upgrade_{target_user_id}_{duration}_100{free_suffix}")
                ],
                [
                    InlineKeyboardButton("500 Requests", callback_data=f"upgrade_{target_user_id}_{duration}_500{free_suffix}"),
                    InlineKeyboardButton("1000 Requests", callback_data=f"upgrade_{target_user_id}_{duration}_1000{free_suffix}")
                ],
                [
                    InlineKeyboardButton("♾️ Unlimited", callback_data=f"upgrade_{target_user_id}_{duration}_unlimited{free_suffix}")
                ],
                [
                    InlineKeyboardButton("✏️ Custom Amount", callback_data=f"custom_requests_{target_user_id}_{duration}{free_suffix}")
                ],
                [
                    InlineKeyboardButton("👥 Back to Users", callback_data="admin_users"),
                    InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(requests_text, parse_mode='Markdown', reply_markup=reply_markup)
            return
            
        except (ValueError, IndexError) as e:
            await query.answer("❌ Invalid request", show_alert=True)
            return
    
    # Handle custom request amount input
    elif data.startswith("custom_requests_"):
        if not db.is_admin(user_id):
            await query.answer("❌ Access Denied", show_alert=True)
            return
        
        # Parse: custom_requests_USERID_DURATION or custom_requests_USERID_DURATION_free
        parts = data.split("_")
        if len(parts) < 4:
            await query.answer("❌ Invalid request", show_alert=True)
            return
        
        is_free_upgrade = len(parts) > 4 and parts[4] == "free"
        
        try:
            target_user_id = int(parts[2])
            duration = parts[3]  # 10min, 1day, or 7days
            
            # Get user info
            conn = db.get_connection()
            cursor = execute_db_query(conn, "SELECT * FROM users WHERE user_id = ?", (target_user_id,))
            user = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if not user:
                await query.answer("❌ User not found", show_alert=True)
                return
            
            user = dict(user)
            user_name = user.get('first_name', 'N/A') or f"User {target_user_id}"
            
            # Parse duration for display
            if duration == "10min":
                duration_text = "10 minutes"
            elif duration == "1day":
                duration_text = "1 day"
            elif duration == "7days":
                duration_text = "7 days"
            else:
                duration_text = duration
            
            custom_text = f"""
╔═══════════════════════════════════════╗
║     ✏️ CUSTOM REQUEST AMOUNT ✏️        ║
╚═══════════════════════════════════════╝

┌─ USER INFO ──────────────────────────┐
│ Name: {user_name:<27} │
│ User ID: `{target_user_id}`          │
│ Duration: {duration_text}            │
└──────────────────────────────────────┘

┌─ ENTER CUSTOM AMOUNT ──────────────────┐
│ Please send a message with the number  │
│ of requests you want to give.          │
│                                         │
│ Examples:                               │
│ • 25 (for 25 requests)                 │
│ • 250 (for 250 requests)               │
│ • 5000 (for 5000 requests)             │
│                                         │
│ Minimum: 1 request                     │
│ Maximum: 999999 requests               │
└──────────────────────────────────────┘

💡 Send the number as a message (e.g., "250")
            """
            
            keyboard = [
                [
                    InlineKeyboardButton("👥 Back to Users", callback_data="admin_users"),
                    InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(custom_text, parse_mode='Markdown', reply_markup=reply_markup)
            
            # Store the pending upgrade in context for message handler
            context.user_data[f'pending_upgrade_{user_id}'] = {
                'target_user_id': target_user_id,
                'duration': duration,
                'user_name': user_name
            }
            
            await query.answer("💡 Now send a message with the number of requests (e.g., '250')", show_alert=True)
            return
            
        except (ValueError, IndexError) as e:
            await query.answer("❌ Invalid request", show_alert=True)
            return
    
    # Handle upgrade callbacks: upgrade_USERID_DURATION_REQUESTS
    elif data.startswith("upgrade_") and data != "admin_upgrade_menu":
        logger.info(f"Processing upgrade callback: {data} from user {user_id}")
        
        # Don't answer immediately - we'll answer with proper feedback
        # This allows us to show alerts properly
        
        if not db.is_admin(user_id):
            logger.warning(f"Non-admin user {user_id} tried to upgrade")
            try:
                await query.answer("❌ Access Denied", show_alert=True)
            except:
                pass
            return
        
        logger.info(f"Admin {user_id} confirmed, processing upgrade...")
        try:
            # Parse: upgrade_USERID_DURATION_REQUESTS
            # Format: upgrade_123456789_1day_100
            parts = data.split("_")
            logger.info(f"Upgrade callback data: {data}, parts: {parts}, len: {len(parts)}")
            
            if len(parts) < 4:
                logger.error(f"Invalid upgrade callback format: {data} (expected 4 parts, got {len(parts)})")
                await query.answer("❌ Invalid upgrade request format", show_alert=True)
                return
            
            target_user_id = int(parts[1])
            duration = parts[2]  # 10min, 1day, or 7days
            requests_str = parts[3]  # 50, 100, 500, 1000, or unlimited
            
            # Check if target user is an admin
            is_target_admin = db.is_admin(target_user_id)
            if is_target_admin:
                # Target user is an admin - show warning but allow upgrade for testing
                if target_user_id == user_id:
                    admin_notice = "\n\n⚠️ Note: You are an admin with unlimited access. This upgrade is for testing purposes only."
                else:
                    admin_notice = f"\n\n⚠️ Note: User {target_user_id} is an admin with unlimited access. This upgrade is for testing purposes only."
                
                # Show alert to admin performing the upgrade
                try:
                    await query.answer("⚠️ Target user is already an admin! Upgrade will still be applied for testing.", show_alert=True)
                except:
                    pass
            else:
                admin_notice = ""
            
            # Parse duration
            if duration == "10min":
                duration_minutes = 10
                duration_days = None
                duration_text = "10 minutes"
            elif duration == "1day":
                duration_minutes = None
                duration_days = 1
                duration_text = "1 day"
            elif duration == "7days":
                duration_minutes = None
                duration_days = 7
                duration_text = "7 days"
            else:
                await query.answer("❌ Invalid duration", show_alert=True)
                return
            
            # Parse request count
            if requests_str == "unlimited":
                requests_limit = 999999  # Effectively unlimited
                requests_text = "Unlimited"
            else:
                try:
                    requests_limit = int(requests_str)
                    requests_text = f"{requests_limit} requests"
                except ValueError:
                    await query.answer("❌ Invalid request count", show_alert=True)
                    return
            
            # Create temporary subscription
            logger.info(f"Creating subscription for user {target_user_id}: {requests_limit} requests, {duration_text}")
            try:
                sub_id = db.create_temporary_subscription(
                    target_user_id,
                    requests_limit=requests_limit,
                    duration_minutes=duration_minutes,
                    duration_days=duration_days
                )
                
                if not sub_id:
                    logger.error(f"create_temporary_subscription returned None for user {target_user_id}")
                    try:
                        await query.answer("❌ Failed to create subscription. Subscription ID is None.", show_alert=True)
                    except:
                        pass
                    return
                
                logger.info(f"Subscription created with ID: {sub_id} for user {target_user_id}")
            except Exception as create_error:
                logger.error(f"Exception creating subscription for user {target_user_id}: {create_error}", exc_info=True)
                try:
                    await query.answer(f"❌ Error creating subscription: {str(create_error)}", show_alert=True)
                except:
                    pass
                return
            
            # Get subscription details for notification
            sub = db.get_user_subscription(target_user_id)
            if not sub:
                logger.error(f"Subscription created (ID: {sub_id}) but not found when retrieving for user {target_user_id}")
                try:
                    await query.answer("❌ Subscription created but not found. Please check status.", show_alert=True)
                except:
                    pass
                return
            
            # Calculate expiration time
            from datetime import datetime, timezone
            try:
                end_date_str = sub['end_date']
                if isinstance(end_date_str, str):
                    if 'Z' in end_date_str or '+' in end_date_str:
                        end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                    else:
                        end_date = datetime.strptime(end_date_str, '%Y-%m-%d %H:%M:%S')
                else:
                    end_date = end_date_str
                
                expires_text = end_date.strftime('%Y-%m-%d %H:%M')
            except:
                expires_text = sub['end_date']
            
            # Show success alert - this is the first answer to the callback
            try:
                success_msg = f"✅ User {target_user_id} upgraded!\n{requests_text} for {duration_text}"
                if is_target_admin:
                    success_msg += "\n\n⚠️ User is an admin (unlimited access)"
                logger.info(f"Showing success alert: {success_msg}")
                await query.answer(success_msg, show_alert=True)
            except Exception as alert_error:
                logger.warning(f"Could not show alert: {alert_error}")
                # Try without alert
                try:
                    await query.answer("✅ Upgrade completed")
                except:
                    pass
            
            # Get user info for display
            conn = db.get_connection()
            cursor = execute_db_query(conn, "SELECT * FROM users WHERE user_id = ?", (target_user_id,))
            user = cursor.fetchone()
            cursor.close()
            conn.close()
            
            user_name = f"User {target_user_id}"
            if user:
                user = dict(user)
                user_name = user.get('first_name', 'N/A') or f"User {target_user_id}"
            
            # Send notification to upgraded user
            try:
                notification_text = f"""
╔═══════════════════════════════════════╗
║   🎉 ACCOUNT UPGRADED! 🎉              ║
╚═══════════════════════════════════════╝

┌─ UPGRADE DETAILS ────────────────────┐
│ Duration: {duration_text}             │
│ Requests: {requests_text}             │
│ Expires: {expires_text}              │
└──────────────────────────────────────┘

✅ Your account has been upgraded successfully!

📋 What's Next:
• Use /status to check your new plan
• Start using your upgraded requests
• Subscription will expire automatically

💡 Remember: This is a temporary upgrade.
   Make the most of it! 🚀
                """
                
                # Send notification to user
                try:
                    bot_instance = None
                    if context and getattr(context, "bot", None):
                        bot_instance = context.bot
                    elif hasattr(query, "bot") and query.bot:
                        bot_instance = query.bot
                    elif bot_application and getattr(bot_application, "bot", None):
                        bot_instance = bot_application.bot

                    if bot_instance:
                        await bot_instance.send_message(
                            chat_id=target_user_id,
                            text=notification_text,
                            parse_mode="Markdown"
                        )
                        logger.info(f"Sent upgrade notification to user {target_user_id}")
                    else:
                        logger.warning(f"Could not send notification to user {target_user_id}: No bot instance available")
                except Exception as send_error:
                    logger.error(f"Failed to send notification to user {target_user_id}: {send_error}", exc_info=True)
            except Exception as e:
                logger.error(f"Failed to send notification to user {target_user_id}: {e}")
            
            # Update message to show success
            success_text = f"""
╔═══════════════════════════════════════╗
║   ✅ USER UPGRADED SUCCESSFULLY ✅      ║
╚═══════════════════════════════════════╝

┌─ UPGRADE DETAILS ────────────────────┐
│ User: {user_name:<27} │
│ User ID: `{target_user_id}`          │
│ Duration: {duration_text}             │
│ Requests: {requests_text}             │
│ Expires: {expires_text}              │
└──────────────────────────────────────┘

✅ User has been upgraded!
📧 Notification sent to user.
Subscription will expire automatically.{admin_notice}
            """
            
            keyboard = [
                [
                    InlineKeyboardButton("👥 View Users", callback_data="admin_users"),
                    InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard")
                ],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(success_text, parse_mode='Markdown', reply_markup=reply_markup)
            
        except ValueError as e:
            logger.error(f"ValueError in upgrade callback: {e}, data: {data}", exc_info=True)
            try:
                await query.answer("❌ Invalid user ID or format", show_alert=True)
            except:
                try:
                    await query.answer()
                except:
                    pass
        except Exception as e:
            logger.error(f"Error upgrading user: {e}, data: {data}", exc_info=True)
            try:
                error_msg = str(e)[:200]  # Limit error message length
                await query.answer(f"❌ Error: {error_msg}", show_alert=True)
            except:
                try:
                    await query.answer()
                except:
                    pass
        return
    
    elif data == "admin_payments":
        if not db.is_admin(user_id):
            await query.answer("❌ Access Denied", show_alert=True)
            return
        
        try:
            # Answer the callback first
            await query.answer("Loading payments...")
            
            payments = db.get_all_payments(limit=50)
            
            payments_text = "╔═══════════════════════════════════════╗\n"
            payments_text += "║      💳 RECENT PAYMENTS 💳             ║\n"
            payments_text += "╚═══════════════════════════════════════╝\n\n"
            
            if not payments:
                payments_text += "No payments found yet.\n\n"
                payments_text += "Payments will appear here once users make purchases.\n"
            else:
                # Get statistics
                total_payments = len(payments)
                completed = sum(1 for p in payments if p.get('status') == 'completed')
                pending = sum(1 for p in payments if p.get('status') == 'pending')
                total_revenue = sum(float(p.get('amount', 0) or 0) for p in payments if p.get('status') == 'completed')
                
                payments_text += f"Total Payments: {total_payments}\n"
                payments_text += f"Completed: {completed} | Pending: {pending}\n"
                payments_text += f"Total Revenue: ${total_revenue:.2f} USD\n\n"
                # Limit to 10 payments to avoid message length issues (Telegram limit: 4096 chars)
                payments_text += f"Showing {min(len(payments), 10)} recent payments:\n\n"
                
                for payment in payments[:10]:
                    username = payment.get('username') or payment.get('first_name') or f"User {payment['user_id']}"
                    plan_type = str(payment.get('plan_type', 'N/A') or 'N/A')
                    amount = float(payment.get('amount', 0) or 0)
                    status = str(payment.get('status', 'unknown') or 'unknown')
                    created = payment.get('created_at', 'N/A')
                    
                    # Truncate username if too long
                    username_display = username[:28] if len(username) > 28 else username
                    
                    # Clean and truncate values for display
                    plan_type_display = plan_type[:24] if len(plan_type) > 24 else plan_type
                    status_display = status[:23] if len(status) > 23 else status
                    
                    # Format more concisely to avoid message length issues
                    payments_text += f"• {username_display[:20]}\n"
                    payments_text += f"  Plan: {plan_type_display[:15]} | ${amount:.2f} | {status_display[:10]}\n"
                    if created and created != 'N/A':
                        created_str = str(created)[:16] if len(str(created)) > 16 else str(created)
                        payments_text += f"  Date: {created_str}\n"
                    payments_text += "\n"
            
            keyboard = [
                [InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Telegram message limit is 4096 characters - truncate if needed
            if len(payments_text) > 4000:
                payments_text = payments_text[:3900] + "\n\n... (message truncated)"
            
            # Send without parse_mode to avoid Markdown parsing errors
            await query.edit_message_text(payments_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error showing payments: {e}", exc_info=True)
            error_msg = f"❌ Error loading payments: {str(e)}"
            try:
                await query.answer(error_msg, show_alert=True)
            except:
                pass
            # Try to send error message
            try:
                await query.message.reply_text(error_msg, parse_mode='Markdown')
            except:
                logger.error("Failed to send error message")
        return
    
    elif data == "admin_subs":
        if not db.is_admin(user_id):
            await query.answer("❌ Access Denied", show_alert=True)
            return
        
        subs = db.get_all_subscriptions(limit=20)
        if not subs:
            await query.answer("No subscriptions found", show_alert=True)
            return
        
        subs_text = "╔═══════════════════════════════════════╗\n"
        subs_text += "║    ⭐ ACTIVE SUBSCRIPTIONS ⭐          ║\n"
        subs_text += "╚═══════════════════════════════════════╝\n\n"
        subs_text += f"Showing {min(len(subs), 10)} of {len(subs)} subscriptions:\n\n"
        for sub in subs[:10]:
            username = sub.get('username') or f"User {sub['user_id']}"
            subs_text += f"┌─ {username[:28]:<28} ┐\n"
            subs_text += f"│ Plan: `{sub['plan_type']:<24}` │\n"
            subs_text += f"│ Used: `{sub['requests_used']}/{sub['requests_limit']:<20}` │\n"
            subs_text += f"│ Status: `{sub['status']:<23}` │\n"
            subs_text += "└──────────────────────────────────────┘\n\n"
        
        keyboard = [
            [InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(subs_text, reply_markup=reply_markup)
        return
    
    elif data == "admin_stats":
        if not db.is_admin(user_id):
            await query.answer("❌ Access Denied", show_alert=True)
            return
        
        try:
            stats = db.get_dashboard_stats()
            
            # Get additional statistics
            conn = db.get_connection()
            try:
                from psycopg2.extras import RealDictCursor
                cursor = conn.cursor(cursor_factory=RealDictCursor)
            except ImportError:
                # Fallback if not PostgreSQL
                cursor = conn.cursor()
            
            # This week's new users (PostgreSQL syntax)
            cursor.execute("""
                SELECT COUNT(*) as count FROM users 
                WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
            """)
            week_users = cursor.fetchone()['count']
            
            # This month's new users (PostgreSQL syntax)
            cursor.execute("""
                SELECT COUNT(*) as count FROM users 
                WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
            """)
            month_users = cursor.fetchone()['count']
            
            # Total payments count
            cursor.execute("SELECT COUNT(*) as count FROM payments")
            total_payments = cursor.fetchone()['count']
            
            # Completed payments count
            cursor.execute("SELECT COUNT(*) as count FROM payments WHERE status = 'completed'")
            completed_payments = cursor.fetchone()['count']
            
            # Pending payments count
            cursor.execute("SELECT COUNT(*) as count FROM payments WHERE status = 'pending'")
            pending_payments = cursor.fetchone()['count']
            
            # Total subscriptions count
            cursor.execute("SELECT COUNT(*) as count FROM subscriptions")
            total_subs = cursor.fetchone()['count']
            
            # Expired subscriptions (PostgreSQL syntax)
            cursor.execute("""
                SELECT COUNT(*) as count FROM subscriptions 
                WHERE status = 'expired' OR end_date <= NOW()
            """)
            expired_subs = cursor.fetchone()['count']
            
            cursor.close()
            conn.close()
            
            stats_text = f"""
╔═══════════════════════════════════════╗
║      📊 DETAILED STATISTICS 📊         ║
╚═══════════════════════════════════════╝

┌─ USER STATISTICS ────────────────────┐
│ Total Users: `{stats['total_users']:<22}` │
│ New Today: `{stats['today_new_users']:<24}` │
│ New This Week: `{week_users:<19}` │
│ New This Month: `{month_users:<18}` │
└──────────────────────────────────────┘

┌─ SUBSCRIPTIONS ──────────────────────┐
│ Active: `{stats['active_subscriptions']:<25}` │
│ Total: `{total_subs:<27}` │
│ Expired: `{expired_subs:<25}` │
└──────────────────────────────────────┘

┌─ PAYMENTS ───────────────────────────┐
│ Total: `{total_payments:<26}` │
│ Completed: `{completed_payments:<23}` │
│ Pending: `{pending_payments:<25}` │
└──────────────────────────────────────┘

┌─ REVENUE ────────────────────────────┐
│ Total Revenue: `${stats['total_revenue']:.2f}` USD │
└──────────────────────────────────────┘
            """
            
            keyboard = [
                [InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(stats_text, parse_mode='Markdown', reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error showing statistics: {e}", exc_info=True)
            error_msg = f"❌ Error: {str(e)[:100]}"  # Limit error message length
            await query.answer(error_msg, show_alert=True)
        return
    
    elif data == "admin_dashboard":
        if not db.is_admin(user_id):
            await query.answer("❌ Access Denied", show_alert=True)
            return
        
        try:
            stats = db.get_dashboard_stats()
            dashboard_text = f"""
╔═══════════════════════════════════════╗
║      📊 ADMIN DASHBOARD 📊            ║
╚═══════════════════════════════════════╝

┌─ USER STATISTICS ────────────────────┐
│ Total Users: `{stats['total_users']:<22}` │
│ New Today: `{stats['today_new_users']:<24}` │
│ Active Subs: `{stats['active_subscriptions']:<21}` │
└──────────────────────────────────────┘

┌─ REVENUE ────────────────────────────┐
│ Total Revenue: `${stats['total_revenue']:.2f}` USD │
└──────────────────────────────────────┘
            """
            keyboard = [
                [
                    InlineKeyboardButton("👥 View Users", callback_data="admin_users"),
                    InlineKeyboardButton("💳 Payments", callback_data="admin_payments")
                ],
                [
                    InlineKeyboardButton("⭐ Subscriptions", callback_data="admin_subs"),
                    InlineKeyboardButton("📊 Statistics", callback_data="admin_stats")
                ],
                [
                    InlineKeyboardButton("🔧 Upgrade Users", callback_data="admin_upgrade_menu")
                ],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(dashboard_text, parse_mode='Markdown', reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error showing dashboard: {e}", exc_info=True)
            await query.answer(f"❌ Error: {str(e)}", show_alert=True)
        return
    
    # Handle block user
    elif data.startswith("block_user_"):
        if not db.is_admin(user_id):
            await query.answer("❌ Access Denied", show_alert=True)
            return
        
        try:
            target_user_id = int(data.replace("block_user_", ""))
            
            # Don't allow blocking admins
            if db.is_admin(target_user_id):
                await query.answer("❌ Cannot block admin users", show_alert=True)
                return
            
            if db.block_user(target_user_id):
                await query.answer("✅ User blocked successfully", show_alert=True)
                logger.info(f"Admin {user_id} blocked user {target_user_id}")
                
                # Refresh the status view
                query.data = f"view_user_status_{target_user_id}"
                await button_callback(update, context)
            else:
                await query.answer("❌ Failed to block user", show_alert=True)
        except ValueError:
            await query.answer("❌ Invalid user ID", show_alert=True)
        except Exception as e:
            logger.error(f"Error blocking user: {e}", exc_info=True)
            await query.answer(f"❌ Error: {str(e)}", show_alert=True)
        return
    
    # Handle unblock user
    elif data.startswith("unblock_user_"):
        if not db.is_admin(user_id):
            await query.answer("❌ Access Denied", show_alert=True)
            return
        
        try:
            target_user_id = int(data.replace("unblock_user_", ""))
            
            if db.unblock_user(target_user_id):
                await query.answer("✅ User unblocked successfully", show_alert=True)
                logger.info(f"Admin {user_id} unblocked user {target_user_id}")
                
                # Send notification to user
                try:
                    notification_text = """
╔═══════════════════════════════════════╗
║   ✅ ACCOUNT UNBLOCKED ✅              ║
╚═══════════════════════════════════════╝

Your account has been unblocked.
You can now use the bot again.

Use /start to begin.
                    """
                    
                    bot_instance = query.message.bot if hasattr(query, 'message') and query.message else None
                    if bot_instance:
                        await bot_instance.send_message(
                            chat_id=target_user_id,
                            text=notification_text,
                            parse_mode='Markdown'
                        )
                        logger.info(f"Sent unblock notification to user {target_user_id}")
                except Exception as e:
                    logger.error(f"Failed to send unblock notification: {e}")
                
                # Refresh the status view
                query.data = f"view_user_status_{target_user_id}"
                await button_callback(update, context)
            else:
                await query.answer("❌ Failed to unblock user", show_alert=True)
        except ValueError:
            await query.answer("❌ Invalid user ID", show_alert=True)
        except Exception as e:
            logger.error(f"Error unblocking user: {e}", exc_info=True)
            await query.answer(f"❌ Error: {str(e)}", show_alert=True)
        return
    
    # Handle downgrade user
    elif data.startswith("downgrade_user_"):
        if not db.is_admin(user_id):
            await query.answer("❌ Access Denied", show_alert=True)
            return
        
        try:
            target_user_id = int(data.replace("downgrade_user_", ""))
            
            # Don't allow downgrading admins
            if db.is_admin(target_user_id):
                await query.answer("❌ Cannot downgrade admin users", show_alert=True)
                return
            
            if db.downgrade_user(target_user_id):
                await query.answer("✅ User downgraded successfully", show_alert=True)
                logger.info(f"Admin {user_id} downgraded user {target_user_id}")
                
                # Send notification to user
                try:
                    notification_text = """
╔═══════════════════════════════════════╗
║   ⚠️ ACCOUNT DOWNGRADED ⚠️             ║
╚═══════════════════════════════════════╝

Your subscription has been removed.
You are now on the free tier.

Use /status to check your current plan.
                    """
                    
                    bot_instance = query.message.bot if hasattr(query, 'message') and query.message else None
                    if bot_instance:
                        await bot_instance.send_message(
                            chat_id=target_user_id,
                            text=notification_text,
                            parse_mode='Markdown'
                        )
                except Exception as e:
                    logger.error(f"Failed to send downgrade notification: {e}")
                
                # Refresh the status view
                query.data = f"view_user_status_{target_user_id}"
                await button_callback(update, context)
            else:
                await query.answer("❌ Failed to downgrade user", show_alert=True)
        except ValueError:
            await query.answer("❌ Invalid user ID", show_alert=True)
        except Exception as e:
            logger.error(f"Error downgrading user: {e}", exc_info=True)
            await query.answer(f"❌ Error: {str(e)}", show_alert=True)
        return


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    user_id = update.effective_user.id
    stats = db.get_user_usage_stats(user_id)
    
    plan_type = stats.get('plan_type', 'free')
    status = stats.get('status', 'active')
    requests_used = stats.get('requests_used', 0)
    requests_limit = stats.get('requests_limit', 4)
    remaining = stats.get('remaining', 0)
    today_usage = stats.get('today_usage', 0)
    is_admin_user = stats.get('is_admin', False)
    
    # Format for display
    if is_admin_user or requests_limit == float('inf'):
        limit_display = "Unlimited"
        remaining_display = "Unlimited"
        plan_display = "ADMIN" if is_admin_user else plan_type.upper()
    else:
        limit_display = f"{requests_used}/{requests_limit}"
        remaining_display = str(remaining)
        plan_display = plan_type.upper()
    
    status_text = f"""
╔═══════════════════════════════════════╗
║        📊 ACCOUNT STATUS 📊           ║
╚═══════════════════════════════════════╝

┌─ SUBSCRIPTION INFO ──────────────────┐
│ Plan: `{plan_display:<25}` │
│ Status: `{status.upper():<23}` │
└──────────────────────────────────────┘

┌─ USAGE STATISTICS ───────────────────┐
│ Used: `{limit_display:<25}` │
│ Remaining: `{remaining_display:<22}` │
│ Today: `{today_usage}` requests        │
└──────────────────────────────────────┘
    """
    
    # Always show expiration for premium/temp plans
    if stats.get('is_premium') and 'end_date' in stats:
        from datetime import datetime, timezone
        try:
            # Parse end_date (handle different formats)
            end_date_str = stats['end_date']
            if isinstance(end_date_str, str):
                # Try parsing with timezone
                if 'Z' in end_date_str or '+' in end_date_str:
                    end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                else:
                    # SQLite datetime format
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d %H:%M:%S')
            else:
                end_date = end_date_str
            
            # Calculate time remaining
            now = datetime.now(timezone.utc) if end_date.tzinfo else datetime.now()
            if end_date.tzinfo:
                now = datetime.now(timezone.utc)
            else:
                now = datetime.now()
            
            time_remaining = end_date - now
            
            if time_remaining.total_seconds() > 0:
                # Format time remaining
                days = time_remaining.days
                hours, remainder = divmod(time_remaining.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                
                if days > 0:
                    time_left = f"{days}d {hours}h {minutes}m"
                elif hours > 0:
                    time_left = f"{hours}h {minutes}m"
                else:
                    time_left = f"{minutes}m"
                
                status_text += f"\n┌─ EXPIRATION INFO ─────────────────────┐\n"
                status_text += f"│ Expires: `{end_date.strftime('%Y-%m-%d %H:%M'):<22}` │\n"
                status_text += f"│ Time Left: `{time_left:<21}` │\n"
                status_text += f"└──────────────────────────────────────┘"
            else:
                # Already expired
                status_text += f"\n┌─ EXPIRATION INFO ─────────────────────┐\n"
                status_text += f"│ Status: `EXPIRED`                      │\n"
                status_text += f"│ Expired: `{end_date.strftime('%Y-%m-%d %H:%M'):<22}` │\n"
                status_text += f"└──────────────────────────────────────┘"
        except Exception as e:
            # Fallback if date parsing fails
            status_text += f"\n┌─ EXPIRATION INFO ─────────────────────┐\n"
            status_text += f"│ Expires: `{str(stats['end_date']):<22}` │\n"
            status_text += f"└──────────────────────────────────────┘"
    
    # Status menu keyboard
    keyboard = []
    if not stats['is_premium']:
        keyboard.append([InlineKeyboardButton("💎 Upgrade Now", callback_data="menu_plans")])
    keyboard.extend([
        [
            InlineKeyboardButton("🆕 New Chat", callback_data="menu_new"),
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
        ]
    ])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(status_text, parse_mode='Markdown', reply_markup=reply_markup)


async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /referral command"""
    user_id = update.effective_user.id
    referral_code = db.get_referral_code(user_id)
    ref_stats = db.get_referral_stats(user_id)
    
    # Get bot username from context
    bot_username = context.bot.username if hasattr(context.bot, 'username') else "your_bot"
    referral_link = f"https://t.me/{bot_username}?start=ref_{referral_code}"
    
    total_refs = ref_stats.get('total_referrals', 0)
    earned = total_refs * 20
    
    referral_text = f"""
╔═══════════════════════════════════════╗
║      🎁 REFERRAL PROGRAM 🎁           ║
╚═══════════════════════════════════════╝

┌─ YOUR REFERRAL CODE ─────────────────┐
│ `{referral_code}`                     │
└──────────────────────────────────────┘

┌─ YOUR STATISTICS ────────────────────┐
│ Total Referrals: `{total_refs:<18}` │
│ Free Requests Earned: `{earned:<12}` │
└──────────────────────────────────────┘

┌─ HOW IT WORKS ────────────────────────┐
│ 1. Share your referral link          │
│ 2. When someone subscribes →         │
│    You get 20 FREE requests!          │
│ 3. Rewards added automatically       │
│ 4. Unlimited referrals = Unlimited!   │
└──────────────────────────────────────┘
    """
    
    # Referral menu keyboard
    keyboard = [
        [InlineKeyboardButton("📤 Share Referral Link", url=f"https://t.me/share/url?url={referral_link}&text=Join%20SMG-Forcer%20AI%20Bot!")],
        [
            InlineKeyboardButton("📋 Copy Code", callback_data=f"copy_code_{referral_code}"),
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(referral_text, parse_mode='Markdown', reply_markup=reply_markup)


async def new_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /new command - Reset user's conversation"""
    user_id = update.effective_user.id
    
    if user_id in user_sessions:
        user_sessions[user_id].reset()
        await update.message.reply_text("✅ *Memory wiped. New session started.*", parse_mode='Markdown')
    else:
        await update.message.reply_text("ℹ️ *No active session. Starting new conversation...*", parse_mode='Markdown')
        get_user_brain(user_id)


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /myid command - Show user's Telegram ID"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "N/A"
    first_name = update.effective_user.first_name or "N/A"
    
    message = f"""
╔═══════════════════════════════════════╗
║     📋 YOUR TELEGRAM INFO 📋          ║
╚═══════════════════════════════════════╝

┌─ ACCOUNT DETAILS ─────────────────────┐
│ User ID: `{user_id}`                 │
│ Username: @{username}                │
│ Name: {first_name}                    │
└──────────────────────────────────────┘

┌─ ADMIN SETUP ─────────────────────────┐
│ To add yourself as admin:            │
│ Run: `python add_admin.py {user_id}` │
└──────────────────────────────────────┘
    """
    
    await update.message.reply_text(message, parse_mode='Markdown')


# ==================== Document Generation Commands ====================

async def generate_document_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /generate_document command"""
    user_id = update.effective_user.id
    user_message = ' '.join(context.args) if context.args else None
    
    if not user_message:
        await update.message.reply_text(
            "📄 *Document Generator*\n\n"
            "Usage: `/generate_document [type] [content]`\n"
            "Types: `pdf`, `word`, `excel`\n\n"
            "Example: `/generate_document pdf This is my document content`",
            parse_mode='Markdown'
        )
        return
    
    try:
        from document_generator import get_document_generator
        
        doc_gen = get_document_generator()
        
        # Parse type and content
        parts = user_message.split(' ', 1)
        doc_type = parts[0].lower() if len(parts) > 1 else 'pdf'
        content = parts[1] if len(parts) > 1 else user_message
        
        # Generate document
        if doc_type == 'pdf':
            filepath = doc_gen.generate_pdf(content, title="Generated Document")
        elif doc_type == 'word' or doc_type == 'docx':
            filepath = doc_gen.generate_word(content, title="Generated Document")
        elif doc_type == 'excel' or doc_type == 'xlsx':
            # For Excel, convert content to table format
            rows = [[cell] for cell in content.split('\n')]
            filepath = doc_gen.generate_excel(rows)
        else:
            await update.message.reply_text(f"❌ Unknown document type: {doc_type}")
            return
        
        if filepath and Path(filepath).exists():
            # Verify file is not empty
            file_size = Path(filepath).stat().st_size
            if file_size == 0:
                await update.message.reply_text("❌ Generated document is empty. Please try again.")
                return
            
            with open(filepath, 'rb') as f:
                await update.message.reply_document(document=f, filename=Path(filepath).name)
            logger.info(f"Sent generated document: {filepath} (size: {file_size} bytes)")
        else:
            await update.message.reply_text("❌ Failed to generate document")
            
    except Exception as e:
        logger.error(f"Error generating document: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def generate_pdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /generate_pdf command"""
    user_message = ' '.join(context.args) if context.args else None
    
    if not user_message:
        await update.message.reply_text("Usage: `/generate_pdf [content]`", parse_mode='Markdown')
        return
    
    try:
        from document_generator import get_document_generator
        doc_gen = get_document_generator()
        filepath = doc_gen.generate_pdf(user_message, title="Generated PDF")
        
        if filepath and Path(filepath).exists():
            file_size = Path(filepath).stat().st_size
            if file_size == 0:
                await update.message.reply_text("❌ Generated PDF is empty. Please try again.")
                return
            with open(filepath, 'rb') as f:
                await update.message.reply_document(document=f, filename=Path(filepath).name)
            logger.info(f"Sent generated PDF: {filepath} (size: {file_size} bytes)")
        else:
            await update.message.reply_text("❌ Failed to generate PDF")
    except Exception as e:
        logger.error(f"Error generating PDF: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def generate_word_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /generate_word command"""
    user_message = ' '.join(context.args) if context.args else None
    
    if not user_message:
        await update.message.reply_text("Usage: `/generate_word [content]`", parse_mode='Markdown')
        return
    
    try:
        from document_generator import get_document_generator
        doc_gen = get_document_generator()
        filepath = doc_gen.generate_word(user_message, title="Generated Document")
        
        if filepath and Path(filepath).exists():
            file_size = Path(filepath).stat().st_size
            if file_size == 0:
                await update.message.reply_text("❌ Generated Word document is empty. Please try again.")
                return
            with open(filepath, 'rb') as f:
                await update.message.reply_document(document=f, filename=Path(filepath).name)
            logger.info(f"Sent generated Word document: {filepath} (size: {file_size} bytes)")
        else:
            await update.message.reply_text("❌ Failed to generate Word document")
    except Exception as e:
        logger.error(f"Error generating Word document: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def generate_excel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /generate_excel command"""
    user_message = ' '.join(context.args) if context.args else None
    
    if not user_message:
        await update.message.reply_text("Usage: `/generate_excel [data]`\nFormat: Each line is a row, comma-separated values", parse_mode='Markdown')
        return
    
    try:
        from document_generator import get_document_generator
        doc_gen = get_document_generator()
        
        # Parse CSV-like data
        rows = [line.split(',') for line in user_message.split('\n') if line.strip()]
        filepath = doc_gen.generate_excel(rows)
        
        if filepath and Path(filepath).exists():
            file_size = Path(filepath).stat().st_size
            if file_size == 0:
                await update.message.reply_text("❌ Generated Excel spreadsheet is empty. Please try again.")
                return
            with open(filepath, 'rb') as f:
                await update.message.reply_document(document=f, filename=Path(filepath).name)
            logger.info(f"Sent generated Excel spreadsheet: {filepath} (size: {file_size} bytes)")
        else:
            await update.message.reply_text("❌ Failed to generate Excel spreadsheet")
    except Exception as e:
        logger.error(f"Error generating Excel: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def generate_qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /generate_qr command"""
    data = ' '.join(context.args) if context.args else None
    
    if not data:
        await update.message.reply_text(
            "📱 *QR Code Generator*\n\n"
            "Usage: `/generate_qr [data]`\n\n"
            "Example: `/generate_qr https://example.com`\n"
            "Example: `/generate_qr Hello World`",
            parse_mode='Markdown'
        )
        return
    
    try:
        from document_generator import get_document_generator
        
        await update.message.reply_text("📱 Generating QR code...")
        
        doc_gen = get_document_generator()
        filepath = doc_gen.generate_qr_code(data)
        
        if filepath:
            with open(filepath, 'rb') as f:
                await update.message.reply_photo(photo=f, caption=f"📱 QR Code: `{data[:50]}`", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Failed to generate QR code")
            
    except Exception as e:
        logger.error(f"Error generating QR code: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def generate_barcode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /generate_barcode command"""
    args = context.args
    
    if not args or len(args) < 1:
        await update.message.reply_text(
            "📊 *Barcode Generator*\n\n"
            "Usage: `/generate_barcode [data] [type]`\n\n"
            "Types: `code128`, `code39`, `ean13`, `ean8`, `upc`, `isbn10`, `isbn13`\n\n"
            "Example: `/generate_barcode 1234567890 code128`\n"
            "Example: `/generate_barcode 9781234567890 isbn13`",
            parse_mode='Markdown'
        )
        return
    
    try:
        from document_generator import get_document_generator
        
        data = args[0]
        barcode_type = args[1] if len(args) > 1 else 'code128'
        
        await update.message.reply_text(f"📊 Generating {barcode_type} barcode...")
        
        doc_gen = get_document_generator()
        filepath = doc_gen.generate_barcode(data, barcode_type=barcode_type)
        
        if filepath:
            with open(filepath, 'rb') as f:
                await update.message.reply_photo(photo=f, caption=f"📊 Barcode ({barcode_type}): `{data}`", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Failed to generate barcode")
            
    except Exception as e:
        logger.error(f"Error generating barcode: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


# ==================== Template Management Commands ====================

async def save_template_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /save_template command"""
    user_id = update.effective_user.id
    args = context.args
    
    if not args or len(args) < 2:
        await update.message.reply_text(
            "💾 *Save Template*\n\n"
            "Usage: `/save_template [name] [type] [category]`\n"
            "Types: `pdf`, `word`, `excel`\n\n"
            "Example: `/save_template invoice_template pdf invoice`",
            parse_mode='Markdown'
        )
        return
    
    try:
        from template_manager import get_template_manager
        template_mgr = get_template_manager(db)
        
        name = args[0]
        template_type = args[1] if len(args) > 1 else 'pdf'
        category = args[2] if len(args) > 2 else None
        
        # Get last generated document (would need to track this)
        # For now, create a basic template
        template_data = {
            'content': 'Template content',
            'options': {}
        }
        
        template_id = template_mgr.save_template(
            user_id=user_id,
            name=name,
            template_type=template_type,
            template_data=template_data,
            category=category
        )
        
        if template_id:
            await update.message.reply_text(f"✅ Template saved: `{name}` (ID: {template_id})", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Failed to save template")
            
    except Exception as e:
        logger.error(f"Error saving template: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def use_template_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /use_template command"""
    user_id = update.effective_user.id
    template_name = ' '.join(context.args) if context.args else None
    
    if not template_name:
        await update.message.reply_text("Usage: `/use_template [template_name]`", parse_mode='Markdown')
        return
    
    try:
        from template_manager import get_template_manager
        from document_generator import get_document_generator
        
        template_mgr = get_template_manager(db)
        template = template_mgr.get_template(name=template_name, user_id=user_id)
        
        if not template:
            await update.message.reply_text(f"❌ Template not found: `{template_name}`", parse_mode='Markdown')
            return
        
        # Process template if it's a PSD file
        template_file_path = template.get('template_data', {}).get('file_path')
        if template_file_path and Path(template_file_path).exists():
            try:
                from template_processor import get_template_processor
                processor = get_template_processor()
                processed_info = processor.process_template(template_file_path, template_name)
                if processed_info:
                    await update.message.reply_text(
                        f"✅ Template processed!\n"
                        f"📊 Layers: {processed_info.get('layer_count', 0)}\n"
                        f"📝 Text fields: {processed_info.get('text_layer_count', 0)}",
                        parse_mode='Markdown'
                    )
            except Exception as e:
                logger.warning(f"Could not process template: {e}")
        
        # Check if this is an ID template request with photo
        template_data = template.get('template_data', {})
        template_file_path = template_data.get('file_path')
        
        # Check if user uploaded a photo (in context)
        user_photo = None
        if context.user_data.get('last_photo'):
            user_photo = context.user_data.get('last_photo')
        
        # If it's an ID template and we have a photo, use ID processor
        if template_name and 'id' in template_name.lower() and user_photo:
            try:
                from id_template_processor import get_id_processor
                id_processor = get_id_processor()
                
                # Extract user data from message if provided
                user_data = {}
                message_text = update.message.text or ""
                if message_text:
                    # Try to extract data from message
                    import re
                    if 'name' in message_text.lower():
                        name_match = re.search(r'name[:\s]+([^\n,]+)', message_text, re.I)
                        if name_match:
                            user_data['name'] = name_match.group(1).strip()
                
                filepath = id_processor.process_texas_id_with_photo(
                    user_photo,
                    template_name=template_name,
                    user_data=user_data
                )
            except Exception as e:
                logger.warning(f"ID processor not available, using document generator: {e}")
                filepath = None
        else:
            # Use regular document generator
            doc_gen = get_document_generator()
            filepath = doc_gen.generate_from_template(
                template['template_data'],
                doc_type=template['type'],
                variables={},  # Can be enhanced to accept variables
                template_name=template_name
            )
        
        if filepath and Path(filepath).exists():
            # Verify file is not empty
            file_size = Path(filepath).stat().st_size
            if file_size == 0:
                await update.message.reply_text("❌ Generated file is empty. Please try again.")
                return
            
            # Determine file type and send appropriately
            file_ext = Path(filepath).suffix.lower()
            if file_ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                # Send images as photos
                with open(filepath, 'rb') as f:
                    await update.message.reply_photo(photo=f, caption="✅ Generated from template")
            else:
                # Send documents as documents
                with open(filepath, 'rb') as f:
                    await update.message.reply_document(document=f, filename=Path(filepath).name)
            logger.info(f"Sent generated file: {filepath} (size: {file_size} bytes)")
        else:
            await update.message.reply_text("❌ Failed to generate document from template")
            
    except Exception as e:
        logger.error(f"Error using template: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def list_templates_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list_templates command"""
    user_id = update.effective_user.id
    
    try:
        from template_manager import get_template_manager
        template_mgr = get_template_manager(db)
        templates = template_mgr.list_templates(user_id=user_id)
        
        if not templates:
            await update.message.reply_text("📋 No templates found. Use `/save_template` to create one.", parse_mode='Markdown')
            return
        
        message = "📋 *Your Templates:*\n\n"
        for template in templates:
            scope = "🌐 Global" if template['is_global'] else "👤 Personal"
            message += f"• `{template['name']}` ({template['type']}) - {scope}\n"
            if template.get('description'):
                message += f"  _{template['description']}_\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error listing templates: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def delete_template_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /delete_template command"""
    user_id = update.effective_user.id
    template_name = ' '.join(context.args) if context.args else None
    
    if not template_name:
        await update.message.reply_text("Usage: `/delete_template [template_name]`", parse_mode='Markdown')
        return
    
    try:
        from template_manager import get_template_manager
        template_mgr = get_template_manager(db)
        
        template = template_mgr.get_template(name=template_name, user_id=user_id)
        if not template:
            await update.message.reply_text(f"❌ Template not found: `{template_name}`", parse_mode='Markdown')
            return
        
        if template_mgr.delete_template(template['id'], user_id=user_id):
            await update.message.reply_text(f"✅ Template deleted: `{template_name}`", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Failed to delete template (check permissions)")
            
    except Exception as e:
        logger.error(f"Error deleting template: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def download_template_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /download_template command - Download template from MediaFire or URL"""
    user_id = update.effective_user.id
    args = context.args
    
    if not args or len(args) < 1:
        await update.message.reply_text(
            "📥 *Download Template*\n\n"
            "Usage: `/download_template [url] [name]`\n\n"
            "Supports:\n"
            "• MediaFire links\n"
            "• Direct download URLs\n\n"
            "Example: `/download_template https://www.mediafire.com/file/.../texas_dl.rar texas_dl`",
            parse_mode='Markdown'
        )
        return
    
    url = args[0]
    template_name = args[1] if len(args) > 1 else None
    
    try:
        from template_downloader import get_template_downloader
        
        await update.message.reply_text("📥 Downloading template... This may take a moment.")
        
        downloader = get_template_downloader()
        
        # Determine source and download
        if 'mediafire.com' in url.lower():
            file_path = downloader.download_from_mediafire(url, template_name)
        elif 'mega.nz' in url.lower():
            file_path = downloader.download_from_mega(url, template_name)
        else:
            # Direct URL download (basic support)
            await update.message.reply_text("📥 Downloading from direct URL...")
            try:
                import requests
                response = requests.get(url, stream=True, timeout=300)
                response.raise_for_status()
                
                if not template_name:
                    # Extract filename from URL or Content-Disposition
                    content_disposition = response.headers.get('Content-Disposition', '')
                    if 'filename=' in content_disposition:
                        template_name = content_disposition.split('filename=')[1].strip('"\'')
                    else:
                        import time
                template_name = url.split('/')[-1].split('?')[0] or f"template_{int(time.time())}"
                
                file_ext = Path(template_name).suffix.lower()
                if file_ext == '.psd':
                    save_path = downloader.psd_dir / template_name
                else:
                    save_path = downloader.templates_dir / template_name
                
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                file_path = str(save_path)
            except Exception as e:
                logger.error(f"Error downloading from URL: {e}")
                await update.message.reply_text(f"❌ Failed to download from URL: {str(e)}")
                return
        
        if file_path:
            # Process template for AI use (extract PSD layers, etc.)
            template_processed = False
            try:
                from template_processor import get_template_processor
                processor = get_template_processor()
                processed_info = processor.process_template(file_path, template_name)
                if processed_info:
                    template_processed = True
                    await update.message.reply_text(
                        f"🔧 Processing template...\n"
                        f"📊 Extracted {processed_info.get('layer_count', 0)} layers\n"
                        f"📝 Found {processed_info.get('text_layer_count', 0)} editable text fields",
                        parse_mode='Markdown'
                    )
            except Exception as e:
                logger.warning(f"Could not process template: {e}")
            
            # Save to template database
            from template_manager import get_template_manager
            template_mgr = get_template_manager(db)
            
            # Determine template type from file extension
            file_ext = Path(file_path).suffix.lower() if file_path else None
            if file_ext == '.psd':
                template_type = 'psd'
            elif file_ext == '.pdf':
                template_type = 'pdf'
            elif file_ext in ['.rar', '.zip']:
                template_type = 'archive'
            else:
                template_type = 'other'
            
            # Determine source
            if 'mediafire.com' in url.lower():
                source = 'mediafire'
            elif 'mega.nz' in url.lower():
                source = 'mega'
            else:
                source = 'direct'
            
            final_template_name = template_name or (Path(file_path).stem if file_path else f"template_{int(time.time())}")
            
            template_id = template_mgr.save_template(
                user_id=user_id,
                name=final_template_name,
                template_type=template_type,
                template_data={'file_path': file_path, 'source_url': url, 'source': source, 'processed': template_processed},
                category='downloaded',
                description=f"Downloaded from {source}" + (" (Processed for AI)" if template_processed else ""),
                source_url=url,
                file_path=file_path
            )
            
            if template_id:
                status_msg = f"✅ Template downloaded and saved!\n\n"
                status_msg += f"📁 File: `{Path(file_path).name}`\n"
                status_msg += f"💾 Template ID: `{template_id}`\n"
                if template_processed:
                    status_msg += f"🤖 AI-ready: Template processed and ready for generation\n"
                status_msg += f"📋 Use with: `/use_template {final_template_name}`"
                
                await update.message.reply_text(status_msg, parse_mode='Markdown')
            else:
                await update.message.reply_text(
                    f"✅ Template downloaded: `{file_path}`\n\n"
                    f"⚠️ Could not save to database, but file is available.",
                    parse_mode='Markdown'
                )
        else:
            await update.message.reply_text("❌ Failed to download template. Check the URL and try again.")
            
    except Exception as e:
        logger.error(f"Error downloading template: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


# ==================== Image Generation Commands ====================

async def generate_image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /generate_image command"""
    prompt = ' '.join(context.args) if context.args else None
    
    if not prompt:
        await update.message.reply_text(
            "🎨 *Image Generator*\n\n"
            "Usage: `/generate_image [prompt]`\n\n"
            "Example: `/generate_image a beautiful sunset over mountains`",
            parse_mode='Markdown'
        )
        return
    
    try:
        from image_generator import get_image_generator
        
        await update.message.reply_text("🎨 Generating image... This may take a moment.")
        
        img_gen = get_image_generator()
        filepath = img_gen.generate_image(prompt)
        
        if filepath:
            with open(filepath, 'rb') as f:
                await update.message.reply_photo(photo=f)
        else:
            await update.message.reply_text("❌ Failed to generate image")
            
    except Exception as e:
        logger.error(f"Error generating image: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


# ==================== Image Editing Commands ====================

async def edit_image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /edit_image command"""
    await update.message.reply_text(
        "🖼️ *Image Editor*\n\n"
        "Upload an image and use one of these commands:\n"
        "• `/add_text [text]` - Add text overlay\n"
        "• `/apply_filter [type]` - Apply filter (blur, sharpen, etc.)\n"
        "• `/crop [x1,y1,x2,y2]` - Crop image\n"
        "• `/rotate [angle]` - Rotate image\n"
        "• `/resize [width]x[height]` - Resize image",
        parse_mode='Markdown'
    )


# ==================== Face Swap Commands ====================

# Service Management Commands
async def start_service_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start_service command"""
    user_id = update.effective_user.id
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /start_service [name] [command]\n\n"
            "Example: /start_service evilginx './evilginx -p phishlets/'"
        )
        return
    
    service_name = context.args[0]
    command = ' '.join(context.args[1:])
    
    try:
        from service_manager import get_service_manager
        from user_workspace_manager import UserWorkspaceManager
        
        workspace_manager = UserWorkspaceManager.get_instance()
        user_workspace = workspace_manager.get_user_workspace(user_id)
        
        service_mgr = get_service_manager(str(user_workspace))
        service_info = service_mgr.start_service(service_name, command, str(user_workspace), user_id)
        
        # Save to database
        db.save_service(
            user_id=user_id,
            service_name=service_name,
            command=command,
            workspace_path=str(user_workspace),
            pid=service_info.get('pid'),
            status=service_info.get('status', 'running'),
            metadata=service_info.get('metadata', {})
        )
        
        if service_info.get('status') == 'running':
            await update.message.reply_text(
                f"✅ Service `{service_name}` started successfully\n\n"
                f"PID: `{service_info.get('pid')}`\n"
                f"Status: `{service_info.get('status')}`\n"
                f"Logs: `{service_info.get('log_file', 'N/A')}`",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"❌ Failed to start service `{service_name}`\n\n"
                f"Error: {service_info.get('message', 'Unknown error')}",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Error in start_service_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def stop_service_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stop_service command"""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("Usage: /stop_service [name]")
        return
    
    service_name = context.args[0]
    
    try:
        from service_manager import get_service_manager
        from user_workspace_manager import UserWorkspaceManager
        
        workspace_manager = UserWorkspaceManager.get_instance()
        user_workspace = workspace_manager.get_user_workspace(user_id)
        
        service_mgr = get_service_manager(str(user_workspace))
        service = db.get_service(user_id, service_name)
        
        if not service:
            await update.message.reply_text(f"❌ Service `{service_name}` not found", parse_mode='Markdown')
            return
        
        pid = service.get('pid')
        success = service_mgr.stop_service(service_name, user_id, pid)
        
        if success:
            db.update_service_status(user_id, service_name, 'stopped')
            await update.message.reply_text(f"✅ Service `{service_name}` stopped", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Failed to stop service `{service_name}`", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in stop_service_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def list_services_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list_services command"""
    user_id = update.effective_user.id
    
    try:
        services = db.list_user_services(user_id)
        
        if not services:
            await update.message.reply_text("No services found")
            return
        
        message = "📋 *Your Services*\n\n"
        for service in services:
            status_emoji = "🟢" if service.get('status') == 'running' else "🔴"
            message += f"{status_emoji} *{service.get('service_name')}*\n"
            message += f"Status: `{service.get('status')}`\n"
            if service.get('pid'):
                message += f"PID: `{service.get('pid')}`\n"
            message += f"Started: `{service.get('started_at', 'N/A')}`\n\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in list_services_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def service_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /service_status command"""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("Usage: /service_status [name]")
        return
    
    service_name = context.args[0]
    
    try:
        from service_manager import get_service_manager
        from user_workspace_manager import UserWorkspaceManager
        
        workspace_manager = UserWorkspaceManager.get_instance()
        user_workspace = workspace_manager.get_user_workspace(user_id)
        
        service_mgr = get_service_manager(str(user_workspace))
        service = db.get_service(user_id, service_name)
        
        if not service:
            await update.message.reply_text(f"❌ Service `{service_name}` not found", parse_mode='Markdown')
            return
        
        pid = service.get('pid')
        status = service_mgr.get_service_status(service_name, user_id, pid)
        
        message = f"📊 *Service Status: {service_name}*\n\n"
        message += f"Status: `{status.get('status')}`\n"
        message += f"Running: `{status.get('running')}`\n"
        if status.get('pid'):
            message += f"PID: `{status.get('pid')}`\n"
            message += f"CPU: `{status.get('cpu_percent', 0):.1f}%`\n"
            message += f"Memory: `{status.get('memory_mb', 0):.1f} MB`\n"
            message += f"Uptime: `{status.get('uptime_seconds', 0)}s`\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in service_status_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def service_logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /service_logs command"""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("Usage: /service_logs [name] [lines]")
        return
    
    service_name = context.args[0]
    lines = int(context.args[1]) if len(context.args) > 1 else 50
    
    try:
        from service_manager import get_service_manager
        from user_workspace_manager import UserWorkspaceManager
        
        workspace_manager = UserWorkspaceManager.get_instance()
        user_workspace = workspace_manager.get_user_workspace(user_id)
        
        service_mgr = get_service_manager(str(user_workspace))
        logs = service_mgr.get_service_logs(service_name, user_id, lines)
        
        if len(logs) > 4000:
            logs = logs[-4000:] + "\n... (truncated)"
        
        await update.message.reply_text(f"📄 *Logs for {service_name}*\n\n```\n{logs}\n```", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in service_logs_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


# Project Management Commands
async def save_project_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /save_project command"""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("Usage: /save_project [name]")
        return
    
    project_name = context.args[0]
    
    try:
        from project_persistence import get_project_persistence
        from user_workspace_manager import UserWorkspaceManager
        
        workspace_manager = UserWorkspaceManager.get_instance()
        user_workspace = workspace_manager.get_user_workspace(user_id)
        
        persistence = get_project_persistence(db)
        success = persistence.save_project(user_id, project_name, str(user_workspace))
        
        if success:
            await update.message.reply_text(f"✅ Project `{project_name}` saved successfully", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Failed to save project `{project_name}`", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in save_project_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def restore_project_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /restore_project command"""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("Usage: /restore_project [name]")
        return
    
    project_name = context.args[0]
    
    try:
        from project_persistence import get_project_persistence
        from user_workspace_manager import UserWorkspaceManager
        
        workspace_manager = UserWorkspaceManager.get_instance()
        user_workspace = workspace_manager.get_user_workspace(user_id)
        
        persistence = get_project_persistence(db)
        success = persistence.restore_project(user_id, project_name, str(user_workspace))
        
        if success:
            await update.message.reply_text(f"✅ Project `{project_name}` restored successfully", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Failed to restore project `{project_name}`", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in restore_project_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def list_projects_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list_projects command"""
    user_id = update.effective_user.id
    
    try:
        from project_persistence import get_project_persistence
        persistence = get_project_persistence(db)
        projects = persistence.list_projects(user_id)
        
        if not projects:
            await update.message.reply_text("No saved projects found")
            return
        
        message = "📋 *Your Saved Projects*\n\n"
        for project in projects:
            metadata = project.get('metadata', {})
            if isinstance(metadata, str):
                import json
                try:
                    metadata = json.loads(metadata)
                except:
                    metadata = {}
            
            message += f"📁 *{project.get('project_name')}*\n"
            message += f"Type: `{metadata.get('project_type', 'unknown')}`\n"
            message += f"Files: `{metadata.get('file_count', 0)}`\n"
            message += f"Saved: `{project.get('created_at', 'N/A')}`\n\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in list_projects_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def delete_project_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /delete_project command"""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("Usage: /delete_project [name]")
        return
    
    project_name = context.args[0]
    
    try:
        from project_persistence import get_project_persistence
        persistence = get_project_persistence(db)
        success = persistence.delete_project(user_id, project_name)
        
        if success:
            await update.message.reply_text(f"✅ Project `{project_name}` deleted", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Failed to delete project `{project_name}`", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in delete_project_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


# Admin Commands
async def admin_workspaces_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin_workspaces command (admin only)"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("❌ Access denied. Admin only.")
        return
    
    try:
        from admin_workspace_manager import get_admin_workspace_manager
        admin_mgr = get_admin_workspace_manager(db)
        workspaces = admin_mgr.list_all_workspaces()
        
        if not workspaces:
            await update.message.reply_text("No workspaces found")
            return
        
        message = "📋 *All User Workspaces*\n\n"
        for ws in workspaces[:20]:  # Limit to 20 for message size
            message += f"👤 User: `{ws.get('user_id')}` ({ws.get('username', 'N/A')})\n"
            message += f"Projects: `{ws.get('project_count', 0)}` | Services: `{ws.get('service_count', 0)}`\n"
            if ws.get('workspace_exists'):
                size_mb = ws.get('workspace_size', 0) / 1024 / 1024
                message += f"Size: `{size_mb:.1f} MB`\n"
            message += "\n"
        
        if len(workspaces) > 20:
            message += f"\n... and {len(workspaces) - 20} more"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in admin_workspaces_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def admin_workspace_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin_workspace command (admin only)"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("❌ Access denied. Admin only.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /admin_workspace [user_id]")
        return
    
    try:
        target_user_id = int(context.args[0])
        from admin_workspace_manager import get_admin_workspace_manager
        admin_mgr = get_admin_workspace_manager(db)
        details = admin_mgr.get_workspace_details(target_user_id)
        
        message = f"📊 *Workspace Details for User {target_user_id}*\n\n"
        message += f"Username: `{details.get('username', 'N/A')}`\n"
        message += f"Workspace: `{details.get('workspace_path', 'N/A')}`\n"
        message += f"Exists: `{details.get('exists', False)}`\n"
        if details.get('exists'):
            size_mb = details.get('size', 0) / 1024 / 1024
            message += f"Size: `{size_mb:.1f} MB`\n"
            message += f"Files: `{details.get('file_count', 0)}`\n"
            message += f"Projects: `{len(details.get('projects', []))}`\n"
        
        message += f"\nActive Services: `{len(details.get('active_services', []))}`\n"
        if details.get('hosting_detected'):
            message += f"⚠️ *Hosting Detected*\n"
            hosting_info = details.get('hosting_info', {})
            message += f"Processes: `{len(hosting_info.get('running_processes', []))}`\n"
            message += f"Open Ports: `{len(hosting_info.get('open_ports', []))}`\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID")
    except Exception as e:
        logger.error(f"Error in admin_workspace_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def admin_services_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin_services command (admin only)"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("❌ Access denied. Admin only.")
        return
    
    try:
        all_services = db.get_all_services()
        
        if not all_services:
            await update.message.reply_text("No services found")
            return
        
        message = "📋 *All Active Services*\n\n"
        for service in all_services[:20]:  # Limit to 20
            status_emoji = "🟢" if service.get('status') == 'running' else "🔴"
            message += f"{status_emoji} User: `{service.get('user_id')}` | Service: `{service.get('service_name')}`\n"
            message += f"Status: `{service.get('status')}`\n"
            if service.get('pid'):
                message += f"PID: `{service.get('pid')}`\n"
            message += "\n"
        
        if len(all_services) > 20:
            message += f"\n... and {len(all_services) - 20} more"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in admin_services_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def admin_service_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin_service command (admin only)"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("❌ Access denied. Admin only.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /admin_service [user_id]")
        return
    
    try:
        target_user_id = int(context.args[0])
        services = db.list_user_services(target_user_id)
        
        if not services:
            await update.message.reply_text(f"No services found for user {target_user_id}")
            return
        
        message = f"📋 *Services for User {target_user_id}*\n\n"
        for service in services:
            status_emoji = "🟢" if service.get('status') == 'running' else "🔴"
            message += f"{status_emoji} *{service.get('service_name')}*\n"
            message += f"Status: `{service.get('status')}`\n"
            if service.get('pid'):
                message += f"PID: `{service.get('pid')}`\n"
            message += f"Command: `{service.get('command', 'N/A')[:50]}...`\n\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID")
    except Exception as e:
        logger.error(f"Error in admin_service_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def admin_delete_project_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin_delete_project command (admin only)"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("❌ Access denied. Admin only.")
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Usage: /admin_delete_project [user_id] [project_name]")
        return
    
    try:
        target_user_id = int(context.args[0])
        project_name = context.args[1]
        
        from admin_workspace_manager import get_admin_workspace_manager
        admin_mgr = get_admin_workspace_manager(db)
        success = admin_mgr.delete_user_project(target_user_id, project_name)
        
        if success:
            await update.message.reply_text(f"✅ Project `{project_name}` deleted for user {target_user_id}", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Failed to delete project", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID")
    except Exception as e:
        logger.error(f"Error in admin_delete_project_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def admin_stop_service_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin_stop_service command (admin only)"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("❌ Access denied. Admin only.")
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Usage: /admin_stop_service [user_id] [service_name]")
        return
    
    try:
        target_user_id = int(context.args[0])
        service_name = context.args[1]
        
        from admin_workspace_manager import get_admin_workspace_manager
        admin_mgr = get_admin_workspace_manager(db)
        success = admin_mgr.stop_user_service(target_user_id, service_name)
        
        if success:
            await update.message.reply_text(f"✅ Service `{service_name}` stopped for user {target_user_id}", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Failed to stop service", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID")
    except Exception as e:
        logger.error(f"Error in admin_stop_service_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def admin_delete_service_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin_delete_service command (admin only)"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("❌ Access denied. Admin only.")
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Usage: /admin_delete_service [user_id] [service_name]")
        return
    
    try:
        target_user_id = int(context.args[0])
        service_name = context.args[1]
        
        from admin_workspace_manager import get_admin_workspace_manager
        admin_mgr = get_admin_workspace_manager(db)
        success = admin_mgr.delete_user_service(target_user_id, service_name)
        
        if success:
            await update.message.reply_text(f"✅ Service `{service_name}` deleted for user {target_user_id}", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Failed to delete service", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID")
    except Exception as e:
        logger.error(f"Error in admin_delete_service_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def admin_workspace_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin_workspace_stats command (admin only)"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("❌ Access denied. Admin only.")
        return
    
    try:
        from admin_workspace_manager import get_admin_workspace_manager
        admin_mgr = get_admin_workspace_manager(db)
        stats = admin_mgr.get_workspace_statistics()
        
        message = "📊 *Workspace Statistics*\n\n"
        message += f"Total Workspaces: `{stats.get('total_workspaces', 0)}`\n"
        total_size_gb = stats.get('total_size', 0) / 1024 / 1024 / 1024
        message += f"Total Size: `{total_size_gb:.2f} GB`\n"
        message += f"Active Services: `{stats.get('active_services_count', 0)}`\n"
        message += f"Total Projects: `{stats.get('total_projects', 0)}`\n"
        message += f"Users with Hosting: `{stats.get('users_with_hosting', 0)}`\n\n"
        
        if stats.get('projects_by_type'):
            message += "*Projects by Type:*\n"
            for ptype, count in stats['projects_by_type'].items():
                message += f"`{ptype}`: {count}\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in admin_workspace_stats_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def face_swap_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /face_swap command"""
    user_id = update.effective_user.id
    
    # Check if user has uploaded images
    if update.message.photo or update.message.document:
        # Store images in context for processing
        context.user_data['face_swap_pending'] = True
        await update.message.reply_text(
            "🔄 *Face Swap*\n\n"
            "Please send two images:\n"
            "1. Source image (face to copy)\n"
            "2. Target image (face to replace)\n\n"
            "You can also add context: `/face_swap holding a card`",
            parse_mode='Markdown'
        )
        return
    
    context_instruction = ' '.join(context.args) if context.args else None
    
    if context_instruction:
        context.user_data['face_swap_context'] = context_instruction
        await update.message.reply_text(
            f"✅ Context saved: `{context_instruction}`\n"
            "Now send two images for face swap.",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "🔄 *Face Swap*\n\n"
            "Usage: Send two images (source + target) or use:\n"
            "`/face_swap [context]`\n\n"
            "Example: `/face_swap holding a card`",
            parse_mode='Markdown'
        )


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle image messages - process with vision models"""
    user_id = update.effective_user.id
    
    # Check if user is blocked
    if db.is_blocked(user_id):
        return
    
    # Get image file
    photo = update.message.photo
    if photo:
        # Get largest photo
        file_id = photo[-1].file_id
    elif update.message.document:
        file_id = update.message.document.file_id
    else:
        await update.message.reply_text("❌ No image found in message.")
        return
    
    try:
        # Get user workspace for permanent photo storage
        try:
            from user_workspace_manager import UserWorkspaceManager
            workspace_manager = UserWorkspaceManager.get_instance()
            user_workspace = workspace_manager.get_user_workspace(user_id)
            workspace = Path(user_workspace)
        except ImportError:
            base_workspace = os.getenv('WORKSPACE_ROOT', os.getcwd())
            workspace = Path(base_workspace) / f"user_{user_id}"
            workspace.mkdir(parents=True, exist_ok=True)
        
        # Download image to permanent location
        file = await context.bot.get_file(file_id)
        image_path = workspace / f"photo_{user_id}_{int(time.time())}.jpg"
        await file.download_to_drive(str(image_path))
        
        # Store photo path in context for template processing
        context.user_data['last_photo'] = str(image_path)
        context.user_data['last_photo_time'] = time.time()
        
        # Persist photo to database state
        try:
            from user_state_manager import get_user_state_manager
            state_mgr = get_user_state_manager(db)
            state_mgr.save_state(user_id, 'last_photo', {'path': str(image_path), 'timestamp': time.time()}, workspace_path=str(workspace))
            logger.info(f"Saved photo to state: {image_path}")
        except Exception as e:
            logger.warning(f"Could not save photo to state: {e}")
        
        # Send immediate confirmation that photo is saved
        await update.message.reply_text(
            f"📸 **Photo received and saved!**\n\n"
            f"✅ Photo is ready for ID generation.\n\n"
            f"Send your details:\n"
            f"• Name: [Your Name]\n"
            f"• DOB: [MM/DD/YYYY]\n"
            f"• Address: [Your Address]"
        )
        
        # Get caption or use default
        caption = update.message.caption or "What is in this image? Describe it in detail."
        
        # Process image with vision models (optional - photo is already saved, run in background)
        vision_processed = False
        try:
            # Try to use DesktopAIHandler, fallback to vision_processor
            try:
                from desktop_ai_handler import DesktopAIHandler
                handler_available = True
            except ImportError:
                handler_available = False
                from vision_processor import get_vision_processor
            
            brain = get_user_brain(user_id)
            
            if handler_available:
                try:
                    workspace = os.path.join(os.getcwd(), f"user_{user_id}")
                    os.makedirs(workspace, exist_ok=True)
                    desktop_handler = DesktopAIHandler(brain, workspace_root=workspace, user_id=user_id)
                    # Add timeout to prevent hanging
                    import asyncio
                    result = await asyncio.wait_for(
                        desktop_handler.process_image(image_path, caption),
                        timeout=30.0  # 30 second timeout
                    )
                    
                    if result.get('success'):
                        response_text = result.get('result', 'Image processed successfully')
                        # Send analysis as separate message (photo already confirmed)
                        await update.message.reply_text(f"🖼️ **Image Analysis:**\n\n{response_text}", parse_mode='Markdown')
                        vision_processed = True
                    else:
                        error = result.get('error', 'Unknown error')
                        # Don't send another message - photo already confirmed above
                        logger.info(f"Vision analysis failed: {error}")
                except asyncio.TimeoutError:
                    logger.warning("Vision processing timed out after 30 seconds")
                    # Photo already confirmed, no need to send another message
                except Exception as e:
                    logger.warning(f"Vision processing error: {e}")
                    # Photo already confirmed, no need to send another message
            else:
                # Fallback: use vision processor directly with timeout
                try:
                    vision_proc = get_vision_processor()
                    # Add timeout to prevent hanging
                    import asyncio
                    result = await asyncio.wait_for(
                        asyncio.to_thread(vision_proc.process_image, image_path, prompt=caption),
                        timeout=30.0  # 30 second timeout
                    )
                    
                    if result.get('success'):
                        response_text = result.get('result', 'Image processed successfully')
                        # Send analysis as separate message (photo already confirmed)
                        await update.message.reply_text(f"🖼️ **Image Analysis:**\n\n{response_text}", parse_mode='Markdown')
                        vision_processed = True
                    else:
                        error = result.get('error', 'Unknown error')
                        # Don't send another message - photo already confirmed above
                        logger.info(f"Vision analysis failed: {error}")
                except asyncio.TimeoutError:
                    logger.warning("Vision processing timed out after 30 seconds")
                    # Photo already confirmed, no need to send another message
                except Exception as e:
                    logger.warning(f"Vision processing error: {e}")
                    # Photo already confirmed, no need to send another message
        
        except Exception as e:
            logger.error(f"Image processing error: {e}", exc_info=True)
            # Don't fail completely - photo is saved
            if 'No vision models' in str(e) or 'vision' in str(e).lower():
                await update.message.reply_text(
                    f"📸 **Photo saved!**\n\n"
                    f"ℹ️ Vision analysis is optional (no API keys needed for ID generation).\n"
                    f"✅ Photo is ready for ID generation.\n\n"
                    f"Send your name, DOB, and address to generate your Texas ID."
                )
            else:
                await update.message.reply_text(
                    f"📸 **Photo saved!**\n\n"
                    f"⚠️ Vision analysis error: {str(e)}\n"
                    f"✅ Photo is ready for ID generation."
                )
        
        # Vision processing is optional - photo is already confirmed above
        # No need to send another confirmation message
    except Exception as e:
        logger.error(f"Error handling image: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")
    # Note: Photo is saved permanently in user workspace, not deleted


async def analyze_uploaded_file(file_path: str, mime_type: str = None) -> Dict:
    """Analyze uploaded file and return full content + summary"""
    try:
        path = Path(file_path)
        if not path.exists():
            return {'summary': 'File not found', 'type': 'unknown', 'content': None}
        
        file_size = path.stat().st_size
        file_ext = path.suffix.lower()
        
        # Maximum file size for reading (1MB for code files, 10MB for PDFs)
        MAX_FILE_SIZE = 1024 * 1024  # 1MB
        MAX_PDF_SIZE = 10 * 1024 * 1024  # 10MB for PDFs
        
        # Detect file type - check MIME type first (most reliable), then extension, then magic bytes
        file_type = 'unknown'
        
        # Check MIME type first (from Telegram) - most reliable
        if mime_type:
            mime_lower = mime_type.lower()
            if 'pdf' in mime_lower:
                file_type = 'pdf'
            elif 'word' in mime_lower or 'document' in mime_lower or 'docx' in mime_lower or 'msword' in mime_lower:
                file_type = 'word'
            elif 'excel' in mime_lower or 'spreadsheet' in mime_lower or 'xlsx' in mime_lower or 'ms-excel' in mime_lower:
                file_type = 'excel'
            elif 'powerpoint' in mime_lower or 'presentation' in mime_lower or 'pptx' in mime_lower or 'ms-powerpoint' in mime_lower:
                file_type = 'powerpoint'
            elif 'image' in mime_lower:
                file_type = 'image'
            elif 'video' in mime_lower:
                file_type = 'video'
            elif 'audio' in mime_lower:
                file_type = 'audio'
            elif 'zip' in mime_lower or 'archive' in mime_lower or 'compressed' in mime_lower:
                file_type = 'archive'
            elif 'text' in mime_lower or 'plain' in mime_lower:
                file_type = 'text'
            elif 'json' in mime_lower:
                file_type = 'config'
            elif 'javascript' in mime_lower or 'js' in mime_lower:
                file_type = 'javascript'
            elif 'python' in mime_lower or 'py' in mime_lower:
                file_type = 'python'
        
        # If MIME type didn't help, check extension
        if file_type == 'unknown':
            # Document types
            document_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp']
            archive_extensions = ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz']
            image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.ico', '.tiff', '.tif']
            video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.mpg', '.mpeg']
            audio_extensions = ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a']
            
            # Code extensions
            code_extensions = ['.py', '.pyw', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h', 
                              '.hpp', '.go', '.rs', '.php', '.rb', '.swift', '.kt', '.scala', '.sh', 
                              '.bash', '.zsh', '.sql', '.html', '.css', '.scss', '.less', '.vue', '.svelte']
            config_extensions = ['.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.conf', '.env']
            text_extensions = ['.txt', '.md', '.markdown', '.rst', '.log']
            
            # Check file type by extension
            if file_ext in document_extensions:
                if file_ext == '.pdf':
                    file_type = 'pdf'
                elif file_ext in ['.doc', '.docx']:
                    file_type = 'word'
                elif file_ext in ['.xls', '.xlsx']:
                    file_type = 'excel'
                elif file_ext in ['.ppt', '.pptx']:
                    file_type = 'powerpoint'
                else:
                    file_type = 'document'
            elif file_ext in archive_extensions:
                file_type = 'archive'
            elif file_ext in image_extensions:
                file_type = 'image'
            elif file_ext in video_extensions:
                file_type = 'video'
            elif file_ext in audio_extensions:
                file_type = 'audio'
            elif file_ext in code_extensions:
                file_type = 'code'
                # More specific types
                if file_ext in ['.py', '.pyw']:
                    file_type = 'python'
                elif file_ext in ['.js', '.ts', '.jsx', '.tsx']:
                    file_type = 'javascript'
                elif file_ext in ['.sh', '.bash', '.zsh']:
                    file_type = 'shell'
            elif file_ext in config_extensions:
                file_type = 'config'
            elif file_ext in text_extensions:
                file_type = 'text'
        else:
            file_type = 'unknown'
        
        # Also check file magic bytes for better detection (especially for PDFs)
        if file_type == 'unknown' or file_ext == '':
            try:
                with open(file_path, 'rb') as f:
                    header = f.read(16)
                    # PDF magic bytes: %PDF
                    if header.startswith(b'%PDF'):
                        file_type = 'pdf'
                    # ZIP-based formats (docx, xlsx, etc.)
                    elif header.startswith(b'PK\x03\x04'):
                        if file_ext in ['.docx']:
                            file_type = 'word'
                        elif file_ext in ['.xlsx']:
                            file_type = 'excel'
                        elif file_ext in ['.pptx']:
                            file_type = 'powerpoint'
                        elif file_ext in ['.zip']:
                            file_type = 'archive'
                        else:
                            file_type = 'archive'  # Likely a ZIP-based format
            except Exception as e:
                logger.debug(f"Could not read file header for type detection: {e}")
        
        # Read full file content if it's a text-based file and within size limit
        file_content = None
        if file_type == 'pdf':
            # For PDFs, try to extract basic info from PDF if PyPDF2 is available
            try:
                try:
                    import PyPDF2
                    with open(file_path, 'rb') as f:
                        pdf_reader = PyPDF2.PdfReader(f)
                        num_pages = len(pdf_reader.pages)
                        # Try to extract first page text as preview
                        if num_pages > 0:
                            try:
                                first_page = pdf_reader.pages[0]
                                preview_text = first_page.extract_text()[:500]
                                if preview_text:
                                    file_content = preview_text
                            except:
                                pass
                except ImportError:
                    pass  # PyPDF2 not available - that's okay
            except Exception as e:
                logger.debug(f"Could not read PDF: {e}")
        elif file_size <= MAX_FILE_SIZE and file_type in ['code', 'python', 'javascript', 'shell', 'text', 'config']:
            try:
                # Try UTF-8 first
                file_content = path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                try:
                    # Fallback to latin-1
                    file_content = path.read_text(encoding='latin-1')
                except:
                    file_content = None
                    logger.warning(f"Could not read file content: {file_path}")
        
        # Generate summary
        summary = f"File type: {file_type}\nSize: {file_size / 1024:.1f} KB"
        if mime_type:
            summary += f"\nMIME type: {mime_type}"
        
        if file_type == 'pdf':
            summary += "\n📄 PDF document detected"
            if file_content:
                summary += f"\nPreview (first page): {file_content[:200]}..."
        
        if file_content:
            lines = len(file_content.split('\n'))
            summary += f"\nLines: {lines}"
            
            # Language-specific analysis
            if file_type == 'python':
                functions = len(re.findall(r'^\s*def\s+\w+', file_content, re.MULTILINE))
                classes = len(re.findall(r'^\s*class\s+\w+', file_content, re.MULTILINE))
                imports = len(re.findall(r'^(?:from\s+\S+\s+)?import\s+', file_content, re.MULTILINE))
                summary += f"\nFunctions: {functions}\nClasses: {classes}\nImports: {imports}"
            elif file_type == 'javascript':
                functions = len(re.findall(r'(?:function\s+\w+|const\s+\w+\s*=\s*(?:\([^)]*\)\s*)?=>|async\s+function)', file_content, re.MULTILINE))
                classes = len(re.findall(r'^\s*class\s+\w+', file_content, re.MULTILINE))
                summary += f"\nFunctions: {functions}\nClasses: {classes}"
            elif file_type == 'code':
                # Generic code analysis
                functions = len(re.findall(r'(?:function|def|fn|func)\s+\w+', file_content, re.MULTILINE | re.IGNORECASE))
                classes = len(re.findall(r'class\s+\w+', file_content, re.MULTILINE | re.IGNORECASE))
                summary += f"\nFunctions: {functions}\nClasses: {classes}"
        else:
            if file_type == 'pdf':
                summary += "\n📄 PDF document (binary format)"
            else:
                summary += "\n⚠️ File too large or binary - content not read"
        
        return {
            'summary': summary,
            'type': file_type,
            'size': file_size,
            'extension': file_ext,
            'content': file_content,  # Full file content
            'lines': len(file_content.split('\n')) if file_content else 0
        }
    except Exception as e:
        logger.error(f"Error analyzing file: {e}")
        return {'summary': f'Error analyzing file: {str(e)}', 'type': 'unknown', 'content': None}

def create_enhancement_keyboard():
    """Create inline keyboard for enhancement options"""
    keyboard = [
        [
            InlineKeyboardButton("✨ Enhance Code", callback_data="enhance_code"),
            InlineKeyboardButton("🔍 Analyze Only", callback_data="analyze_code")
        ],
        [
            InlineKeyboardButton("🛠️ Add Features", callback_data="enhance_add_features"),
            InlineKeyboardButton("⚡ Optimize", callback_data="enhance_optimize")
        ],
        [
            InlineKeyboardButton("📝 Refactor", callback_data="enhance_refactor"),
            InlineKeyboardButton("🛡️ Add Error Handling", callback_data="enhance_error_handling")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def handle_enhancement_request(query, data: str, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Handle code enhancement requests"""
    try:
        await query.answer("Processing enhancement request...")
        
        # Get uploaded file from context
        uploaded_files = context.user_data.get('uploaded_files', [])
        if not uploaded_files:
            await query.edit_message_text("❌ No file found. Please upload a file first.")
            return
        
        latest_file = uploaded_files[-1]
        file_path = latest_file['file_path']
        file_name = latest_file['file_name']
        
        # Determine enhancement type
        enhancement_type = 'general'
        if data == "enhance_add_features":
            enhancement_type = "add_features"
        elif data == "enhance_optimize":
            enhancement_type = "optimize"
        elif data == "enhance_refactor":
            enhancement_type = "refactor"
        elif data == "enhance_error_handling":
            enhancement_type = "add_error_handling"
        elif data == "enhance_code":
            enhancement_type = "general"
        elif data == "analyze_code":
            # Just analyze, don't enhance
            await query.edit_message_text("🔍 Analyzing code...")
            try:
                # Try to import DesktopAIHandler, fallback to direct brain usage
                try:
                    from desktop_ai_handler import DesktopAIHandler
                    handler_available = True
                except ImportError:
                    handler_available = False
                    logger.warning("DesktopAIHandler not available, using direct brain access")
                
                brain = get_user_brain(user_id)
                
                # Read and analyze code
                code = Path(file_path).read_text(encoding='utf-8', errors='ignore')
                analysis_prompt = f"Analyze this code in detail:\n\n```python\n{code[:2000]}\n```\n\nProvide a comprehensive analysis."
                
                if handler_available:
                    workspace = Path(file_path).parent
                    handler = DesktopAIHandler(brain, workspace_root=str(workspace), user_id=user_id)
                    analysis_result = ""
                    for chunk in handler.stream_ai_response(analysis_prompt):
                        analysis_result += chunk
                else:
                    # Fallback: use brain directly
                    analysis_result = ""
                    for chunk in brain.chat(analysis_prompt):
                        analysis_result += chunk
                
                await query.edit_message_text(
                    f"📊 **Code Analysis:** `{file_name}`\n\n{analysis_result[:3000]}",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error analyzing code: {e}")
                await query.edit_message_text(f"❌ Error analyzing code: {str(e)}")
            return
        
        # Enhance code
        await query.edit_message_text(f"✨ Enhancing code ({enhancement_type})...")
        
        try:
            # Try to import DesktopAIHandler, fallback to direct brain usage
            try:
                from desktop_ai_handler import DesktopAIHandler
                handler_available = True
            except ImportError:
                handler_available = False
                logger.warning("DesktopAIHandler not available, using direct brain access")
            
            brain = get_user_brain(user_id)
            
            if handler_available:
                workspace = Path(file_path).parent
                handler = DesktopAIHandler(brain, workspace_root=str(workspace), user_id=user_id)
                
                # Enhance code
                enhanced_path, review = await handler.enhance_uploaded_code(
                    file_path, enhancement_type, query.message, context
                )
                
                # Send enhanced file
                if Path(enhanced_path).exists():
                    with open(enhanced_path, 'rb') as f:
                        await query.message.reply_document(
                            document=f,
                            filename=f"enhanced_{file_name}",
                            caption=f"✨ Enhanced code ({enhancement_type})"
                        )
                    await query.edit_message_text(f"✅ Code enhanced successfully! Enhanced file sent.")
                else:
                    await query.edit_message_text("❌ Enhancement failed. File not generated.")
            else:
                # Fallback: use brain directly to enhance
                code = Path(file_path).read_text(encoding='utf-8', errors='ignore')
                enhancement_prompt = f"Enhance this code ({enhancement_type}):\n\n```python\n{code[:2000]}\n```"
                
                enhanced_code = ""
                for chunk in brain.chat(enhancement_prompt):
                    enhanced_code += chunk
                
                # Save enhanced code
                enhanced_path = Path(file_path).parent / f"enhanced_{file_name}"
                enhanced_path.write_text(enhanced_code, encoding='utf-8')
                
                if Path(enhanced_path).exists():
                    with open(enhanced_path, 'rb') as f:
                        await query.message.reply_document(
                            document=f,
                            filename=f"enhanced_{file_name}",
                            caption=f"✨ Enhanced code ({enhancement_type})"
                        )
                    await query.edit_message_text(f"✅ Code enhanced successfully! Enhanced file sent.")
                else:
                    await query.edit_message_text("❌ Enhancement failed. File not generated.")
        except Exception as e:
            logger.error(f"Error enhancing code: {e}", exc_info=True)
            await query.edit_message_text(f"❌ Error enhancing code: {str(e)}")
    except Exception as e:
        logger.error(f"Error handling enhancement request: {e}", exc_info=True)
        try:
            await query.edit_message_text(f"❌ Error: {str(e)}")
        except:
            pass

async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle file uploads from Telegram"""
    user_id = update.effective_user.id
    document = update.message.document
    
    if not document:
        return
    
    try:
        # Get file info
        file_name = document.file_name or f"uploaded_file_{document.file_id[:8]}"
        
        # Get user workspace
        try:
            from user_workspace_manager import UserWorkspaceManager
            workspace_manager = UserWorkspaceManager.get_instance()
            user_workspace = workspace_manager.get_user_workspace(user_id)
            workspace = Path(user_workspace)
        except ImportError:
            base_workspace = os.getenv('WORKSPACE_ROOT', os.getcwd())
            workspace = Path(base_workspace) / f"user_{user_id}"
            workspace.mkdir(parents=True, exist_ok=True)
        
        # Download file
        file = await context.bot.get_file(document.file_id)
        file_path = workspace / f"uploaded_{file_name}"
        await file.download_to_drive(str(file_path))
        
        logger.info(f"File uploaded by user {user_id}: {file_name} -> {file_path}")
        
        # Analyze file and read full content
        # Get MIME type from Telegram document if available
        mime_type = getattr(document, 'mime_type', None)
        analysis = await analyze_uploaded_file(str(file_path), mime_type=mime_type)
        
        # Store file in context as current file
        if hasattr(context, 'user_data'):
            # Store as current file (for questions/edits)
            context.user_data['current_file'] = {
                'file_path': str(file_path),
                'file_name': file_name,
                'file_type': analysis.get('type', 'unknown'),
                'file_content': analysis.get('content'),  # Full file content
                'file_size': analysis.get('size', 0),
                'lines': analysis.get('lines', 0),
                'uploaded_at': time.time()
            }
            
            # Also store in uploaded_files list for history
            if 'uploaded_files' not in context.user_data:
                context.user_data['uploaded_files'] = []
            context.user_data['uploaded_files'].append({
                'file_path': str(file_path),
                'file_name': file_name,
                'analysis': analysis,
                'content': analysis.get('content')  # Store content for reference
            })
            
            # Generic resource file handling - check if waiting for any resource type
            waiting_resource = None
            for key in list(context.user_data.keys()):
                if key.startswith('waiting_') and key.endswith(f'_{user_id}'):
                    resource_type = key.replace('waiting_', '').replace(f'_{user_id}', '')
                    waiting_resource = resource_type
                    break
            
            if waiting_resource:
                # Store file path for the resource type
                context.user_data[f'{waiting_resource}_path'] = str(file_path)
                context.user_data[f'waiting_{waiting_resource}_{user_id}'] = False
                resource_display = waiting_resource.replace('_', ' ').title()
                await update.message.reply_text(
                    f"✅ **Received your {resource_display.lower()}: `{file_name}`**\n\nContinuing task...", 
                    parse_mode='Markdown'
                )
                return
            
            # Also store as generic uploaded file (fallback for any resource check)
            context.user_data[f'uploaded_file_{user_id}'] = str(file_path)
        
        # Create response message
        file_info_text = f"📄 **File Received:** `{file_name}`\n\n"
        file_info_text += f"**Analysis:**\n```\n{analysis['summary']}\n```\n\n"
        
        if analysis.get('content'):
            file_info_text += f"✅ **File content loaded** ({analysis.get('lines', 0)} lines)\n\n"
            file_info_text += "💡 You can now:\n"
            file_info_text += "• Ask questions about the code\n"
            file_info_text += "• Request edits or improvements\n"
            file_info_text += "• Ask me to explain functions or classes\n"
        else:
            file_info_text += "⚠️ File content could not be read (too large or binary)\n\n"
        
        # Send analysis with mode keyboard
        enhancement_keyboard = create_enhancement_keyboard()
        reply_markup = ensure_mode_keyboard_at_bottom(user_id, context, enhancement_keyboard)
        
        await update.message.reply_text(
            file_info_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error handling file upload: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error processing file: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular text messages"""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    logger.info(f"📨 Received message from user {user_id}: {user_message[:100] if user_message else 'None'}")
    
    if not user_message:
        logger.debug(f"Empty message from user {user_id}, skipping")
        return
    
    # RESTORE STATE: Check for pending tasks and saved data from previous session
    try:
        from user_state_manager import get_user_state_manager
        from continuous_executor import get_continuous_executor
        
        state_mgr = get_user_state_manager(db)
        continuous_exec = get_continuous_executor()
        
        # Get ALL saved state for this user
        all_state = state_mgr.get_all_user_state(user_id)
        
        # Restore saved photo if exists
        if 'last_photo' in all_state:
            photo_state = all_state['last_photo']
            photo_path = photo_state.get('value', {}).get('path')
            if photo_path:
                from pathlib import Path as PathLib
                if PathLib(photo_path).exists():
                    context.user_data['last_photo'] = photo_path
                    context.user_data['last_photo_time'] = photo_state.get('last_updated')
                    logger.info(f"Restored saved photo: {photo_path}")
        
        # Restore saved user data (name, DOB, address, etc.)
        if 'user_data' in all_state:
            user_data_state = all_state['user_data']
            saved_user_data = user_data_state.get('value', {})
            if saved_user_data:
                context.user_data['saved_user_data'] = saved_user_data
                logger.info(f"Restored saved user data: {saved_user_data}")
        
        # Restore current project
        if 'current_project' in all_state:
            current_project = all_state['current_project'].get('value', {})
            if current_project:
                context.user_data['current_project'] = current_project
                logger.info(f"Restored current project: {current_project.get('project_name')}")
        
        # Check for pending task (async function - need to await)
        try:
            pending_task = await continuous_exec.check_and_resume_task(user_id)
        except Exception as e:
            logger.warning(f"Error checking pending task: {e}")
            pending_task = None
        
        if pending_task:
            task_desc = pending_task.get('task_description', '')
            # If user is asking about their work, restore context
            if any(keyword in user_message.lower() for keyword in ['project', 'working', 'doing', 'id project', 'continue', 'resume', 'remember', 'were working']):
                restored_info = []
                if context.user_data.get('last_photo'):
                    restored_info.append("✅ Photo found")
                if context.user_data.get('saved_user_data'):
                    restored_info.append(f"✅ User data: {context.user_data['saved_user_data'].get('name', 'N/A')}")
                if current_project:
                    restored_info.append(f"✅ Project: {current_project.get('project_name')}")
                
                await update.message.reply_text(
                    f"📋 **Resuming Previous Task:**\n\n"
                    f"Task: {task_desc}\n"
                    f"Status: {pending_task.get('status', 'pending')}\n"
                    f"{chr(10).join(restored_info) if restored_info else '⚠️ No saved data found'}\n\n"
                    f"🔄 Continuing execution...",
                    parse_mode='Markdown'
                )
    except Exception as e:
        logger.warning(f"Could not restore state: {e}", exc_info=True)
    
    # Log user message for training data collection
    try:
        from datetime import datetime
        import json
        training_log = {
            'type': 'user_input',
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'username': update.effective_user.username or f"user_{user_id}",
            'first_name': update.effective_user.first_name or 'Unknown',
            'message': user_message,
            'message_length': len(user_message),
            'chat_id': update.effective_chat.id,
            'chat_type': update.effective_chat.type
        }
        logger.info(f"🎓 TRAINING_DATA | USER_INPUT | {json.dumps(training_log, ensure_ascii=False)}")
    except Exception as e:
        logger.warning(f"Error logging training data (user input): {e}")
    
    # Detect and save requested state if user mentions it (e.g., "I want a Florida state ID")
    message_lower = user_message.lower()
    state_keywords_detect = {
        'texas': ['texas', 'tx'],
        'florida': ['florida', 'fl'],
        'california': ['california', 'ca'],
        'new york': ['new york', 'ny', 'newyork'],
        'illinois': ['illinois', 'il'],
        'ohio': ['ohio', 'oh'],
        'pennsylvania': ['pennsylvania', 'pa'],
        'georgia': ['georgia', 'ga'],
        'michigan': ['michigan', 'mi']
    }
    
    # Check if message contains state ID request (e.g., "I want a Florida state ID")
    id_request_patterns = ['want', 'need', 'get', 'generate', 'create', 'make', 'check']
    has_id_request = any(pattern in message_lower for pattern in id_request_patterns)
    has_state_id_keywords = any(keyword in message_lower for keyword in ['state id', 'state id', 'driver license', 'driver\'s license', 'dl', 'id'])
    
    if has_id_request and has_state_id_keywords:
        for state, keywords in state_keywords_detect.items():
            if any(keyword in message_lower for keyword in keywords):
                try:
                    from user_state_manager import get_user_state_manager
                    state_mgr = get_user_state_manager(db)
                    state_mgr.save_state(user_id, 'requested_state', state)
                    logger.info(f"Detected and saved requested state from message: {state}")
                except Exception as e:
                    logger.warning(f"Could not save detected state: {e}")
                break
    
    # Check if user is blocked
    if db.is_blocked(user_id):
        blocked_text = """
╔═══════════════════════════════════════╗
║        🚫 ACCOUNT BLOCKED 🚫           ║
╚═══════════════════════════════════════╝

Your account has been blocked by an administrator.

If you believe this is an error, please contact support.
        """
        try:
            await update.message.reply_text(blocked_text, parse_mode='Markdown')
        except:
            pass
        return
    
    # AUTO-DETECT: Check if user has photo + ID data and wants to generate ID
    # First check context, then check saved state
    user_photo = context.user_data.get('last_photo')
    if not user_photo:
        # Try to restore from saved state
        try:
            from user_state_manager import get_user_state_manager
            state_mgr = get_user_state_manager(db)
            photo_state = state_mgr.get_state(user_id, 'last_photo')
            if photo_state and photo_state.get('value', {}).get('path'):
                user_photo = photo_state['value']['path']
                context.user_data['last_photo'] = user_photo
        except Exception as e:
            logger.warning(f"Could not restore photo from state: {e}")
    
    # CHECK FOR "SEND ME THE GENERATED ID" REQUEST
    message_lower = user_message.lower()
    if any(phrase in message_lower for phrase in ['send me the generated id', 'send me the id', 'where is the id', 'do you have the id', 'show me the id']):
        # Check if ID was already generated
        try:
            from user_state_manager import get_user_state_manager
            state_mgr = get_user_state_manager(db)
            
            # Check for delivered results
            pending_task = state_mgr.get_pending_task(user_id)
            if pending_task:
                delivered = pending_task.get('results_delivered', [])
                for result in delivered:
                    if result.get('type') == 'id_image' and result.get('path'):
                        id_path = result['path']
                        if Path(id_path).exists():
                            # Send existing ID
                            with open(id_path, 'rb') as f:
                                await update.message.reply_document(
                                    document=f,
                                    filename=Path(id_path).name,
                                    caption="✅ **Texas ID (Previously Generated)**"
                                )
                            logger.info(f"Sent previously generated ID: {id_path}")
                            return
            
            # Check workspace for generated ID files
            try:
                from user_workspace_manager import UserWorkspaceManager
                workspace_manager = UserWorkspaceManager.get_instance()
                user_workspace = workspace_manager.get_user_workspace(user_id)
            except ImportError:
                base_workspace = os.getenv('WORKSPACE_ROOT', os.getcwd())
                user_workspace = Path(os.path.join(base_workspace, f"user_{user_id}"))
            
            # Search for ID files
            id_files = list(user_workspace.rglob('*id*.png')) + list(user_workspace.rglob('*texas*.png'))
            if id_files:
                # Get most recent
                latest_id = max(id_files, key=lambda p: p.stat().st_mtime)
                with open(latest_id, 'rb') as f:
                    await update.message.reply_document(
                        document=f,
                        filename=latest_id.name,
                        caption="✅ **Texas ID Found**"
                    )
                logger.info(f"Sent found ID: {latest_id}")
                return
            
            # If no ID found, generate it using saved photo + data
            user_photo = context.user_data.get('last_photo')
            if not user_photo:
                photo_state = state_mgr.get_state(user_id, 'last_photo')
                if photo_state and photo_state.get('value', {}).get('path'):
                    user_photo = photo_state['value']['path']
                    context.user_data['last_photo'] = user_photo
            
            if user_photo and Path(user_photo).exists():
                # Get saved user data
                user_data = context.user_data.get('saved_user_data', {})
                if not user_data:
                    user_data_state = state_mgr.get_state(user_id, 'user_data')
                    if user_data_state:
                        user_data = user_data_state.get('value', {})
                
                if user_data:
                    await update.message.reply_text("🔄 Generating ID from saved photo and data...")
                    # Will fall through to ID generation below
                else:
                    await update.message.reply_text("❌ I have your photo but need name/DOB/address. Please provide:\n\nName: [Your Name]\nDOB: [MM/DD/YYYY]\nAddress: [Your Address]")
                    return
            else:
                await update.message.reply_text("❌ No photo found. Please upload a photo first.")
                return
        except Exception as e:
            logger.error(f"Error checking for generated ID: {e}", exc_info=True)
    
    if user_photo:
        from pathlib import Path as PathLib
        if PathLib(user_photo).exists():
            # Check if message contains ID-related keywords or data
            id_keywords = ['texas', 'florida', 'california', 'id', 'driver', 'license', 'dl', 'identification', 'generate id', 'create id', 'state id']
            has_id_keyword = any(keyword in message_lower for keyword in id_keywords)
            
            # Check saved state for requested state (from previous messages)
            requested_state_from_history = None
            try:
                from user_state_manager import get_user_state_manager
                state_mgr = get_user_state_manager(db)
                state_history = state_mgr.get_state(user_id, 'requested_state')
                if state_history and state_history.get('value'):
                    requested_state_from_history = state_history['value']
                    logger.info(f"Found saved requested state: {requested_state_from_history}")
            except Exception as e:
                logger.debug(f"Could not load requested state from history: {e}")
            
            # Also check current message for state keywords (in case user mentions state in data message)
            state_keywords_check = {
                'texas': ['texas', 'tx'],
                'florida': ['florida', 'fl'],
                'california': ['california', 'ca'],
                'new york': ['new york', 'ny', 'newyork'],
                'illinois': ['illinois', 'il'],
                'ohio': ['ohio', 'oh'],
                'pennsylvania': ['pennsylvania', 'pa'],
                'georgia': ['georgia', 'ga'],
                'michigan': ['michigan', 'mi']
            }
            
            # If state detected in current message, save it
            for state, keywords in state_keywords_check.items():
                if any(keyword in message_lower for keyword in keywords):
                    try:
                        from user_state_manager import get_user_state_manager
                        state_mgr = get_user_state_manager(db)
                        state_mgr.save_state(user_id, 'requested_state', state)
                        requested_state_from_history = state
                        logger.info(f"Detected and saved state from current message: {state}")
                    except Exception as e:
                        logger.warning(f"Could not save detected state: {e}")
                    break
            
            # Check if message looks like ID data (name, DOB, address pattern)
            import re
            # More flexible name detection: "NAME" keyword or capitalized words at start
            has_name = bool(re.search(r'(?:name[:\s]+)?([A-Z][A-Z\s]+)', user_message)) or bool(re.search(r'^([A-Z][A-Z\s]{3,})', user_message))
            # DOB detection: MM/DD/YYYY or MM-DD-YYYY
            has_dob = bool(re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', user_message))
            # Address detection: number + street name (Rd, St, Ave, Road, Street, etc.)
            has_address = bool(re.search(r'\d+\s+[A-Za-z]+.*?(?:rd|st|ave|road|street|blvd|boulevard|drive|dr|ln|lane|ct|court|way|pl|place)', user_message, re.I))
            
            # If user mentions ID or has ID data pattern, auto-generate
            if has_id_keyword or (has_name and (has_dob or has_address)):
                try:
                    # Extract user data from message OR use saved state
                    user_data = {}
                    
                    # First, try to get saved user data from state
                    saved_data = context.user_data.get('saved_user_data', {})
                    if not saved_data:
                        try:
                            from user_state_manager import get_user_state_manager
                            state_mgr = get_user_state_manager(db)
                            user_data_state = state_mgr.get_state(user_id, 'user_data')
                            if user_data_state:
                                saved_data = user_data_state.get('value', {})
                        except Exception as e:
                            logger.warning(f"Could not load saved user data: {e}")
                    
                    if saved_data:
                        user_data.update(saved_data)
                        logger.info(f"Using saved user data: {user_data}")
                    
                    # Then, extract/override from current message
                    # Extract name - prioritize "Name:" pattern, then first line
                    # Pattern: "Name: Dawn Price" - match everything after "Name:" until newline
                    name_match = re.search(r'(?:^|\n)\s*name[:\s]+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+)', user_message, re.I | re.MULTILINE)
                    if not name_match:
                        # Try pattern without "Name:" keyword (first capitalized words at start)
                        name_match = re.search(r'^([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+)', user_message, re.MULTILINE)
                    if name_match:
                        name = name_match.group(1).strip().upper()
                        # Remove "NAME" keyword if present
                        name = re.sub(r'^NAME\s+', '', name, flags=re.I)
                        # Don't use if it's just "DOB" or other keywords, and require at least 2 words
                        excluded_keywords = ['DOB', 'ADDRESS', 'LICENSE', 'EXPIRATION', 'ISSUE', 'SEX', 'HEIGHT', 'WEIGHT', 'CLASS', 'RESTRICTIONS', 'DATE']
                        if name and name not in excluded_keywords and len(name.split()) >= 2:
                            user_data['name'] = name
                            logger.info(f"Extracted name: {name}")
                    
                    # Extract DOB
                    dob_match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', user_message)
                    if dob_match:
                        month, day, year = dob_match.groups()
                        if len(year) == 2:
                            year = '20' + year if int(year) < 50 else '19' + year
                        user_data['dob'] = f"{month}/{day}/{year}"
                    
                    # Extract address - more flexible pattern
                    address_match = re.search(r'(\d+\s+[A-Za-z\s]+(?:rd|st|ave|road|street|blvd|boulevard|drive|dr|ln|lane|ct|court|way|pl|place)[^,\n]*)', user_message, re.I)
                    if address_match:
                        full_address = address_match.group(1).strip()
                        # Try to extract city, state, zip if present
                        city_state_zip = re.search(r',\s*([A-Za-z]+),?\s*([A-Z]{2})?\s*(\d{5})?', user_message[address_match.end():], re.I)
                        if city_state_zip:
                            city = city_state_zip.group(1).strip() if city_state_zip.group(1) else ""
                            state = city_state_zip.group(2).strip() if city_state_zip.group(2) else ""
                            zip_code = city_state_zip.group(3).strip() if city_state_zip.group(3) else ""
                            user_data['address'] = full_address
                            if city:
                                user_data['city'] = city
                            if state:
                                user_data['state'] = state
                            if zip_code:
                                user_data['zip'] = zip_code
                        else:
                            user_data['address'] = full_address
                    else:
                        # Fallback: try to find address pattern without street type
                        address_match = re.search(r'(\d+\s+[A-Za-z\s]+)(?:,\s*([A-Za-z]+))?(?:,\s*([A-Z]{2}))?(?:\s+(\d{5}))?', user_message, re.I)
                        if address_match:
                            street = address_match.group(1).strip()
                            city = address_match.group(2).strip() if address_match.group(2) else ""
                            state = address_match.group(3).strip() if address_match.group(3) else ""
                            zip_code = address_match.group(4).strip() if address_match.group(4) else ""
                            user_data['address'] = street
                            if city:
                                user_data['city'] = city
                            if state:
                                user_data['state'] = state
                            if zip_code:
                                user_data['zip'] = zip_code
                    
                    # Detect which state ID the user wants from message
                    state_keywords = {
                        'texas': ['texas', 'tx'],
                        'florida': ['florida', 'fl'],
                        'california': ['california', 'ca'],
                        'new york': ['new york', 'ny', 'newyork'],
                        'illinois': ['illinois', 'il'],
                        'ohio': ['ohio', 'oh'],
                        'pennsylvania': ['pennsylvania', 'pa'],
                        'georgia': ['georgia', 'ga'],
                        'michigan': ['michigan', 'mi']
                    }
                    
                    requested_state = None
                    for state, keywords in state_keywords.items():
                        if any(keyword in message_lower for keyword in keywords):
                            requested_state = state
                            break
                    
                    # Also check user_data for state
                    if not requested_state and user_data.get('state'):
                        state_abbr = user_data['state'].upper()
                        state_map = {'TX': 'texas', 'FL': 'florida', 'CA': 'california', 'NY': 'new york', 
                                    'IL': 'illinois', 'OH': 'ohio', 'PA': 'pennsylvania', 'GA': 'georgia', 'MI': 'michigan'}
                        if state_abbr in state_map:
                            requested_state = state_map[state_abbr]
                    
                    # Default to Texas if no state specified
                    if not requested_state:
                        requested_state = 'texas'
                    
                    # Check database for the requested state template
                    from template_manager import get_template_manager
                    tm = get_template_manager(db)
                    
                    # Search for state-specific ID template
                    template = None
                    all_templates = tm.list_templates(template_type='id')
                    for t in all_templates:
                        if isinstance(t, dict):
                            name = t.get('name', '').lower()
                            desc = t.get('description', '').lower()
                            # Check if template matches requested state
                            if requested_state in name or requested_state in desc:
                                template = t
                                break
                    
                    # If no state-specific template found, try to get any ID template
                    if not template:
                        for t in all_templates:
                            if isinstance(t, dict):
                                name = t.get('name', '').lower()
                                if 'id' in name or 'driver' in name or 'license' in name:
                                    template = t
                                    break
                    
                    # Generate template name based on state
                    template_name_map = {
                        'texas': 'texas_dl',
                        'florida': 'florida_dl',
                        'california': 'california_dl',
                        'new york': 'newyork_id',
                        'illinois': 'illinois_dl',
                        'ohio': 'ohio_dl',
                        'pennsylvania': 'pennsylvania_dl',
                        'georgia': 'georgia_dl',
                        'michigan': 'michigan_dl'
                    }
                    template_name = template.get('name', template_name_map.get(requested_state, 'texas_dl')) if template else template_name_map.get(requested_state, 'texas_dl')
                    
                    # Save user data to state for persistence
                    try:
                        from user_state_manager import get_user_state_manager
                        state_mgr = get_user_state_manager(db)
                        state_mgr.save_state(user_id, 'user_data', user_data)
                        logger.info(f"Saved user data to state: {user_data}")
                    except Exception as e:
                        logger.warning(f"Could not save user data to state: {e}")
                    
                    # Generate ID
                    state_display = requested_state.replace('_', ' ').title() if requested_state else 'ID'
                    await update.message.reply_text(f"🔄 Detected photo + ID data! Generating {state_display} ID...")
                    
                    from id_template_processor import get_id_processor
                    id_processor = get_id_processor()
                    
                    filepath = id_processor.process_texas_id_with_photo(
                        user_photo,
                        template_name=template_name,
                        user_data=user_data
                    )
                    
                    if filepath and PathLib(filepath).exists():
                        # Verify file is not empty
                        file_size = PathLib(filepath).stat().st_size
                        if file_size == 0:
                            logger.error(f"Generated ID file is empty: {filepath}")
                            await update.message.reply_text("❌ Generated ID file is empty. Please try again.")
                            return
                        
                        # Send the generated ID as photo (better display in Telegram)
                        file_ext = PathLib(filepath).suffix.lower()
                        if file_ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                            # Send as photo for better Telegram display
                            with open(filepath, 'rb') as f:
                                await update.message.reply_photo(
                                    photo=f,
                                    caption=f"✅ **{state_display} ID Generated**\n\n"
                                           f"Name: {user_data.get('name', 'N/A')}\n"
                                           f"DOB: {user_data.get('dob', 'N/A')}\n"
                                           f"Address: {user_data.get('address', 'N/A')}",
                                    parse_mode='Markdown'
                                )
                        else:
                            # Send as document for non-image formats
                            with open(filepath, 'rb') as f:
                                await update.message.reply_document(
                                    document=f,
                                    filename=PathLib(filepath).name,
                                    caption=f"✅ **{state_display} ID Generated**\n\n"
                                           f"Name: {user_data.get('name', 'N/A')}\n"
                                           f"DOB: {user_data.get('dob', 'N/A')}\n"
                                           f"Address: {user_data.get('address', 'N/A')}",
                                    parse_mode='Markdown'
                                )
                        logger.info(f"Auto-generated and sent ID: {filepath} (size: {file_size} bytes)")
                        
                        # Mark result as delivered in state
                        try:
                            from user_state_manager import get_user_state_manager
                            state_mgr = get_user_state_manager(db)
                            state_mgr.mark_result_delivered(user_id, 'id_image', filepath)
                            state_mgr.clear_pending_task(user_id)
                        except Exception as e:
                            logger.warning(f"Could not update state: {e}")
                        
                        # Keep photo in state for future use (don't delete from context)
                        return
                    else:
                        logger.warning(f"ID generation failed, filepath: {filepath}")
                        # Continue to normal message handling
                except Exception as e:
                    logger.error(f"Error auto-generating ID: {e}", exc_info=True)
                    # Continue to normal message handling
    
    # Check if admin is searching for a user by ID
    pending_search_key = f'pending_search_{user_id}'
    if pending_search_key in context.user_data:
        if not db.is_admin(user_id):
            del context.user_data[pending_search_key]
            return
        
        # Try to parse user ID
        try:
            search_user_id = int(user_message.strip())
            
            # Get user info
            conn = db.get_connection()
            cursor = execute_db_query(conn, "SELECT * FROM users WHERE user_id = ?", (search_user_id,))
            user = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if not user:
                await update.message.reply_text(f"❌ User ID `{search_user_id}` not found.", parse_mode='Markdown')
                del context.user_data[pending_search_key]
                return
            
            user = dict(user)
            user_name = user.get('first_name', 'N/A') or f"User {search_user_id}"
            
            # Get user stats
            stats = db.get_user_usage_stats(search_user_id)
            
            # Format plan type
            plan_type = stats.get('plan_type', 'free')
            if plan_type == 'free':
                plan_display = "🆓 FREE"
            elif plan_type.startswith('Temp'):
                plan_display = f"⏱️ {plan_type.upper()}"
            elif stats.get('is_admin'):
                plan_display = "👑 ADMIN"
            else:
                plan_display = f"💎 {plan_type.upper()}"
            
            # Format requests
            requests_limit = stats.get('requests_limit', 0)
            requests_used = stats.get('requests_used', 0)
            remaining = stats.get('remaining', 0)
            
            if requests_limit == float('inf'):
                requests_display = "♾️ Unlimited"
            else:
                requests_display = f"{requests_used}/{requests_limit} (Remaining: {remaining})"
            
            search_result_text = f"""
╔═══════════════════════════════════════╗
║      👤 USER FOUND 👤                  ║
╚═══════════════════════════════════════╝

┌─ USER INFO ───────────────────────────┐
│ Name: {user_name:<27} │
│ User ID: `{search_user_id}`            │
│ Username: @{user.get('username', 'N/A') or 'N/A':<24} │
└──────────────────────────────────────┘

┌─ SUBSCRIPTION STATUS ──────────────────┐
│ Plan: {plan_display:<27} │
│ Requests: {requests_display:<25} │
│ Status: {stats.get('status', 'active'):<26} │
└──────────────────────────────────────┘

**Actions:**
• View detailed status
• Upgrade user
• Free upgrade (downtime compensation)
            """
            
            keyboard = [
                [
                    InlineKeyboardButton("📊 View Status", callback_data=f"view_user_status_{search_user_id}"),
                    InlineKeyboardButton("🔧 Upgrade", callback_data=f"select_user_{search_user_id}")
                ],
                [
                    InlineKeyboardButton("🎁 Free Upgrade", callback_data=f"select_user_{search_user_id}_free")
                ],
                [
                    InlineKeyboardButton("🔍 Search Another", callback_data="admin_search_user"),
                    InlineKeyboardButton("👥 View All Users", callback_data="admin_users")
                ],
                [
                    InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard"),
                    InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(search_result_text, parse_mode='Markdown', reply_markup=reply_markup)
            del context.user_data[pending_search_key]
            return
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid user ID (numbers only).", parse_mode='Markdown')
            return
        except Exception as e:
            logger.error(f"Error searching for user: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)}", parse_mode='Markdown')
            del context.user_data[pending_search_key]
            return
    
    # Check if admin is entering custom request amount for upgrade
    pending_key = f'pending_upgrade_{user_id}'
    if pending_key in context.user_data:
        if not db.is_admin(user_id):
            del context.user_data[pending_key]
            return
        
        pending = context.user_data[pending_key]
        target_user_id = pending['target_user_id']
        duration = pending['duration']
        user_name = pending['user_name']
        
        # Try to parse the number
        try:
            custom_requests = int(user_message.strip())
            if custom_requests < 1:
                await update.message.reply_text("❌ Please enter a number greater than 0.", parse_mode='Markdown')
                return
            if custom_requests > 999999:
                await update.message.reply_text("❌ Maximum is 999999 requests. Please enter a smaller number.", parse_mode='Markdown')
                return
            
            # Parse duration
            if duration == "10min":
                duration_minutes = 10
                duration_days = None
                duration_text = "10 minutes"
            elif duration == "1day":
                duration_minutes = None
                duration_days = 1
                duration_text = "1 day"
            elif duration == "7days":
                duration_minutes = None
                duration_days = 7
                duration_text = "7 days"
            else:
                await update.message.reply_text("❌ Invalid duration.", parse_mode='Markdown')
                del context.user_data[pending_key]
                return
            
            # Create subscription
            logger.info(f"Creating custom subscription: user {target_user_id}, {custom_requests} requests, {duration_text}")
            sub_id = db.create_temporary_subscription(
                target_user_id,
                requests_limit=custom_requests,
                duration_minutes=duration_minutes,
                duration_days=duration_days
            )
            
            if not sub_id:
                await update.message.reply_text("❌ Failed to create subscription. Please try again.", parse_mode='Markdown')
                del context.user_data[pending_key]
                return
            
            # Get subscription details
            sub = db.get_user_subscription(target_user_id)
            if not sub:
                await update.message.reply_text("❌ Subscription created but not found. Please check status.", parse_mode='Markdown')
                del context.user_data[pending_key]
                return
            
            # Calculate expiration
            from datetime import datetime
            try:
                end_date_str = sub['end_date']
                if isinstance(end_date_str, str):
                    if 'Z' in end_date_str or '+' in end_date_str:
                        end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                    else:
                        end_date = datetime.strptime(end_date_str, '%Y-%m-%d %H:%M:%S')
                else:
                    end_date = end_date_str
                expires_text = end_date.strftime('%Y-%m-%d %H:%M')
            except:
                expires_text = str(sub['end_date'])
            
            # Send success message (with free upgrade indicator if applicable)
            if is_free_upgrade:
                success_text = f"""
╔═══════════════════════════════════════╗
║   🎁 FREE UPGRADE SUCCESSFUL 🎁         ║
╚═══════════════════════════════════════╝

┌─ UPGRADE DETAILS ────────────────────┐
│ User: {user_name:<27} │
│ User ID: `{target_user_id}`          │
│ Duration: {duration_text}             │
│ Requests: {custom_requests} requests  │
│ Type: 🎁 FREE (Downtime Compensation) │
│ Expires: {expires_text}              │
└──────────────────────────────────────┘

✅ User has been upgraded for FREE!
📧 Notification will be sent to user.
Subscription will expire automatically.
                """
            else:
                success_text = f"""
╔═══════════════════════════════════════╗
║   ✅ USER UPGRADED SUCCESSFULLY ✅      ║
╚═══════════════════════════════════════╝

┌─ UPGRADE DETAILS ────────────────────┐
│ User: {user_name:<27} │
│ User ID: `{target_user_id}`          │
│ Duration: {duration_text}             │
│ Requests: {custom_requests} requests  │
│ Expires: {expires_text}              │
└──────────────────────────────────────┘

✅ User has been upgraded!
📧 Notification will be sent to user.
Subscription will expire automatically.
                """
            
            await update.message.reply_text(success_text, parse_mode='Markdown')
            
            # Send notification to upgraded user
            try:
                if is_free_upgrade:
                    notification_text = f"""
╔═══════════════════════════════════════╗
║   🎁 FREE UPGRADE - DOWNTIME COMP 🎁   ║
╚═══════════════════════════════════════╝

┌─ UPGRADE DETAILS ────────────────────┐
│ Duration: {duration_text}             │
│ Requests: {custom_requests} requests  │
│ Type: 🎁 FREE (Downtime Compensation) │
│ Expires: {expires_text}              │
└──────────────────────────────────────┘

✅ Your account has been upgraded for FREE!
This is compensation for the recent bot downtime.

📋 What's Next:
• Use /status to check your new plan
• Start using your upgraded requests
• Subscription will expire automatically

💡 Thank you for your patience! 🚀
                    """
                else:
                    notification_text = f"""
╔═══════════════════════════════════════╗
║   🎉 ACCOUNT UPGRADED! 🎉              ║
╚═══════════════════════════════════════╝

┌─ UPGRADE DETAILS ────────────────────┐
│ Duration: {duration_text}             │
│ Requests: {custom_requests} requests  │
│ Expires: {expires_text}              │
└──────────────────────────────────────┘

✅ Your account has been upgraded successfully!

📋 What's Next:
• Use /status to check your new plan
• Start using your upgraded requests
• Subscription will expire automatically

💡 Remember: This is a temporary upgrade.
   Make the most of it! 🚀
                    """
                
                await update.message.bot.send_message(
                    chat_id=target_user_id,
                    text=notification_text,
                    parse_mode='Markdown'
                )
                logger.info(f"Sent upgrade notification to user {target_user_id}")
            except Exception as e:
                logger.error(f"Failed to send notification to user {target_user_id}: {e}")
            
            # Clear pending upgrade
            del context.user_data[pending_key]
            return
            
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid number (e.g., 250).", parse_mode='Markdown')
            return
    
    # Get or create user
    db.get_or_create_user(
        user_id,
        update.effective_user.username,
        update.effective_user.first_name
    )
    
    # Check usage limits and track usage
    try:
        usage_ok = db.increment_usage(user_id)
        if usage_ok:
            logger.info(f"Usage incremented successfully for user {user_id}")
        else:
            logger.warning(f"Usage limit reached for user {user_id}")
    except AttributeError:
        # Fallback if increment_usage not available yet (during deployment)
        logger.warning("increment_usage not available, allowing message")
        usage_ok = True
    except Exception as e:
        # Log any other errors but still allow the message
        logger.error(f"Error incrementing usage for user {user_id}: {e}", exc_info=True)
        # Still allow message but log the error
        usage_ok = True
    
    if not usage_ok:
        stats = db.get_user_usage_stats(user_id)
        limit_text = f"""
❌ *Limit Reached*

You've used all your available requests.

*Current:* {stats['requests_used']}/{stats['requests_limit']}

*Upgrade Options:*
• Use `/plans` to view subscription plans
• Use `/subscribe` to upgrade

*Free tier:* 3 one-time requests (no daily refresh)
*To continue using the bot, please subscribe to a plan.*
        """
        keyboard = [
            [InlineKeyboardButton("💎 View Plans", callback_data="menu_plans")],
            [InlineKeyboardButton("📊 My Status", callback_data="menu_status")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(limit_text, parse_mode='Markdown', reply_markup=reply_markup)
        return
    
    try:
        # Get user's brain instance
        brain = get_user_brain(user_id)
        
        # Use desktop AI handler (full desktop app approach)
        try:
            try:
                from desktop_ai_handler import DesktopAIHandler
                DESKTOP_HANDLER_AVAILABLE = True
            except ImportError:
                DESKTOP_HANDLER_AVAILABLE = False
                logger.warning("DesktopAIHandler not available, using basic streaming")
            
            if not DESKTOP_HANDLER_AVAILABLE:
                # Fallback to basic streaming without DesktopAIHandler
                raise ImportError("DesktopAIHandler not available")
            
            # Get workspace for user (isolated per-user workspace for concurrent safety)
            # Use UserWorkspaceManager for proper isolation
            try:
                from user_workspace_manager import UserWorkspaceManager
                workspace_manager = UserWorkspaceManager.get_instance()
                user_workspace = workspace_manager.get_user_workspace(user_id)
                workspace = str(user_workspace)
            except ImportError:
                # Fallback if UserWorkspaceManager not available
                base_workspace = os.getenv('WORKSPACE_ROOT', os.getcwd())
                workspace = os.path.join(base_workspace, f"user_{user_id}")
                os.makedirs(workspace, exist_ok=True)
                logger.warning("UserWorkspaceManager not available, using fallback workspace isolation")
            
            if DESKTOP_HANDLER_AVAILABLE:
                logger.info(f"Initializing DesktopAIHandler for user {user_id} with workspace: {workspace}")
                desktop_handler = DesktopAIHandler(brain, workspace_root=workspace, user_id=user_id)
                logger.info(f"DesktopAIHandler initialized successfully for user {user_id}")
            else:
                raise ImportError("DesktopAIHandler not available")
            
            # Load memory context and store user message
            if SECURE_MEMORY_AVAILABLE and secure_memory:
                try:
                    from datetime import datetime as dt
                    existing_history = secure_memory.get_chat_history(user_id) or []
                    existing_history.append({
                        'role': 'user',
                        'content': user_message,
                        'timestamp': dt.now().isoformat()
                    })
                    secure_memory.store_chat_history(user_id, existing_history)
                except Exception as e:
                    logger.warning(f"Error storing user message: {e}")
            
            # Start typing indicator
            typing_task = asyncio.create_task(
                send_typing_continuously(context, update.effective_chat.id)
            )
            
            try:
                # Store task information for summary generation
                context.user_data['task_start_time'] = time.time()
                context.user_data['last_task_description'] = user_message
                context.user_data['last_task_results'] = {}
                
                # Create progress streamer for long tasks
                try:
                    from progress_streamer import create_progress_streamer
                    progress_streamer = create_progress_streamer(update=update, context=context, update_interval=15)
                    context.user_data['progress_streamer'] = progress_streamer
                except Exception as e:
                    logger.warning(f"Could not create progress streamer: {e}")
                    progress_streamer = None
                
                # CONTINUOUS EXECUTION: Keep executing until results are delivered
                try:
                    from continuous_executor import get_continuous_executor
                    from user_state_manager import get_user_state_manager
                    
                    continuous_exec = get_continuous_executor(max_iterations=5, check_interval=3.0)
                    state_mgr = get_user_state_manager(db)
                    
                    # Determine expected results based on task
                    expected_results = []
                    message_lower = user_message.lower()
                    if 'id' in message_lower or 'driver' in message_lower or 'license' in message_lower:
                        expected_results = ['id_image', 'file']
                    elif 'generate' in message_lower or 'create' in message_lower:
                        expected_results = ['file', 'script']
                    elif 'scan' in message_lower or 'check' in message_lower:
                        expected_results = ['file', 'report']
                    else:
                        expected_results = ['message']  # At minimum, expect a response message
                    
                    # Save current project if detected
                    if 'project' in message_lower or 'working' in message_lower:
                        # Try to detect project name
                        project_name = f"user_{user_id}_project_{int(time.time())}"
                        state_mgr.save_current_project(user_id, project_name, 'general', workspace)
                    
                    # Execute with continuous checking and command execution
                    async def execute_task():
                        """Execute task with automatic command execution (Cursor-style)"""
                        try:
                            # Import command execution modules
                            from command_executor import get_command_executor
                            from ai_response_parser import get_ai_response_parser
                            from auto_retry_manager import get_auto_retry_manager
                            from telegram_rate_limiter import get_telegram_rate_limiter
                            
                            command_executor = get_command_executor(workspace)
                            response_parser = get_ai_response_parser()
                            retry_manager = get_auto_retry_manager()
                            rate_limiter = get_telegram_rate_limiter()
                            
                            # Get initial AI response
                            if CONCURRENCY_MANAGER_AVAILABLE and concurrency_manager:
                                async def process_message():
                                    return await desktop_handler.handle_with_streaming(
                                        user_message,
                                        update,
                                        context
                                    )
                                
                                ai_response = await concurrency_manager.process_request(
                                    user_id,
                                    process_message
                                )
                            else:
                                ai_response = await desktop_handler.handle_with_streaming(
                                    user_message,
                                    update,
                                    context
                                )
                            
                            # Parse AI response for commands
                            parsed = response_parser.parse_ai_response(ai_response)
                            
                            # If no commands, return response as-is
                            if not parsed['commands']:
                                logger.debug("No commands found in AI response")
                                return ai_response
                            
                            # Execute commands automatically
                            logger.info(f"Found {len(parsed['commands'])} commands in AI response, executing...")
                            
                            execution_results = []
                            conversation_context = user_message
                            max_iterations = 10
                            iteration = 0
                            
                            while iteration < max_iterations:
                                iteration += 1
                                
                                # Update progress
                                if progress_streamer:
                                    progress_streamer.update_progress(
                                        f"Executing commands (iteration {iteration}/{max_iterations})",
                                        progress_pct=int((iteration / max_iterations) * 50),
                                        details=f"Found {len(parsed['commands'])} commands"
                                    )
                                    await progress_streamer.send_progress_update()
                                
                                # Execute all commands
                                for i, command in enumerate(parsed['commands'], 1):
                                    logger.info(f"Executing command {i}/{len(parsed['commands'])}: {command}")
                                    
                                    # Execute with retry
                                    max_retries = 3
                                    executed = False
                                    
                                    for attempt in range(max_retries):
                                        result = command_executor.execute_command(
                                            command,
                                            cwd=workspace,
                                            timeout=300,
                                            verify=True
                                        )
                                        
                                        execution_results.append(result)
                                        
                                        # Check if verified (actually ran)
                                        if result.get('verified', False) and result.get('success', False):
                                            executed = True
                                            logger.info(f"Command {i} executed and verified: {command}")
                                            break
                                        else:
                                            # Try alternative
                                            if attempt < max_retries - 1:
                                                error_msg = result.get('error', '') or result.get('stderr', '') or 'Verification failed'
                                                alt_command = retry_manager.retry_with_alternative(command, error_msg, attempt + 1)
                                                if alt_command and alt_command != command:
                                                    logger.info(f"Trying alternative: {alt_command}")
                                                    command = alt_command
                                                await asyncio.sleep(1)
                                    
                                    if not executed:
                                        logger.warning(f"Command {i} failed after {max_retries} attempts: {command}")
                                
                                # Format results for AI
                                results_summary = "\n".join([
                                    f"Command: {r['command']}\n"
                                    f"Exit code: {r.get('exit_code', 'N/A')}\n"
                                    f"Output: {r.get('stdout', '')[:500]}\n"
                                    f"Error: {r.get('stderr', '')[:200]}\n"
                                    f"Verified: {'Yes' if r.get('verified', False) else 'No'}\n"
                                    for r in execution_results[-len(parsed['commands']):]
                                ])
                                
                                # Check if task complete
                                if parsed['is_complete']:
                                    logger.info("Task marked as complete by AI")
                                    break
                                
                                # Feed results back to AI and get next response
                                next_prompt = f"""Previous commands executed. Results:
{results_summary}

Continue with next steps. If task is complete, say "Task complete"."""
                                
                                # Get next AI response
                                try:
                                    next_response = ""
                                    for chunk in brain.chat(next_prompt):
                                        next_response += chunk
                                    
                                    # Parse next response
                                    parsed = response_parser.parse_ai_response(next_response)
                                    
                                    # If no more commands and task complete, break
                                    if not parsed['commands'] and parsed['is_complete']:
                                        logger.info("Task complete (no more commands)")
                                        break
                                    
                                    # If no more commands but not complete, wait a bit and check again
                                    if not parsed['commands']:
                                        await asyncio.sleep(2)
                                        # Try one more time
                                        final_response = ""
                                        for chunk in brain.chat("Are there any more commands to execute? If task is complete, say 'Task complete'."):
                                            final_response += chunk
                                        final_parsed = response_parser.parse_ai_response(final_response)
                                        if final_parsed['is_complete'] or not final_parsed['commands']:
                                            break
                                    
                                except Exception as e:
                                    logger.error(f"Error getting next AI response: {e}", exc_info=True)
                                    break
                                
                                # Brief delay
                                await asyncio.sleep(1)
                            
                            # Return final response with execution summary
                            final_summary = f"{ai_response}\n\n**Commands Executed:** {len(execution_results)}\n**Verified:** {sum(1 for r in execution_results if r.get('verified', False))}"
                            return final_summary
                            
                        except Exception as e:
                            logger.error(f"Error in command execution: {e}", exc_info=True)
                            # Fallback to standard execution
                            if CONCURRENCY_MANAGER_AVAILABLE and concurrency_manager:
                                async def process_message():
                                    return await desktop_handler.handle_with_streaming(
                                        user_message,
                                        update,
                                        context
                                    )
                                
                                return await concurrency_manager.process_request(
                                    user_id,
                                    process_message
                                )
                            else:
                                return await desktop_handler.handle_with_streaming(
                                    user_message,
                                    update,
                                    context
                                )
                    
                    async def check_results(exec_result, expected, ws_path):
                        """Check if results were delivered"""
                        results = []
                        
                        # Check for files in workspace
                        if ws_path and Path(ws_path).exists():
                            workspace = Path(ws_path)
                            
                            # Check for ID images
                            if 'id_image' in expected:
                                id_files = list(workspace.rglob('*id*.png')) + list(workspace.rglob('*texas*.png'))
                                if id_files:
                                    results.append({'type': 'id_image', 'path': str(id_files[0])})
                            
                            # Check for generated files
                            if 'file' in expected:
                                py_files = list(workspace.rglob('*.py'))
                                json_files = list(workspace.rglob('*.json'))
                                if py_files or json_files:
                                    results.append({'type': 'file', 'path': str(py_files[0] if py_files else json_files[0])})
                        
                        # Check if response was sent (basic check)
                        if 'message' in expected and exec_result:
                            results.append({'type': 'message', 'content': exec_result[:100]})
                        
                        return results
                    
                    # Execute continuously until results delivered
                    exec_result = await continuous_exec.execute_until_delivered(
                        task_description=user_message,
                        execution_function=execute_task,
                        expected_results=expected_results,
                        result_checker=check_results,
                        user_id=user_id,
                        workspace_path=workspace
                    )
                    
                    cleaned_response = exec_result.get('execution_result', '')
                    delivered = exec_result.get('delivered_results', [])
                    
                    if exec_result.get('success'):
                        logger.info(f"Task completed successfully: {len(delivered)} results delivered")
                    else:
                        logger.warning(f"Task may not be complete: {exec_result.get('message', 'Unknown')}")
                    
                except Exception as e:
                    logger.warning(f"Continuous execution not available, using standard execution: {e}")
                    # Fallback to standard execution with command execution
                    try:
                        # Get AI response first
                        ai_response = ""
                        for chunk in brain.chat(user_message):
                            ai_response += chunk
                        
                        # Parse and execute commands automatically
                        try:
                            from command_executor import get_command_executor
                            from ai_response_parser import get_ai_response_parser
                            from auto_retry_manager import get_auto_retry_manager
                            
                            command_executor = get_command_executor(workspace)
                            response_parser = get_ai_response_parser()
                            retry_manager = get_auto_retry_manager()
                            
                            # Parse AI response
                            parsed = response_parser.parse_ai_response(ai_response)
                            
                            # Execute commands if found
                            if parsed['commands']:
                                logger.info(f"Found {len(parsed['commands'])} commands, executing...")
                                execution_results = []
                                
                                for i, command in enumerate(parsed['commands'], 1):
                                    logger.info(f"Executing command {i}/{len(parsed['commands'])}: {command}")
                                    
                                    # Execute with retry
                                    max_retries = 3
                                    for attempt in range(max_retries):
                                        result = command_executor.execute_command(
                                            command,
                                            cwd=workspace,
                                            timeout=300,
                                            verify=True
                                        )
                                        execution_results.append(result)
                                        
                                        if result.get('verified', False) and result.get('success', False):
                                            logger.info(f"Command {i} executed successfully")
                                            break
                                        elif attempt < max_retries - 1:
                                            error_msg = result.get('error', '') or result.get('stderr', '') or 'Verification failed'
                                            alt_command = retry_manager.retry_with_alternative(command, error_msg, attempt + 1)
                                            if alt_command and alt_command != command:
                                                logger.info(f"Trying alternative: {alt_command}")
                                                command = alt_command
                                            await asyncio.sleep(1)
                                
                                # Format results and append to response
                                if execution_results:
                                    results_summary = "\n\n**Execution Results:**\n"
                                    for r in execution_results:
                                        results_summary += f"`{r['command']}` → Exit: {r.get('exit_code', 'N/A')}, Verified: {'Yes' if r.get('verified', False) else 'No'}\n"
                                        if r.get('stdout'):
                                            results_summary += f"Output: {r['stdout'][:200]}...\n"
                                    ai_response += results_summary
                        except Exception as cmd_err:
                            logger.warning(f"Command execution failed: {cmd_err}", exc_info=True)
                            # Continue with original response if command execution fails
                        
                        cleaned_response = ai_response
                    except Exception as fallback_err:
                        logger.error(f"Fallback execution failed: {fallback_err}", exc_info=True)
                        # Last resort: just use brain directly
                        cleaned_response = ""
                        for chunk in brain.chat(user_message):
                            cleaned_response += chunk
                
                # Update task results if available
                if hasattr(desktop_handler, 'last_task_results'):
                    context.user_data['last_task_results'] = desktop_handler.last_task_results
                
                # Store AI response in secure memory (with vector embeddings if available)
                # Use timeout to prevent hanging on slow memory operations
                if SECURE_MEMORY_AVAILABLE and secure_memory:
                    try:
                        logger.info(f"Storing AI response in memory for user {user_id}")
                        from datetime import datetime as dt
                        
                        # Store in executor with timeout (non-blocking)
                        def store_sync():
                            try:
                                # Use enhanced storage with embeddings if available
                                if hasattr(secure_memory, 'store_conversation_with_embedding'):
                                    # Store the full conversation (user message + response)
                                    secure_memory.store_conversation_with_embedding(
                                        user_id, user_message, response=cleaned_response,
                                        metadata={'source': 'telegram', 'chat_id': update.effective_chat.id}
                                    )
                                else:
                                    # Fallback to basic storage
                                    existing_history = secure_memory.get_chat_history(user_id) or []
                                    existing_history.append({
                                        'role': 'assistant',
                                        'content': cleaned_response,
                                        'timestamp': dt.now().isoformat()
                                    })
                                    secure_memory.store_chat_history(user_id, existing_history)
                                logger.info(f"Successfully stored AI response in memory")
                            except Exception as e:
                                logger.warning(f"Error storing AI response: {e}")
                        
                        # Run storage with timeout in executor (non-blocking)
                        try:
                            loop = asyncio.get_event_loop()
                            await asyncio.wait_for(
                                loop.run_in_executor(None, store_sync),
                                timeout=2.0
                            )
                        except asyncio.TimeoutError:
                            logger.warning(f"Memory storage timed out after 2s, skipping")
                        except Exception as e:
                            logger.warning(f"Error in memory storage: {e}")
                    except Exception as e:
                        logger.warning(f"Error storing AI response: {e}")
            finally:
                # Stop typing indicator
                logger.info(f"Cleaning up typing indicator for user {user_id}")
                typing_task.cancel()
                try:
                    await asyncio.wait_for(typing_task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                logger.info(f"Cleanup complete for user {user_id}")
            
            # SAVE STATE: Save current task state before sending results
            try:
                from user_state_manager import get_user_state_manager
                from datetime import datetime
                state_mgr = get_user_state_manager(db)
                
                # Save last task description
                if 'last_task_description' in context.user_data:
                    state_mgr.save_state(
                        user_id,
                        'last_task',
                        {
                            'description': context.user_data.get('last_task_description'),
                            'response': cleaned_response[:500] if cleaned_response else '',
                            'timestamp': datetime.now().isoformat()
                        },
                        workspace
                    )
            except Exception as e:
                logger.warning(f"Could not save task state: {e}")
            
            # Send screenshots if any
            screenshots = context.user_data.get('screenshots', [])
            if screenshots:
                try:
                    from pathlib import Path
                    for screenshot_path in screenshots:
                        if screenshot_path and Path(screenshot_path).exists():
                            try:
                                # Send as document (file) - better for downloading and sharing
                                # Users can download and save the screenshot file
                                with open(screenshot_path, 'rb') as f:
                                    await update.message.reply_document(
                                        document=f,
                                        filename=Path(screenshot_path).name,
                                        caption="📸 Screenshot captured"
                                    )
                                logger.info(f"Sent screenshot as file: {screenshot_path}")
                            except Exception as e:
                                logger.error(f"Failed to send screenshot as file: {e}")
                                # Fallback: try sending as photo if document fails
                                try:
                                    with open(screenshot_path, 'rb') as f:
                                        await update.message.reply_photo(
                                            photo=f,
                                            caption="📸 Screenshot captured"
                                        )
                                    logger.info(f"Sent screenshot as image (fallback): {screenshot_path}")
                                except Exception as e2:
                                    logger.error(f"Failed to send screenshot as image: {e2}")
                except Exception as e:
                    logger.error(f"Error sending screenshots: {e}")
            
            # Send generated files if any
            generated_files = context.user_data.get('generated_files', [])
            if generated_files:
                try:
                    from file_generator import is_file_size_valid, MAX_FILE_SIZE
                    from pathlib import Path
                    from task_summary_generator import get_task_summary_generator
                    import time
                    
                    # Get task information for summary
                    task_description = context.user_data.get('last_task_description', user_message)
                    task_results = context.user_data.get('last_task_results', {})
                    task_start_time = context.user_data.get('task_start_time', time.time())
                    task_duration = time.time() - task_start_time
                    
                    # Generate summary
                    summary_generator = get_task_summary_generator()
                    
                    # Prepare file information
                    file_info_list = []
                    for file_path in generated_files:
                        if not file_path or not Path(file_path).exists():
                            continue
                        
                        file_info = summary_generator.generate_file_usage_guide(file_path)
                        file_info_list.append(file_info)
                    
                    # Generate and send summary
                    if file_info_list:
                        summary_text = summary_generator.generate_summary(
                            task_description=task_description,
                            results=task_results,
                            files=file_info_list,
                            duration=task_duration,
                            status='complete'
                        )
                        
                        # Send summary as document
                        try:
                            from document_generator import get_document_generator
                            doc_gen = get_document_generator()
                            summary_file = doc_gen.generate_pdf(
                                summary_text,
                                filename=f"task_summary_{int(time.time())}.pdf",
                                title="Task Completion Summary"
                            )
                            
                            if summary_file and Path(summary_file).exists():
                                with open(summary_file, 'rb') as f:
                                    file_keyboard = ensure_mode_keyboard_at_bottom(user_id, context)
                                    await update.message.reply_document(
                                        document=f,
                                        filename=Path(summary_file).name,
                                        caption="📋 *Task Completion Summary*\n\nIncludes usage instructions and results overview",
                                        parse_mode='Markdown',
                                        reply_markup=file_keyboard
                                    )
                        except Exception as e:
                            logger.warning(f"Could not generate summary PDF, sending as text: {e}")
                            # Send summary as text message
                            summary_preview = summary_text[:3000] + ("..." if len(summary_text) > 3000 else "")
                            file_keyboard = ensure_mode_keyboard_at_bottom(user_id, context)
                            await update.message.reply_text(
                                f"📋 *Task Completion Summary*\n\n{summary_preview}",
                                parse_mode='Markdown',
                                reply_markup=file_keyboard
                            )
                    
                    # Send files with descriptions
                    for file_path in generated_files:
                        if not file_path or not Path(file_path).exists():
                            continue
                        
                        # Find file info
                        file_info = next((f for f in file_info_list if f['name'] == Path(file_path).name), None)
                        
                        # Check file size
                        if is_file_size_valid(file_path):
                            try:
                                with open(file_path, 'rb') as f:
                                    # Add mode keyboard to file sending
                                    file_keyboard = ensure_mode_keyboard_at_bottom(user_id, context)
                                    
                                    # Create caption with usage info
                                    caption = None
                                    if file_info:
                                        caption = f"📄 *{file_info['desc']}*\n\n*Usage:*\n```\n{file_info['usage']}\n```"
                                    
                                    await update.message.reply_document(
                                        document=f,
                                        filename=Path(file_path).name,
                                        caption=caption,
                                        parse_mode='Markdown',
                                        reply_markup=file_keyboard
                                    )
                                logger.info(f"Sent file: {file_path}")
                            except Exception as e:
                                logger.error(f"Failed to send file {file_path}: {e}")
                        else:
                            file_size = Path(file_path).stat().st_size
                            file_keyboard = ensure_mode_keyboard_at_bottom(user_id, context)
                            await update.message.reply_text(
                                f"⚠️ File `{Path(file_path).name}` is too large ({file_size / 1024 / 1024:.2f}MB). "
                                f"Maximum size is {MAX_FILE_SIZE / 1024 / 1024:.0f}MB.",
                                parse_mode='Markdown',
                                reply_markup=file_keyboard
                            )
                except Exception as e:
                    logger.error(f"Error sending files: {e}")
                
                # Clean up files after sending
                try:
                    if hasattr(desktop_handler, 'file_generator') and desktop_handler.file_generator:
                        desktop_handler.file_generator.cleanup_files(generated_files)
                except Exception as e:
                    logger.warning(f"Error cleaning up files: {e}")
            
            # Get updated stats
            stats = db.get_user_usage_stats(user_id)
            
            # Add usage info for free users
            if not stats.get('is_premium', False):
                usage_info = f"\n\n*Usage: {stats.get('today_usage', 0)}/4 today*"
                # Append to last message if possible
                try:
                    # Try to edit the last sent message to add usage info
                    # This is a best-effort attempt
                    pass  # Usage info can be added in next message if needed
                except:
                    pass
        except ImportError as e:
            logger.warning(f"Desktop AI handler not available: {e}, using basic streaming")
            # Fallback to basic streaming
            # Ensure time module is accessible (re-import to avoid shadowing issues)
            import time as time_module
            typing_task = asyncio.create_task(
                send_typing_continuously(context, update.effective_chat.id)
            )
            
            try:
                # Basic streaming fallback
                sent_message = None
                full_response = ""
                last_update_time = 0
                update_interval = 0.3
                chunk_buffer = ""
                buffer_size = 30
                
                for chunk in brain.chat(user_message):
                    full_response += chunk
                    chunk_buffer += chunk
                    
                    current_time = time_module.time()
                    should_update = (
                        current_time - last_update_time >= update_interval or
                        len(chunk_buffer) >= buffer_size
                    )
                    
                    if should_update:
                        cleaned_chunk = full_response.replace("[SMG-Forcer]:", "").replace("[HacxGPT]:", "").strip()
                        if not cleaned_chunk:
                            cleaned_chunk = "💭 Processing..."
                        
                        try:
                            if sent_message is None:
                                display_text = cleaned_chunk[:4000] if len(cleaned_chunk) > 4000 else cleaned_chunk
                                try:
                                    sent_message = await update.message.reply_text(display_text, parse_mode='Markdown')
                                except BadRequest:
                                    sent_message = await update.message.reply_text(display_text)
                            else:
                                display_text = cleaned_chunk[:4000] if len(cleaned_chunk) > 4000 else cleaned_chunk
                                try:
                                    await sent_message.edit_text(display_text, parse_mode='Markdown')
                                except BadRequest as e:
                                    if 'not modified' not in str(e).lower():
                                        if 'too long' in str(e).lower() and len(cleaned_chunk) > 4000:
                                            remaining = cleaned_chunk[4000:]
                                            if remaining:
                                                sent_message = await update.message.reply_text(remaining[:4000], parse_mode='Markdown')
                            
                            last_update_time = current_time
                            chunk_buffer = ""
                        except Exception as e:
                            logger.debug(f"Streaming error: {e}")
                
                # Final update
                cleaned_response = full_response.replace("[SMG-Forcer]:", "").replace("[HacxGPT]:", "").strip()
                if not cleaned_response:
                    cleaned_response = "No response generated."
                
                # Parse and execute commands automatically (Cursor-style)
                try:
                    from command_executor import get_command_executor
                    from ai_response_parser import get_ai_response_parser
                    from auto_retry_manager import get_auto_retry_manager
                    
                    # Get workspace
                    try:
                        from user_workspace_manager import UserWorkspaceManager
                        workspace_manager = UserWorkspaceManager.get_instance()
                        user_workspace = workspace_manager.get_user_workspace(user_id)
                        workspace = str(user_workspace)
                    except ImportError:
                        base_workspace = os.getenv('WORKSPACE_ROOT', os.getcwd())
                        workspace = os.path.join(base_workspace, f"user_{user_id}")
                        os.makedirs(workspace, exist_ok=True)
                    
                    command_executor = get_command_executor(workspace)
                    response_parser = get_ai_response_parser()
                    retry_manager = get_auto_retry_manager()
                    
                    # Parse AI response for commands
                    parsed = response_parser.parse_ai_response(cleaned_response)
                    
                    # Execute commands if found
                    if parsed['commands']:
                        logger.info(f"Found {len(parsed['commands'])} commands in response, executing...")
                        execution_results = []
                        
                        for i, command in enumerate(parsed['commands'], 1):
                            logger.info(f"Executing command {i}/{len(parsed['commands'])}: {command}")
                            
                            # Execute with retry
                            max_retries = 3
                            executed = False
                            
                            for attempt in range(max_retries):
                                result = command_executor.execute_command(
                                    command,
                                    cwd=workspace,
                                    timeout=300,
                                    verify=True
                                )
                                execution_results.append(result)
                                
                                if result.get('verified', False) and result.get('success', False):
                                    executed = True
                                    logger.info(f"Command {i} executed and verified")
                                    break
                                elif attempt < max_retries - 1:
                                    error_msg = result.get('error', '') or result.get('stderr', '') or 'Verification failed'
                                    alt_command = retry_manager.retry_with_alternative(command, error_msg, attempt + 1)
                                    if alt_command and alt_command != command:
                                        logger.info(f"Trying alternative: {alt_command}")
                                        command = alt_command
                                    await asyncio.sleep(1)
                            
                            if not executed:
                                logger.warning(f"Command {i} failed after {max_retries} attempts")
                        
                        # Append execution results to response
                        if execution_results:
                            results_summary = "\n\n**Execution Results:**\n"
                            for r in execution_results:
                                status = "✅" if r.get('verified', False) and r.get('success', False) else "❌"
                                results_summary += f"{status} `{r['command'][:60]}...`\n"
                                if r.get('stdout'):
                                    results_summary += f"   Output: {r['stdout'][:150]}...\n"
                                elif r.get('stderr'):
                                    results_summary += f"   Error: {r['stderr'][:150]}...\n"
                            cleaned_response += results_summary
                            
                            # Update sent message with results
                            if sent_message:
                                try:
                                    final_text = cleaned_response[:4000] if len(cleaned_response) > 4000 else cleaned_response
                                    await sent_message.edit_text(final_text, parse_mode='Markdown')
                                except BadRequest:
                                    pass
                except Exception as cmd_err:
                    logger.warning(f"Command execution failed: {cmd_err}", exc_info=True)
                    # Continue with original response if command execution fails
                
                if sent_message:
                    try:
                        final_text = cleaned_response[:4000] if len(cleaned_response) > 4000 else cleaned_response
                        await sent_message.edit_text(final_text, parse_mode='Markdown')
                        if len(cleaned_response) > 4000:
                            remaining = cleaned_response[4000:]
                            chunks = [remaining[i:i+4000] for i in range(0, len(remaining), 4000)]
                            for chunk in chunks:
                                await update.message.reply_text(chunk, parse_mode='Markdown')
                    except BadRequest:
                        pass
                else:
                    max_length = 4000
                    if len(cleaned_response) > max_length:
                        chunks = [cleaned_response[i:i+max_length] for i in range(0, len(cleaned_response), max_length)]
                        for chunk in chunks:
                            await safe_reply_text(update, chunk, parse_mode='Markdown')
                    else:
                        await safe_reply_text(update, cleaned_response, parse_mode='Markdown')
                
                # Add usage info
                stats = db.get_user_usage_stats(user_id)
                if not stats.get('is_premium', False):
                    await update.message.reply_text(f"*Usage: {stats.get('today_usage', 0)}/4 today*", parse_mode='Markdown')
            finally:
                typing_task.cancel()
                try:
                    await typing_task
                except asyncio.CancelledError:
                    pass
        except Exception as e:
            # Comprehensive error logging
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(f"❌ CRITICAL ERROR in desktop AI handler: {e}", exc_info=True)
            logger.error(f"❌ Error type: {type(e).__name__}")
            logger.error(f"❌ Full traceback:\n{error_traceback}")
            logger.error(f"❌ User ID: {user_id}, Message: {user_message[:200] if 'user_message' in locals() else 'N/A'}")
            logger.error(f"❌ Error occurred at: {traceback.format_exc()}")
            
            try:
                await safe_reply_text(
                    update,
                    f"❌ *Error occurred:* {str(e)[:500]}\n\n"
                    f"Error type: {type(e).__name__}\n\n"
                    f"Please try again or use /new to reset your session.",
                    parse_mode='Markdown'
                )
            except Exception as send_error:
                logger.error(f"❌ Failed to send error message: {send_error}", exc_info=True)
                logger.error(f"❌ Send error traceback:\n{traceback.format_exc()}")
            
    except ValueError as e:
        await safe_reply_text(
            update,
            f"❌ *Error:* {str(e)}",
            parse_mode='Markdown'
        )
    except Exception as e:
        # Comprehensive error logging
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"❌ CRITICAL ERROR handling message: {e}")
        logger.error(f"❌ Error type: {type(e).__name__}")
        logger.error(f"❌ Full traceback:\n{error_traceback}")
        user_id = update.effective_user.id if hasattr(update, 'effective_user') else 'unknown'
        user_message = update.message.text if update.message and update.message.text else 'N/A'
        logger.error(f"❌ User ID: {user_id}, Message: {user_message[:200]}")
        
        try:
            await safe_reply_text(
                update,
                f"❌ *Error occurred:* {str(e)[:500]}\n\n"
                f"Error type: {type(e).__name__}\n\n"
                "Please try again or use /new to reset your session.",
                parse_mode='Markdown'
            )
        except Exception as send_error:
            logger.error(f"❌ Failed to send error message: {send_error}", exc_info=True)
            logger.error(f"❌ Send error traceback:\n{traceback.format_exc()}")


async def send_typing_continuously(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Send typing indicator continuously while processing"""
    try:
        while True:
            await context.bot.send_chat_action(chat_id=chat_id, action='typing')
            await asyncio.sleep(3)  # Telegram requires typing indicator every 3-5 seconds
    except asyncio.CancelledError:
        pass


# Admin commands
async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin dashboard command"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("❌ *Access Denied*\n\nYou are not an admin.", parse_mode='Markdown')
        return
    
    stats = db.get_dashboard_stats()
    
    dashboard_text = f"""
╔═══════════════════════════════════════╗
║      📊 ADMIN DASHBOARD 📊            ║
╚═══════════════════════════════════════╝

┌─ USER STATISTICS ────────────────────┐
│ Total Users: `{stats['total_users']:<22}` │
│ New Today: `{stats['today_new_users']:<24}` │
│ Active Subs: `{stats['active_subscriptions']:<21}` │
└──────────────────────────────────────┘

┌─ REVENUE ────────────────────────────┐
│ Total Revenue: `${stats['total_revenue']:.2f}` USD │
└──────────────────────────────────────┘
    """
    
    # Admin menu keyboard
    keyboard = [
        [
            InlineKeyboardButton("👥 View Users", callback_data="admin_users"),
            InlineKeyboardButton("💳 Payments", callback_data="admin_payments")
        ],
        [
            InlineKeyboardButton("⭐ Subscriptions", callback_data="admin_subs"),
            InlineKeyboardButton("📊 Statistics", callback_data="admin_stats")
        ],
        [
            InlineKeyboardButton("🔧 Upgrade Users", callback_data="admin_upgrade_menu")
        ],
        [
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(dashboard_text, parse_mode='Markdown', reply_markup=reply_markup)


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View all users"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("❌ Access Denied", parse_mode='Markdown')
        return
    
    # Get all users (increase limit significantly)
    users = db.get_all_users(limit=1000)
    
    if not users:
        await update.message.reply_text("No users found.")
        return
    
    # Get total user count for accurate display
    stats = db.get_dashboard_stats()
    total_users = stats['total_users']
    
    users_text = "╔═══════════════════════════════════════╗\n"
    users_text += "║        👥 ALL USERS 👥                 ║\n"
    users_text += "╚═══════════════════════════════════════╝\n\n"
    users_text += f"Total users: {total_users}\n"
    users_text += f"Showing all {len(users)} users:\n\n"
    
    # Split into multiple messages if too many users (Telegram has 4096 char limit)
    if len(users) > 50:
        # Send first message with summary
        summary_text = users_text + f"\n⚠️ Too many users to display in one message ({len(users)} users).\n"
        summary_text += "Use the admin dashboard buttons to view users in smaller groups.\n"
        summary_text += f"\nFirst 50 users:\n\n"
        
        for i, user in enumerate(users[:50], 1):
            user_id_val = user['user_id']
            name = user.get('first_name', 'N/A') or 'N/A'
            username = user.get('username', 'N/A') or 'N/A'
            # Check if user is admin
            is_user_admin = db.is_admin(user_id_val)
            if is_user_admin:
                status = '👑 ADMIN'
            else:
                status = user.get('current_status', 'free') or 'free'
            summary_text += f"{i}. {name} (@{username}) - ID: {user_id_val} - Status: {status}\n"
        
        await update.message.reply_text(summary_text, parse_mode='Markdown')
    else:
        # Show all users if 50 or less
        for user in users:
            user_id_val = user['user_id']
            # Check if user is admin
            is_user_admin = db.is_admin(user_id_val)
            users_text += f"┌─ User ID: `{user_id_val}` ───────────┐\n"
            users_text += f"│ Name: {user.get('first_name', 'N/A'):<25} │\n"
            username = user.get('username', 'N/A')
            users_text += f"│ Username: @{username[:22]:<22} │\n"
            if is_user_admin:
                status_display = '👑 ADMIN'
            else:
                status_display = user.get('current_status', 'free') or 'free'
            users_text += f"│ Status: `{status_display:<22}` │\n"
            users_text += f"│ Referrals: `{user.get('total_referrals', 0):<21}` │\n"
            users_text += "└──────────────────────────────────────┘\n\n"
    
    await update.message.reply_text(users_text, parse_mode='Markdown')


async def admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add admin user"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("❌ Access Denied", parse_mode='Markdown')
        return
    
    if not context.args:
        await update.message.reply_text("Usage: `/admin_add USER_ID`", parse_mode='Markdown')
        return
    
    try:
        new_admin_id = int(context.args[0])
        db.add_admin(new_admin_id)
        await update.message.reply_text(f"✅ Admin {new_admin_id} added successfully.", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.", parse_mode='Markdown')


async def admin_upgrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Upgrade user manually (admin only)"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("❌ Access Denied", parse_mode='Markdown')
        return
    
    if not context.args or len(context.args) < 2:
        help_text = """
╔═══════════════════════════════════════╗
║     🔧 ADMIN UPGRADE USER 🔧          ║
╚═══════════════════════════════════════╝

Usage: `/admin_upgrade USER_ID DURATION`

Durations:
• `10min` - 10 minutes
• `1day` - 1 day
• `7days` - 7 days

Examples:
• `/admin_upgrade 123456789 10min`
• `/admin_upgrade 123456789 1day`
• `/admin_upgrade 123456789 7days`
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
        return
    
    try:
        target_user_id = int(context.args[0])
        duration = context.args[1].lower()
        
        # Parse duration
        if duration == "10min":
            duration_minutes = 10
            duration_days = None
            duration_text = "10 minutes"
        elif duration == "1day":
            duration_minutes = None
            duration_days = 1
            duration_text = "1 day"
        elif duration == "7days":
            duration_minutes = None
            duration_days = 7
            duration_text = "7 days"
        else:
            await update.message.reply_text(
                "❌ Invalid duration. Use: `10min`, `1day`, or `7days`",
                parse_mode='Markdown'
            )
            return
        
        # Create temporary subscription (unlimited requests)
        sub_id = db.create_temporary_subscription(
            target_user_id,
            requests_limit=999999,  # Effectively unlimited
            duration_minutes=duration_minutes,
            duration_days=duration_days
        )
        
        # Get subscription details for notification
        sub = db.get_user_subscription(target_user_id)
        if not sub:
            await update.message.reply_text("❌ Failed to create subscription. Please try again.", parse_mode='Markdown')
            return
        
        # Calculate expiration time
        from datetime import datetime
        try:
            end_date_str = sub['end_date']
            if isinstance(end_date_str, str):
                if 'Z' in end_date_str or '+' in end_date_str:
                    end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                else:
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d %H:%M:%S')
            else:
                end_date = end_date_str
            
            expires_text = end_date.strftime('%Y-%m-%d %H:%M')
        except:
            expires_text = str(sub['end_date'])
        
        # Send notification to upgraded user
        try:
            notification_text = f"""
╔═══════════════════════════════════════╗
║   🎉 ACCOUNT UPGRADED! 🎉              ║
╚═══════════════════════════════════════╝

┌─ UPGRADE DETAILS ────────────────────┐
│ Duration: {duration_text}             │
│ Requests: Unlimited                    │
│ Expires: {expires_text}              │
└──────────────────────────────────────┘

✅ Your account has been upgraded successfully!

📋 What's Next:
• Use /status to check your new plan
• Start using your upgraded requests
• Subscription will expire automatically

💡 Remember: This is a temporary upgrade.
   Make the most of it! 🚀
            """
            
            # Send notification to user
            try:
                await update.message.bot.send_message(
                    chat_id=target_user_id,
                    text=notification_text,
                    parse_mode='Markdown'
                )
                logger.info(f"Sent upgrade notification to user {target_user_id}")
            except Exception as send_error:
                logger.error(f"Failed to send notification to user {target_user_id}: {send_error}")
                # Try alternative method
                if bot_application:
                    await bot_application.bot.send_message(
                        chat_id=target_user_id,
                        text=notification_text,
                        parse_mode='Markdown'
                    )
        except Exception as e:
            logger.error(f"Failed to send notification to user {target_user_id}: {e}")
        
        success_text = f"""
╔═══════════════════════════════════════╗
║   ✅ USER UPGRADED SUCCESSFULLY ✅      ║
╚═══════════════════════════════════════╝

┌─ UPGRADE DETAILS ────────────────────┐
│ User ID: `{target_user_id}`           │
│ Duration: {duration_text}             │
│ Requests: Unlimited                    │
│ Expires: {expires_text}              │
└──────────────────────────────────────┘

✅ User has been upgraded!
📧 Notification sent to user.
Subscription will expire automatically.
        """
        
        await update.message.reply_text(success_text, parse_mode='Markdown')
        
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Must be a number.", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error upgrading user: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}", parse_mode='Markdown')


def main():
    """Main function to run the bot"""
    global TELEGRAM_BOT_TOKEN, bot_application
    
    logger.info("="*60)
    logger.info("SMG-Forcer Telegram Bot - Starting...")
    logger.info("="*60)
    
    # Check if bot token is set
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables!")
        logger.info("Please set TELEGRAM_BOT_TOKEN in your .hacx file or environment.")
        logger.info("Run 'python production_setup.py' to verify your setup.")
        
        # In production, don't prompt for input - exit instead
        if os.getenv("PRODUCTION_MODE") == "true":
            logger.error("Production mode: Exiting due to missing bot token")
            sys.exit(1)
        
        token = input("Enter your Telegram Bot Token (or press Enter to exit): ").strip()
        if token:
            set_key(Config.ENV_FILE, "TELEGRAM_BOT_TOKEN", token)
            TELEGRAM_BOT_TOKEN = token
            logger.info("Token saved to .hacx file")
        else:
            sys.exit(1)
    
    if not DEEPSEEK_API_KEYS:
        logger.error("No DeepSeek API keys configured! Bot will not work.")
        logger.info("Add at least one DeepSeek API key to .hacx file:")
        logger.info("  SMG-Forcer-API=sk-your-deepseek-key")
        logger.info("  DEEPSEEK_API_KEY_2=sk-another-deepseek-key (optional)")
        sys.exit(1)
    
    logger.info(f"Loaded {len(DEEPSEEK_API_KEYS)} DeepSeek API key(s) for rotation")
    if len(DEEPSEEK_API_KEYS) > 1:
        logger.info("Multi-key rotation enabled - bot will automatically switch if one key fails")
    
    # Initialize multi-model manager (synchronous, no event loop needed)
    if MULTI_MODEL_AVAILABLE:
        try:
            # Initialize multi-model manager with DeepSeek keys
            model_manager = get_model_manager(DEEPSEEK_API_KEYS)
            logger.info("Multi-model manager initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize multi-model manager: {e}")
    
    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    bot_application = application  # Store globally for notifications
    
    # Start background processor workers after application starts (lazy initialization)
    # Workers will start automatically when first task is added
    if BACKGROUND_PROCESSOR_AVAILABLE:
        # Initialize processor instance (workers start lazily when needed)
        try:
            background_processor = get_background_processor(max_concurrent=3)
            logger.info("Background processor ready (workers start on first task)")
        except Exception as e:
            logger.warning(f"Failed to initialize background processor: {e}")
    
    # Start concurrency manager queue processor
    if CONCURRENCY_MANAGER_AVAILABLE and concurrency_manager:
        async def start_queue_processor():
            await concurrency_manager.process_queue()
        
        # Start queue processor as background task (only if job_queue is available)
        if application.job_queue is not None:
            try:
                application.job_queue.run_once(
                    lambda context: asyncio.create_task(start_queue_processor()),
                    when=1
                )
                logger.info("Concurrency manager queue processor started via job_queue")
            except Exception as e:
                logger.warning(f"Could not start queue processor via job_queue: {e}")
        else:
            # Alternative: Start queue processor in application startup
            async def start_queue_on_startup():
                # Wait a bit for application to fully start
                await asyncio.sleep(2)
                asyncio.create_task(start_queue_processor())
            
            # Use application.post_init if available, otherwise start manually
            original_post_init = getattr(application, 'post_init', None)
            
            async def combined_post_init(app: Application) -> None:
                if original_post_init:
                    await original_post_init(app)
                await start_queue_on_startup()
            
            application.post_init = combined_post_init
            logger.info("Concurrency manager queue processor will start on application init")
    
    # Start memory cleanup service
    if SECURE_MEMORY_AVAILABLE and cleanup_service:
        cleanup_service.start()
        logger.info("Memory cleanup service started (3-day retention)")
    
    # Start project cleanup service (3-day retention)
    try:
        from project_manager import ProjectManager
        from user_workspace_manager import UserWorkspaceManager
        workspace_manager = UserWorkspaceManager.get_instance()
        base_workspace = workspace_manager.base_workspace if hasattr(workspace_manager, 'base_workspace') else os.getenv('WORKSPACE_ROOT', os.getcwd())
        
        project_manager = ProjectManager(
            workspace_root=base_workspace,
            secure_memory=secure_memory,
            vector_memory=None  # Will be initialized if available
        )
        
        # Run cleanup on startup
        async def cleanup_projects_on_startup():
            """Cleanup old projects on startup"""
            try:
                # Get all user workspaces and cleanup projects
                if hasattr(workspace_manager, 'get_all_user_workspaces'):
                    user_workspaces = workspace_manager.get_all_user_workspaces()
                    for user_id in user_workspaces.keys():
                        try:
                            project_manager.cleanup_old_projects(user_id, retention_days=3)
                        except Exception as e:
                            logger.warning(f"Error cleaning up projects for user {user_id}: {e}")
            except Exception as e:
                logger.warning(f"Error in project cleanup on startup: {e}")
        
        # Schedule periodic cleanup (every 24 hours)
        if application.job_queue is not None:
            async def periodic_project_cleanup(context):
                """Periodic project cleanup"""
                try:
                    if hasattr(workspace_manager, 'get_all_user_workspaces'):
                        user_workspaces = workspace_manager.get_all_user_workspaces()
                        for user_id in user_workspaces.keys():
                            try:
                                project_manager.cleanup_old_projects(user_id, retention_days=3)
                            except Exception as e:
                                logger.warning(f"Error in periodic project cleanup for user {user_id}: {e}")
                except Exception as e:
                    logger.warning(f"Error in periodic project cleanup: {e}")
            
            # Run cleanup on startup (after 5 seconds)
            application.job_queue.run_once(
                lambda context: asyncio.create_task(cleanup_projects_on_startup()),
                when=5
            )
            
            # Schedule periodic cleanup every 24 hours
            application.job_queue.run_repeating(
                periodic_project_cleanup,
                interval=86400,  # 24 hours in seconds
                first=86400  # First run after 24 hours
            )
            logger.info("Project cleanup service started (3-day retention, runs every 24 hours)")
    except ImportError as e:
        logger.warning(f"ProjectManager not available for cleanup: {e}")
    except Exception as e:
        logger.warning(f"Error starting project cleanup service: {e}")
    
    # Start CVE learning cycle (daily)
    async def start_cve_learning_cycle():
        """Start daily CVE learning cycle"""
        try:
            from desktop_ai_handler import DesktopAIHandler
            from HacxGPT import get_user_brain
            
            # Get a brain instance for learning
            brain = get_user_brain(0)  # Use system user ID 0 for learning
            
            # Initialize CVE learning system
            from cve_learning_system import get_cve_learning_system
            from cve_intelligence import get_cve_intelligence
            from cve_monitor import get_cve_monitor
            
            cve_intelligence = get_cve_intelligence()
            cve_monitor = get_cve_monitor(cve_intelligence=cve_intelligence)
            cve_learning = get_cve_learning_system(
                cve_intelligence=cve_intelligence,
                cve_monitor=cve_monitor
            )
            
            # Run daily learning cycle
            await cve_learning.daily_learning_cycle()
            logger.info("CVE daily learning cycle completed")
        except Exception as e:
            logger.warning(f"Error in CVE learning cycle: {e}")
    
    # Schedule daily CVE learning (run once per day)
    if application.job_queue:
        async def schedule_cve_learning(context):
            await start_cve_learning_cycle()
        
        # Run daily at midnight UTC
        application.job_queue.run_daily(
            schedule_cve_learning,
            time=dt_time(hour=0, minute=0),
            name="cve_daily_learning"
        )
        logger.info("CVE daily learning cycle scheduled (runs daily at midnight UTC)")
    else:
        # If no job queue, run immediately and log
        logger.info("Job queue not available, CVE learning will run on-demand")
    
    # Register handlers
    # Approval callback handler
    async def handle_approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle approval/rejection callbacks"""
        query = update.callback_query
        if not query:
            return
        
        await query.answer()
        
        if not APPROVAL_MANAGER_AVAILABLE:
            await query.edit_message_text("❌ Approval system not available")
            return
        
        try:
            approval_manager = get_approval_manager()
            callback_data = query.data
            
            if callback_data.startswith('approve:'):
                request_id = callback_data.split(':', 1)[1]
                approved = approval_manager.approve(request_id, reason="User approved via Telegram")
                if approved:
                    await query.edit_message_text("✅ **Approved**\n\nAction will be executed.")
                else:
                    await query.edit_message_text("❌ Approval failed. Request may have expired.")
            
            elif callback_data.startswith('reject:'):
                request_id = callback_data.split(':', 1)[1]
                rejected = approval_manager.reject(request_id, reason="User rejected via Telegram")
                if rejected:
                    await query.edit_message_text("❌ **Rejected**\n\nAction cancelled.")
                else:
                    await query.edit_message_text("❌ Rejection failed. Request may have expired.")
        except Exception as e:
            logger.error(f"Error handling approval callback: {e}")
            await query.edit_message_text(f"❌ Error: {str(e)}")
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("new", new_conversation))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("plans", plans_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("referral", referral_command))
    application.add_handler(CommandHandler("myid", myid_command))
    application.add_handler(CommandHandler("admin", admin_dashboard))
    application.add_handler(CommandHandler("admin_users", admin_users))
    application.add_handler(CommandHandler("admin_add", admin_add))
    application.add_handler(CommandHandler("admin_upgrade", admin_upgrade))
    
    # Document generation commands
    application.add_handler(CommandHandler("generate_document", generate_document_command))
    application.add_handler(CommandHandler("generate_pdf", generate_pdf_command))
    application.add_handler(CommandHandler("generate_word", generate_word_command))
    application.add_handler(CommandHandler("generate_excel", generate_excel_command))
    
    # Barcode and QR code commands
    application.add_handler(CommandHandler("generate_qr", generate_qr_command))
    application.add_handler(CommandHandler("generate_barcode", generate_barcode_command))
    
    # Template management commands
    application.add_handler(CommandHandler("save_template", save_template_command))
    application.add_handler(CommandHandler("use_template", use_template_command))
    application.add_handler(CommandHandler("list_templates", list_templates_command))
    application.add_handler(CommandHandler("delete_template", delete_template_command))
    application.add_handler(CommandHandler("download_template", download_template_command))
    
    # Image generation commands
    application.add_handler(CommandHandler("generate_image", generate_image_command))
    
    # Image editing commands
    application.add_handler(CommandHandler("edit_image", edit_image_command))
    
    # Face swap commands
    application.add_handler(CommandHandler("face_swap", face_swap_command))
    
    # Service management commands
    application.add_handler(CommandHandler("start_service", start_service_command))
    application.add_handler(CommandHandler("stop_service", stop_service_command))
    application.add_handler(CommandHandler("list_services", list_services_command))
    application.add_handler(CommandHandler("service_status", service_status_command))
    application.add_handler(CommandHandler("service_logs", service_logs_command))
    
    # Project management commands
    application.add_handler(CommandHandler("save_project", save_project_command))
    application.add_handler(CommandHandler("restore_project", restore_project_command))
    application.add_handler(CommandHandler("list_projects", list_projects_command))
    application.add_handler(CommandHandler("delete_project", delete_project_command))
    
    # Admin workspace/service management commands
    application.add_handler(CommandHandler("admin_workspaces", admin_workspaces_command))
    application.add_handler(CommandHandler("admin_workspace", admin_workspace_command))
    application.add_handler(CommandHandler("admin_services", admin_services_command))
    application.add_handler(CommandHandler("admin_service", admin_service_command))
    application.add_handler(CommandHandler("admin_delete_project", admin_delete_project_command))
    application.add_handler(CommandHandler("admin_stop_service", admin_stop_service_command))
    application.add_handler(CommandHandler("admin_delete_service", admin_delete_service_command))
    application.add_handler(CommandHandler("admin_workspace_stats", admin_workspace_stats_command))
    
    # Add approval callback handler
    application.add_handler(CallbackQueryHandler(handle_approval_callback, pattern=r'^(approve|reject):'))
    # Register dashboard handlers (lazy import to avoid circular dependency)
    try:
        from dashboard_features import register_dashboard_handlers
        register_dashboard_handlers(application)
    except ImportError as e:
        logger.warning(f"Could not import dashboard features: {e}")
        logger.info("Dashboard features will not be available")
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # Add handler for file uploads (documents) - exclude images which are handled separately
    try:
        doc_filter = getattr(filters, 'Document', None)
        if doc_filter:
            # Handle documents that are NOT images
            application.add_handler(MessageHandler(
                doc_filter.ALL & ~doc_filter.IMAGE if hasattr(doc_filter, 'IMAGE') else doc_filter.ALL,
                handle_file_upload
            ))
            logger.info("File upload handler added")
    except Exception as e:
        logger.warning(f"Could not add file upload handler: {e}")
    # Add handler for images/photos
    application.add_handler(MessageHandler(filters.PHOTO, handle_image))
    # Add handler for image documents (optional - photos work without this)
    # handle_image function already supports both photo and document types
    try:
        # Try to add document image handler (python-telegram-bot 20+ syntax)
        # Check if filters.Document exists
        doc_filter = getattr(filters, 'Document', None)
        if doc_filter:
            # Try Document.IMAGE first
            if hasattr(doc_filter, 'IMAGE'):
                application.add_handler(MessageHandler(doc_filter.IMAGE, handle_image))
                logger.info("Document image handler added")
            else:
                # Fallback to Document.ALL (handle_image will filter by mime_type)
                application.add_handler(MessageHandler(doc_filter.ALL, handle_image))
                logger.info("Document handler added (will filter images in handler)")
        else:
            logger.info("Document filter not available - photo uploads will work, document uploads may not")
    except Exception as e:
        # Gracefully handle any errors - photos will still work
        logger.warning(f"Could not add document image handler: {e}. Photo uploads will still work.")
    
    # Start the bot
    logger.info("SMG-Forcer Telegram Bot is starting...")
    logger.info(f"API Provider: {Config.API_PROVIDER}")
    
    # Handle conflict errors gracefully (multiple instances)
    # Use start() instead of run_polling() when running in a thread (Railway)
    import threading
    is_main_thread = threading.current_thread() is threading.main_thread()
    
    try:
        if is_main_thread:
            # Main thread - use run_polling (allows signal handlers)
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,  # Drop pending updates on restart
                close_loop=False  # Don't close event loop on error
            )
        else:
            # Background thread - use async run_polling with new event loop
            logger.info("Running bot in background thread (using async run_polling with new event loop)")
            try:
                # Create new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Run polling in the new event loop
                async def run_bot_async():
                    try:
                        # Initialize the application first
                        await application.initialize()
                        await application.start()
                        await application.updater.start_polling(
                            allowed_updates=Update.ALL_TYPES,
                            drop_pending_updates=True
                        )
                        logger.info("Bot polling started successfully")
                        # Keep running
                        try:
                            await asyncio.Event().wait()  # Wait forever
                        except asyncio.CancelledError:
                            logger.info("Bot polling cancelled")
                            await application.stop()
                            await application.updater.stop()
                    except Exception as e:
                        logger.error(f"Error in bot async loop: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                        # Try to clean up
                        try:
                            await application.stop()
                        except:
                            pass
                        raise
                
                logger.info("Starting bot async loop...")
                loop.run_until_complete(run_bot_async())
            except Exception as e:
                logger.error(f"Event loop error: {e}")
                # Fallback: just sleep (time is already imported at top of file)
                import time
                while True:
                    time.sleep(60)
    except Exception as e:
        if "Conflict" in str(e) or "terminated by other getUpdates" in str(e):
            logger.error("Bot conflict detected - another instance may be running")
            logger.error("This usually happens during Railway restarts")
            logger.info("Waiting 30 seconds before retrying...")
            import time
            time.sleep(30)
            # Retry once
            try:
                application.run_polling(
                    allowed_updates=Update.ALL_TYPES,
                    drop_pending_updates=True
                )
            except Exception as retry_error:
                logger.error(f"Retry failed: {retry_error}")
                raise
        else:
            raise


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        print("\n✅ Bot stopped successfully")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        print("Check the logs above for details")
        sys.exit(1)
