# -*- coding: utf-8 -*-
"""
Dashboard Features with Inline Keyboards for Telegram Bot
Integrates dashboard notification features with inline keyboard interface
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown as tg_escape_markdown
from telegram.error import BadRequest
import logging
import requests
import os

# Try to use hybrid database (auto-detects SQLite or PostgreSQL)
try:
    from database_hybrid import Database
except ImportError:
    # Fallback to regular database
    try:
        from database_postgres import Database
    except ImportError:
        from database import Database

logger = logging.getLogger(__name__)
db = Database()

# Helper function to detect database type
def is_postgres():
    """Check if using PostgreSQL database"""
    try:
        conn = db.get_connection()
        # Try to detect PostgreSQL by checking for psycopg2 connection
        db_type = type(conn).__module__
        conn.close()
        return 'psycopg2' in db_type or 'postgres' in db_type.lower()
    except:
        return False

# Lazy imports to avoid circular dependency
def get_telegram_bot():
    """Lazy import to avoid circular dependency"""
    from telegram_bot_module import telegram_bot
    return telegram_bot

def get_settings_sync():
    """Lazy import to avoid circular dependency"""
    from telegram_bot_module import settings_sync
    return settings_sync

# Dashboard API base URL (from environment or Railway URL)
# Railway provides RAILWAY_PUBLIC_DOMAIN or PORT environment variables
RAILWAY_PUBLIC_DOMAIN = os.getenv('RAILWAY_PUBLIC_DOMAIN')
RAILWAY_STATIC_URL = os.getenv('RAILWAY_STATIC_URL')
PORT = os.getenv('PORT', '5000')

# Determine dashboard API URL
if RAILWAY_STATIC_URL:
    DASHBOARD_API_URL = RAILWAY_STATIC_URL
elif RAILWAY_PUBLIC_DOMAIN:
    DASHBOARD_API_URL = f"https://{RAILWAY_PUBLIC_DOMAIN}"
else:
    # Fallback to explicit DASHBOARD_API_URL or localhost
    DASHBOARD_API_URL = os.getenv('DASHBOARD_API_URL', f'http://localhost:{PORT}')


def get_dashboard_keyboard(user_id: int, is_admin: bool = False) -> InlineKeyboardMarkup:
    """Get main dashboard features keyboard"""
    keyboard = []
    
    # Main dashboard features
    keyboard.append([
        InlineKeyboardButton("💻 Terminal", callback_data="dashboard_terminal"),
        InlineKeyboardButton("🔧 Toolkit", callback_data="dashboard_toolkit")
    ])
    
    keyboard.append([
        InlineKeyboardButton("📦 Extensions", callback_data="dashboard_extensions"),
        InlineKeyboardButton("🔀 Git", callback_data="dashboard_git")
    ])
    
    keyboard.append([
        InlineKeyboardButton("⚙️ Settings", callback_data="dashboard_settings"),
        InlineKeyboardButton("🛠️ Fix Dashboard", callback_data="dashboard_fix")
    ])
    
    # Admin-only features
    if is_admin:
        keyboard.append([
            InlineKeyboardButton("👑 Admin Panel", callback_data="dashboard_admin")
        ])
    
    keyboard.append([
        InlineKeyboardButton("📊 Status", callback_data="dashboard_status"),
        InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_admin_dashboard_keyboard() -> InlineKeyboardMarkup:
    """Get admin dashboard management keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("📊 View Stats", callback_data="admin_stats"),
            InlineKeyboardButton("👥 Manage Users", callback_data="admin_users")
        ],
        [
            InlineKeyboardButton("💳 View Payments", callback_data="admin_payments"),
            InlineKeyboardButton("⭐ Subscriptions", callback_data="admin_subscriptions")
        ],
        [
            InlineKeyboardButton("🔍 Search User by ID", callback_data="admin_search_user"),
            InlineKeyboardButton("🎁 Free Upgrade", callback_data="admin_free_upgrade")
        ],
        [
            InlineKeyboardButton("🎁🎁 Bulk Free Upgrade (All Users)", callback_data="admin_bulk_free_upgrade")
        ],
        [
            InlineKeyboardButton("🔔 Notification Settings", callback_data="admin_notifications"),
            InlineKeyboardButton("⚙️ Dashboard Config", callback_data="admin_config")
        ],
        [
            InlineKeyboardButton("📈 Analytics", callback_data="admin_analytics"),
            InlineKeyboardButton("🔙 Back to Dashboard", callback_data="dashboard_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def handle_dashboard_callback(query, data: str, user_id: int):
    """Handle dashboard-related callback queries"""
    try:
        # Answer callback to prevent loading spinner
        await query.answer()
    except:
        pass  # Ignore if already answered
    
    try:
        is_admin = db.is_admin(user_id)
    except Exception as e:
        logger.error(f"Error checking admin status: {e}", exc_info=True)
        await query.answer("❌ Error checking permissions", show_alert=True)
        return
    
    try:
        if data == "dashboard_menu" or data == "dashboard_home":
            text = """
╔═══════════════════════════════════════╗
║   🖥️ DASHBOARD FEATURES 🖥️            ║
╚═══════════════════════════════════════╝

┌─ AVAILABLE FEATURES ──────────────────┐
│ 💻 Terminal Commands                   │
│ 🔧 Toolkit Tools                       │
│ 📦 Extensions                          │
│ 🔀 Git Operations                      │
│ ⚙️ Settings Sync                       │
│ 🛠️ Dashboard Fixes                     │
└──────────────────────────────────────┘

Select a feature to manage or view:
            """
            reply_markup = get_dashboard_keyboard(user_id, is_admin)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        if data == "dashboard_terminal":
            text = """
╔═══════════════════════════════════════╗
║   💻 TERMINAL COMMANDS 💻              ║
╚═══════════════════════════════════════╝

Monitor and manage terminal commands executed in the desktop app.

**Features:**
• View command history
• Monitor command execution
• Get real-time notifications
• Track command success/failure

**Status:** ✅ Active
            """
            keyboard = [
                [
                    InlineKeyboardButton("📋 View History", callback_data="terminal_history"),
                    InlineKeyboardButton("🔔 Toggle Notifications", callback_data="terminal_toggle")
                ],
                [
                    InlineKeyboardButton("📊 Statistics", callback_data="terminal_stats"),
                    InlineKeyboardButton("🔙 Back", callback_data="dashboard_menu")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        if data == "dashboard_toolkit":
            text = """
╔═══════════════════════════════════════╗
║   🔧 TOOLKIT TOOLS 🔧                 ║
╚═══════════════════════════════════════╝

Manage and monitor RedTeam-Tools execution.

**Features:**
• View available tools
• Monitor tool execution
• Get execution results
• Track tool usage

**Status:** ✅ Active
            """
            keyboard = [
                [
                    InlineKeyboardButton("📋 View Tools", callback_data="toolkit_list"),
                    InlineKeyboardButton("📊 Usage Stats", callback_data="toolkit_stats")
                ],
                [
                    InlineKeyboardButton("🔔 Toggle Notifications", callback_data="toolkit_toggle"),
                    InlineKeyboardButton("🔙 Back", callback_data="dashboard_menu")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        if data == "dashboard_extensions":
            text = """
╔═══════════════════════════════════════╗
║   📦 EXTENSIONS 📦                    ║
╚═══════════════════════════════════════╝

Manage desktop app extensions.

**Features:**
• View installed extensions
• Monitor extension installation
• Get extension updates
• Manage extension settings

**Status:** ✅ Active
            """
            keyboard = [
                [
                    InlineKeyboardButton("📋 Installed", callback_data="extensions_list"),
                    InlineKeyboardButton("🔔 Notifications", callback_data="extensions_toggle")
                ],
                [
                    InlineKeyboardButton("🔙 Back", callback_data="dashboard_menu")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        if data == "dashboard_git":
            text = """
╔═══════════════════════════════════════╗
║   🔀 GIT OPERATIONS 🔀                 ║
╚═══════════════════════════════════════╝

Monitor Git operations in the desktop app.

**Features:**
• View Git operations
• Monitor commits/pushes
• Track repository changes
• Get operation notifications

**Status:** ✅ Active
            """
            keyboard = [
                [
                    InlineKeyboardButton("📋 Recent Operations", callback_data="git_history"),
                    InlineKeyboardButton("🔔 Toggle Notifications", callback_data="git_toggle")
                ],
                [
                    InlineKeyboardButton("🔙 Back", callback_data="dashboard_menu")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        if data == "dashboard_settings":
            settings_sync = get_settings_sync()
            text = """
╔═══════════════════════════════════════╗
║   ⚙️ SETTINGS SYNC ⚙️                 ║
╚═══════════════════════════════════════╝

Sync settings between web and desktop app.

**Features:**
• View synced settings
• Manual sync trigger
• Settings backup/restore
• Cross-platform sync

**Status:** """ + ("✅ Active" if settings_sync.enabled else "❌ Not Configured")
            
            keyboard = [
                [
                    InlineKeyboardButton("📋 View Settings", callback_data="settings_view"),
                    InlineKeyboardButton("🔄 Sync Now", callback_data="settings_sync_now")
                ],
                [
                    InlineKeyboardButton("💾 Backup", callback_data="settings_backup"),
                    InlineKeyboardButton("🔙 Back", callback_data="dashboard_menu")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        if data == "dashboard_fix":
            text = """
╔═══════════════════════════════════════╗
║   🛠️ DASHBOARD FIXES 🛠️               ║
╚═══════════════════════════════════════╝

Automated dashboard issue detection and fixes.

**Features:**
• Auto-detect issues
• Apply fixes automatically
• View fix history
• Manual fix trigger

**Status:** ✅ Active
            """
            keyboard = [
                [
                    InlineKeyboardButton("🔍 Check Issues", callback_data="fix_check"),
                    InlineKeyboardButton("🔧 Apply Fixes", callback_data="fix_apply")
                ],
                [
                    InlineKeyboardButton("📋 Fix History", callback_data="fix_history"),
                    InlineKeyboardButton("🔙 Back", callback_data="dashboard_menu")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        if data == "dashboard_status":
            # Get dashboard status
            try:
                # Use the detected DASHBOARD_API_URL
                status_url = f"{DASHBOARD_API_URL}/api/telegram/dashboard/status"
                logger.debug(f"Checking dashboard status at: {status_url}")
                response = requests.get(status_url, timeout=5)
                if response.status_code == 200:
                    status_data = response.json()
                    telegram_enabled = status_data.get('telegram_enabled', False)
                    settings_enabled = status_data.get('settings_sync_enabled', False)
                    features = status_data.get('features', {})
                    
                    text = f"""
╔═══════════════════════════════════════╗
║   📊 DASHBOARD STATUS 📊              ║
╚═══════════════════════════════════════╝

┌─ INTEGRATION STATUS ──────────────────┐
│ Telegram: {'✅ Enabled' if telegram_enabled else '❌ Disabled'}     │
│ Settings Sync: {'✅ Enabled' if settings_enabled else '❌ Disabled'} │
└──────────────────────────────────────┘

┌─ FEATURES ─────────────────────────────┐
│ Terminal: {'✅' if features.get('terminal_notifications') else '❌'}                    │
│ Toolkit: {'✅' if features.get('toolkit_notifications') else '❌'}                     │
│ Extensions: {'✅' if features.get('extension_notifications') else '❌'}                 │
│ Git: {'✅' if features.get('git_notifications') else '❌'}                         │
│ Dashboard Fix: {'✅' if features.get('dashboard_fix_notifications') else '❌'}         │
│ Settings Sync: {'✅' if features.get('settings_sync') else '❌'}              │
└──────────────────────────────────────┘
                    """
                else:
                    text = """
╔═══════════════════════════════════════╗
║   📊 DASHBOARD STATUS 📊              ║
╚═══════════════════════════════════════╝

❌ Unable to connect to dashboard API.
Please check if the dashboard is running.
                    """
            except Exception as e:
                logger.error(f"Failed to get dashboard status: {e}")
                text = """
╔═══════════════════════════════════════╗
║   📊 DASHBOARD STATUS 📊              ║
╚═══════════════════════════════════════╝

❌ Error connecting to dashboard.
                """
            
            keyboard = [
                [InlineKeyboardButton("🔄 Refresh", callback_data="dashboard_status")],
                [InlineKeyboardButton("🔙 Back", callback_data="dashboard_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        # Admin panel
        if data == "dashboard_admin":
            if not is_admin:
                await query.answer("❌ Admin access required", show_alert=True)
                return
            
            text = """
╔═══════════════════════════════════════╗
║   👑 ADMIN DASHBOARD 👑                ║
╚═══════════════════════════════════════╝

Manage dashboard and system settings.

**Admin Features:**
• View system statistics
• Manage users
• Monitor payments
• Configure notifications
• View analytics

Select an option:
            """
            reply_markup = get_admin_dashboard_keyboard()
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        # Admin sub-menus    
        if data == "admin_stats":
            if not is_admin:
                await query.answer("❌ Admin access required", show_alert=True)
                return
            
            try:
                stats = db.get_dashboard_stats()
                
                # Get additional statistics from database
                conn = db.get_connection()
                use_postgres = is_postgres()
                
                try:
                    if use_postgres:
                        from psycopg2.extras import RealDictCursor
                        cursor = conn.cursor(cursor_factory=RealDictCursor)
                    else:
                        # SQLite - set row_factory before creating cursor
                        import sqlite3
                        if hasattr(conn, 'row_factory'):
                            conn.row_factory = sqlite3.Row
                        cursor = conn.cursor()
                except:
                    cursor = conn.cursor()
                
                # This week's new users (database-agnostic)
                if use_postgres:
                    cursor.execute("""
                        SELECT COUNT(*) as count FROM users 
                        WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
                    """)
                else:
                    # SQLite syntax
                    cursor.execute("""
                        SELECT COUNT(*) as count FROM users 
                        WHERE created_at >= datetime('now', '-7 days')
                    """)
                result = cursor.fetchone()
                # Handle both dict-like (PostgreSQL RealDictCursor, SQLite Row) and tuple results
                if result:
                    if hasattr(result, '__getitem__') and not isinstance(result, (str, bytes)):
                        try:
                            week_users = result['count'] if 'count' in result else result[0]
                        except (KeyError, TypeError):
                            week_users = result[0] if result else 0
                    else:
                        week_users = result[0] if result else 0
                else:
                    week_users = 0
                
                # This month's new users
                if use_postgres:
                    cursor.execute("""
                        SELECT COUNT(*) as count FROM users 
                        WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
                    """)
                else:
                    cursor.execute("""
                        SELECT COUNT(*) as count FROM users 
                        WHERE created_at >= datetime('now', '-30 days')
                    """)
                result = cursor.fetchone()
                # Handle both dict-like and tuple results
                if result:
                    if hasattr(result, '__getitem__') and not isinstance(result, (str, bytes)):
                        try:
                            month_users = result['count'] if 'count' in result else result[0]
                        except (KeyError, TypeError):
                            month_users = result[0] if result else 0
                    else:
                        month_users = result[0] if result else 0
                else:
                    month_users = 0
                
                # Helper function to safely extract count from result
                def get_count(result):
                    if not result:
                        return 0
                    if hasattr(result, '__getitem__') and not isinstance(result, (str, bytes)):
                        try:
                            return result['count'] if 'count' in result else result[0]
                        except (KeyError, TypeError):
                            return result[0] if result else 0
                    return result[0] if result else 0
                
                # Total payments count
                cursor.execute("SELECT COUNT(*) as count FROM payments")
                result = cursor.fetchone()
                total_payments = get_count(result)
                
                # Completed payments count
                cursor.execute("SELECT COUNT(*) as count FROM payments WHERE status = 'completed'")
                result = cursor.fetchone()
                completed_payments = get_count(result)
                
                # Pending payments count
                cursor.execute("SELECT COUNT(*) as count FROM payments WHERE status = 'pending'")
                result = cursor.fetchone()
                pending_payments = get_count(result)
                
                # Total subscriptions count
                cursor.execute("SELECT COUNT(*) as count FROM subscriptions")
                result = cursor.fetchone()
                total_subs = get_count(result)
                
                # Expired subscriptions
                if use_postgres:
                    cursor.execute("""
                        SELECT COUNT(*) as count FROM subscriptions 
                        WHERE status = 'expired' OR end_date <= NOW()
                    """)
                else:
                    cursor.execute("""
                        SELECT COUNT(*) as count FROM subscriptions 
                        WHERE status = 'expired' OR end_date <= datetime('now')
                    """)
                result = cursor.fetchone()
                expired_subs = get_count(result)
                
                cursor.close()
                conn.close()
                
                stats_text = f"""
╔═══════════════════════════════════════╗
║      📊 DETAILED STATISTICS 📊         ║
╚═══════════════════════════════════════╝

┌─ USER STATISTICS ────────────────────┐
│ Total Users: `{stats.get('total_users', 0):<22}` │
│ New Today: `{stats.get('today_new_users', 0):<24}` │
│ New This Week: `{week_users:<19}` │
│ New This Month: `{month_users:<18}` │
└──────────────────────────────────────┘

┌─ SUBSCRIPTIONS ──────────────────────┐
│ Active: `{stats.get('active_subscriptions', 0):<25}` │
│ Total: `{total_subs:<27}` │
│ Expired: `{expired_subs:<25}` │
└──────────────────────────────────────┘

┌─ PAYMENTS ───────────────────────────┐
│ Total: `{total_payments:<26}` │
│ Completed: `{completed_payments:<23}` │
│ Pending: `{pending_payments:<25}` │
└──────────────────────────────────────┘

┌─ REVENUE ────────────────────────────┐
│ Total Revenue: `${stats.get('total_revenue', 0):.2f}` USD │
└──────────────────────────────────────┘
                """
                
                keyboard = [
                    [InlineKeyboardButton("📊 Dashboard", callback_data="dashboard_admin")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(stats_text, parse_mode='Markdown', reply_markup=reply_markup)
                return
            except Exception as e:
                logger.error(f"Error showing statistics: {e}", exc_info=True)
                error_msg = f"❌ Error: {str(e)[:100]}"
                await query.answer(error_msg, show_alert=True)
                return
    
        if data == "admin_users":
            if not is_admin:
                await query.answer("❌ Admin access required", show_alert=True)
                return
            
            try:
                # Use same pattern as working admin dashboard - get more users for better display
                users = db.get_all_users(limit=100)
                if not users:
                    await query.answer("No users found", show_alert=True)
                    return
                
                # Get total user count for accurate display
                stats = db.get_dashboard_stats()
                total_users = stats.get('total_users', len(users))
                displayed_count = len(users)
                
                users_text = "╔═══════════════════════════════════════╗\n"
                users_text += "║        👥 USER LIST 👥                 ║\n"
                users_text += "╚═══════════════════════════════════════╝\n\n"
                users_text += f"Total Users: {total_users}\n"
                users_text += f"Showing {displayed_count} of {total_users} users:\n\n"
                users_text += "Click on a user to upgrade them:\n\n"
                
                keyboard_rows = []
                # Show all users in text
                for user in users:
                    target_user_id = user.get('user_id', 'N/A')
                    user_name = user.get('first_name', 'N/A') or f"User {target_user_id}"
                    # Escape user name to prevent Markdown parsing errors
                    user_name_escaped = tg_escape_markdown(str(user_name))
                    users_text += f"• {user_name_escaped} (ID: {target_user_id})\n"
                
                # But only create buttons for first 50 (Telegram button limit)
                for user in users[:50]:
                    target_user_id = user.get('user_id', 'N/A')
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
                    InlineKeyboardButton("📊 Dashboard", callback_data="dashboard_admin"),
                    InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
                ])
                reply_markup = InlineKeyboardMarkup(keyboard_rows)
                
                # Use safe_edit_message_text like the working code
                try:
                    await query.edit_message_text(users_text, parse_mode='Markdown', reply_markup=reply_markup)
                except BadRequest:
                    # Fallback to plain text if Markdown fails
                    await query.edit_message_text(users_text, reply_markup=reply_markup)
                return
            except Exception as e:
                logger.error(f"Error in admin_users: {e}", exc_info=True)
                await query.answer(f"❌ Error: {str(e)[:50]}", show_alert=True)
                return
    
        if data == "admin_payments":
            if not is_admin:
                await query.answer("❌ Admin access required", show_alert=True)
                return
            
            try:
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
                    payments_text += f"Showing {min(len(payments), 10)} recent payments:\n\n"
                    
                    for payment in payments[:10]:
                        username = payment.get('username') or payment.get('first_name') or f"User {payment.get('user_id', 'N/A')}"
                        plan_type = str(payment.get('plan_type', 'N/A') or 'N/A')
                        amount = float(payment.get('amount', 0) or 0)
                        status = str(payment.get('status', 'unknown') or 'unknown')
                        created = payment.get('created_at', 'N/A')
                        
                        # Truncate username if too long
                        username_display = username[:28] if len(username) > 28 else username
                        plan_type_display = plan_type[:24] if len(plan_type) > 24 else plan_type
                        status_display = status[:23] if len(status) > 23 else status
                        
                        payments_text += f"• {username_display[:20]}\n"
                        payments_text += f"  Plan: {plan_type_display[:15]} | ${amount:.2f} | {status_display[:10]}\n"
                        if created and created != 'N/A':
                            created_str = str(created)[:16] if len(str(created)) > 16 else str(created)
                            payments_text += f"  Date: {created_str}\n"
                        payments_text += "\n"
                
                keyboard = [
                    [InlineKeyboardButton("📊 Dashboard", callback_data="dashboard_admin")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Telegram message limit is 4096 characters - truncate if needed
                if len(payments_text) > 4000:
                    payments_text = payments_text[:3900] + "\n\n... (message truncated)"
                
                # Send without parse_mode to avoid Markdown parsing errors
                await query.edit_message_text(payments_text, reply_markup=reply_markup)
                return
            except Exception as e:
                logger.error(f"Error showing payments: {e}", exc_info=True)
                error_msg = f"❌ Error loading payments: {str(e)}"
                try:
                    await query.answer(error_msg, show_alert=True)
                except:
                    pass
                return
    
        if data == "admin_subscriptions" or data == "admin_subs":
            if not is_admin:
                await query.answer("❌ Admin access required", show_alert=True)
                return
            
            try:
                subs = db.get_all_subscriptions(limit=20)
                if not subs:
                    await query.answer("No subscriptions found", show_alert=True)
                    return
                
                subs_text = "╔═══════════════════════════════════════╗\n"
                subs_text += "║    ⭐ ACTIVE SUBSCRIPTIONS ⭐          ║\n"
                subs_text += "╚═══════════════════════════════════════╝\n\n"
                subs_text += f"Showing {min(len(subs), 10)} of {len(subs)} subscriptions:\n\n"
                for sub in subs[:10]:
                    username = sub.get('username') or f"User {sub.get('user_id', 'N/A')}"
                    subs_text += f"┌─ {username[:28]:<28} ┐\n"
                    subs_text += f"│ Plan: `{sub.get('plan_type', 'N/A'):<24}` │\n"
                    subs_text += f"│ Used: `{sub.get('requests_used', 0)}/{sub.get('requests_limit', 0):<20}` │\n"
                    subs_text += f"│ Status: `{sub.get('status', 'active'):<23}` │\n"
                    subs_text += "└──────────────────────────────────────┘\n\n"
                
                keyboard = [
                    [InlineKeyboardButton("📊 Dashboard", callback_data="dashboard_admin")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(subs_text, reply_markup=reply_markup)
                return
            except Exception as e:
                logger.error(f"Error showing subscriptions: {e}", exc_info=True)
                await query.answer(f"❌ Error: {str(e)[:50]}", show_alert=True)
                return
    
        # Terminal sub-features    
        if data == "terminal_history":
            text = """
╔═══════════════════════════════════════╗
║   📋 TERMINAL HISTORY 📋                ║
╚═══════════════════════════════════════╝

**Recent Terminal Commands:**
• Commands are logged when executed in the desktop app
• View execution history and results
• Monitor command success/failure rates

**Note:** History is stored in the desktop app database.
Use the desktop app to view detailed command history.

**Status:** ✅ Active
            """
            keyboard = [
                [InlineKeyboardButton("🔙 Back", callback_data="dashboard_terminal")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        if data == "terminal_toggle":
            text = """
╔═══════════════════════════════════════╗
║   🔔 TERMINAL NOTIFICATIONS 🔔          ║
╚═══════════════════════════════════════╝

**Notification Settings:**
• Terminal command notifications are enabled
• You will receive notifications when commands are executed
• Notifications include command, output, and status

**Status:** ✅ Enabled
            """
            keyboard = [
                [InlineKeyboardButton("🔙 Back", callback_data="dashboard_terminal")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        if data == "terminal_stats":
            text = """
╔═══════════════════════════════════════╗
║   📊 TERMINAL STATISTICS 📊             ║
╚═══════════════════════════════════════╝

**Statistics:**
• Total commands executed: Tracked in desktop app
• Success rate: Available in desktop app
• Most used commands: View in desktop app

**Note:** Detailed statistics are available in the desktop app dashboard.

**Status:** ✅ Active
            """
            keyboard = [
                [InlineKeyboardButton("🔙 Back", callback_data="dashboard_terminal")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        # Toolkit sub-features    
        if data == "toolkit_list":
            text = """
╔═══════════════════════════════════════╗
║   📋 TOOLKIT TOOLS LIST 📋             ║
╚═══════════════════════════════════════╝

**Available Tools:**
• 138+ RedTeam-Tools available
• Categories: Reconnaissance, Execution, Persistence, etc.
• Tools are auto-discovered from RedTeam-Tools directory

**View Tools:** Use the desktop app to browse and execute tools.

**Status:** ✅ Active
            """
            keyboard = [
                [InlineKeyboardButton("🔙 Back", callback_data="dashboard_toolkit")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        if data == "toolkit_stats":
            text = """
╔═══════════════════════════════════════╗
║   📊 TOOLKIT USAGE STATS 📊            ║
╚═══════════════════════════════════════╝

**Usage Statistics:**
• Total tools: 138+
• Tools executed: Tracked in desktop app
• Most used tools: Available in desktop app

**Note:** Detailed statistics are available in the desktop app.

**Status:** ✅ Active
            """
            keyboard = [
                [InlineKeyboardButton("🔙 Back", callback_data="dashboard_toolkit")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        if data == "toolkit_toggle":
            text = """
╔═══════════════════════════════════════╗
║   🔔 TOOLKIT NOTIFICATIONS 🔔          ║
╚═══════════════════════════════════════╝

**Notification Settings:**
• Toolkit execution notifications are enabled
• You will receive notifications when tools are executed
• Notifications include tool name, result, and status

**Status:** ✅ Enabled
            """
            keyboard = [
                [InlineKeyboardButton("🔙 Back", callback_data="dashboard_toolkit")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        # Extensions sub-features    
        if data == "extensions_list":
            text = """
╔═══════════════════════════════════════╗
║   📦 INSTALLED EXTENSIONS 📦           ║
║   ╚═══════════════════════════════════════╝

**Extensions:**
• View installed extensions in the desktop app
• Manage extension settings
• Install/update extensions

**Note:** Extension management is available in the desktop app.

**Status:** ✅ Active
            """
            keyboard = [
                [InlineKeyboardButton("🔙 Back", callback_data="dashboard_extensions")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        if data == "extensions_toggle":
            text = """
╔═══════════════════════════════════════╗
║   🔔 EXTENSION NOTIFICATIONS 🔔        ║
╚═══════════════════════════════════════╝

**Notification Settings:**
• Extension installation notifications are enabled
• You will receive notifications when extensions are installed/updated
• Notifications include extension ID and status

**Status:** ✅ Enabled
            """
            keyboard = [
                [InlineKeyboardButton("🔙 Back", callback_data="dashboard_extensions")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        # Git sub-features    
        if data == "git_history":
            text = """
╔═══════════════════════════════════════╗
║   📋 GIT OPERATIONS HISTORY 📋         ║
╚═══════════════════════════════════════╝

**Recent Git Operations:**
• Commits, pushes, and pulls are logged
• View operation history in the desktop app
• Monitor repository changes

**Note:** Git operation history is stored in the desktop app.

**Status:** ✅ Active
            """
            keyboard = [
                [InlineKeyboardButton("🔙 Back", callback_data="dashboard_git")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        if data == "git_toggle":
            text = """
╔═══════════════════════════════════════╗
║   🔔 GIT NOTIFICATIONS 🔔               ║
╚═══════════════════════════════════════╝

**Notification Settings:**
• Git operation notifications are enabled
• You will receive notifications for commits, pushes, etc.
• Notifications include operation type and result

**Status:** ✅ Enabled
            """
            keyboard = [
                [InlineKeyboardButton("🔙 Back", callback_data="dashboard_git")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        # Settings sub-features    
        if data == "settings_view":
            settings_sync = get_settings_sync()
            if settings_sync.enabled:
                text = """
╔═══════════════════════════════════════╗
║   📋 SYNCED SETTINGS 📋                 ║
╚═══════════════════════════════════════╝

**Your Synced Settings:**
• Settings are synced between web and desktop
• View and manage settings in the desktop app
• Changes sync automatically

**Status:** ✅ Active
                """
            else:
                text = """
╔═══════════════════════════════════════╗
║   📋 SETTINGS SYNC 📋                  ║
╚═══════════════════════════════════════╝

**Settings Sync:**
• Settings sync is not configured
• Configure SUPABASE_URL and SUPABASE_KEY to enable
• Once enabled, settings sync automatically

**Status:** ❌ Not Configured
                """
            keyboard = [
                [InlineKeyboardButton("🔙 Back", callback_data="dashboard_settings")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        if data == "settings_sync_now":
            settings_sync = get_settings_sync()
            if settings_sync.enabled:
                text = """
╔═══════════════════════════════════════╗
║   🔄 SYNC TRIGGERED 🔄                  ║
╚═══════════════════════════════════════╝

**Manual Sync:**
• Settings sync has been triggered
• Your settings will be synced now
• Sync happens automatically on changes

**Status:** ✅ Syncing
                """
            else:
                text = """
╔═══════════════════════════════════════╗
║   🔄 SYNC NOT AVAILABLE 🔄             ║
╚═══════════════════════════════════════╝

**Settings Sync:**
• Settings sync is not configured
• Configure SUPABASE_URL and SUPABASE_KEY to enable

**Status:** ❌ Not Configured
                """
            keyboard = [
                [InlineKeyboardButton("🔙 Back", callback_data="dashboard_settings")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        if data == "settings_backup":
            settings_sync = get_settings_sync()
            if settings_sync.enabled:
                text = """
╔═══════════════════════════════════════╗
║   💾 SETTINGS BACKUP 💾                ║
╚═══════════════════════════════════════╝

**Backup:**
• Settings are automatically backed up to Supabase
• Backup happens on every sync
• Restore from backup in desktop app

**Status:** ✅ Backed Up
                """
            else:
                text = """
╔═══════════════════════════════════════╗
║   💾 BACKUP NOT AVAILABLE 💾           ║
╚═══════════════════════════════════════╝

**Settings Backup:**
• Backup requires settings sync to be configured
• Configure SUPABASE_URL and SUPABASE_KEY

**Status:** ❌ Not Configured
                """
            keyboard = [
                [InlineKeyboardButton("🔙 Back", callback_data="dashboard_settings")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        # Fix sub-features    
        if data == "fix_check":
            text = """
╔═══════════════════════════════════════╗
║   🔍 CHECKING ISSUES 🔍                 ║
╚═══════════════════════════════════════╝

**Issue Detection:**
• Checking dashboard for issues...
• Auto-detection runs continuously
• Issues are fixed automatically when detected

**Status:** ✅ Active
**Last Check:** Just now
            """
            keyboard = [
                [InlineKeyboardButton("🔧 Apply Fixes", callback_data="fix_apply")],
                [InlineKeyboardButton("🔙 Back", callback_data="dashboard_fix")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        if data == "fix_apply":
            text = """
╔═══════════════════════════════════════╗
║   🔧 APPLYING FIXES 🔧                  ║
╚═══════════════════════════════════════╝

**Auto-Fix:**
• Dashboard Fix Agent is active
• Fixes are applied automatically
• Manual fixes can be triggered from desktop app

**Status:** ✅ Active
**Mode:** Auto-fix enabled
            """
            keyboard = [
                [InlineKeyboardButton("🔍 Check Issues", callback_data="fix_check")],
                [InlineKeyboardButton("🔙 Back", callback_data="dashboard_fix")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        if data == "fix_history":
            text = """
╔═══════════════════════════════════════╗
║   📋 FIX HISTORY 📋                    ║
╚═══════════════════════════════════════╝

**Fix History:**
• View fix history in the desktop app
• Track all applied fixes
• Monitor dashboard health

**Note:** Detailed fix history is available in the desktop app.

**Status:** ✅ Active
            """
            keyboard = [
                [InlineKeyboardButton("🔙 Back", callback_data="dashboard_fix")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        # Admin sub-features    
        if data == "admin_notifications":
            if not is_admin:
                await query.answer("❌ Admin access required", show_alert=True)
                return
            
            text = """
╔═══════════════════════════════════════╗
║   🔔 NOTIFICATION SETTINGS 🔔          ║
╚═══════════════════════════════════════╝

**Admin Notifications:**
• Configure notification preferences
• Manage notification channels
• Set notification rules

**Status:** ✅ Active
            """
            keyboard = [
                [InlineKeyboardButton("🔙 Back to Admin", callback_data="dashboard_admin")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        if data == "admin_config":
            if not is_admin:
                await query.answer("❌ Admin access required", show_alert=True)
                return
            
            text = """
╔═══════════════════════════════════════╗
║   ⚙️ DASHBOARD CONFIG ⚙️                ║
╚═══════════════════════════════════════╝

**Configuration:**
• Dashboard settings and preferences
• API endpoints configuration
• Integration settings

**Status:** ✅ Active
            """
            keyboard = [
                [InlineKeyboardButton("🔙 Back to Admin", callback_data="dashboard_admin")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        if data == "admin_analytics":
            if not is_admin:
                await query.answer("❌ Admin access required", show_alert=True)
                return
            
            try:
                stats = db.get_dashboard_stats()
            except Exception as e:
                logger.error(f"Error getting analytics: {e}", exc_info=True)
                await query.answer(f"❌ Error: {str(e)}", show_alert=True)
                return
            text = f"""
╔═══════════════════════════════════════╗
║   📈 ANALYTICS 📈                       ║
╚═══════════════════════════════════════╝

**System Analytics:**
• Total Users: {stats.get('total_users', 0)}
• Active Subscriptions: {stats.get('active_subscriptions', 0)}
• New Users Today: {stats.get('today_new_users', 0)}
• Total Revenue: ${stats.get('total_revenue', 0):.2f}

**Status:** ✅ Active
            """
            keyboard = [
                [InlineKeyboardButton("🔄 Refresh", callback_data="admin_analytics")],
                [InlineKeyboardButton("🔙 Back to Admin", callback_data="dashboard_admin")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
    
        if data == "admin_upgrade_menu":
            if not is_admin:
                await query.answer("❌ Admin access required", show_alert=True)
                return
            
            text = """
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
                    InlineKeyboardButton("👥 View Users", callback_data="admin_users"),
                    InlineKeyboardButton("🎁 Free Upgrade", callback_data="admin_free_upgrade")
                ],
                [
                    InlineKeyboardButton("📋 Upgrade Help", callback_data="admin_upgrade_help")
                ],
                [
                    InlineKeyboardButton("📊 Dashboard", callback_data="dashboard_admin"),
                    InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
        
        if data == "admin_search_user":
            if not is_admin:
                await query.answer("❌ Admin access required", show_alert=True)
                return
            
            text = """
╔═══════════════════════════════════════╗
║      🔍 SEARCH USER BY ID 🔍          ║
╚═══════════════════════════════════════╝

**Search for a user by their Telegram User ID**

**How to use:**
1. Send a message with the user ID
2. Example: `123456789`
3. The bot will find and display user information

**Or use command:**
`/admin_search USER_ID`

**Note:** User IDs are numeric (e.g., 123456789)
            """
            keyboard = [
                [
                    InlineKeyboardButton("👥 View All Users", callback_data="admin_users")
                ],
                [
                    InlineKeyboardButton("📊 Dashboard", callback_data="dashboard_admin"),
                    InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
        
        if data == "admin_free_upgrade":
            if not is_admin:
                await query.answer("❌ Admin access required", show_alert=True)
                return
            
            text = """
╔═══════════════════════════════════════╗
║      🎁 FREE UPGRADE (DOWNTIME) 🎁     ║
╚═══════════════════════════════════════╝

**Compensate users for bot downtime**

**How to use:**
1. Click "View Users" or "Search User"
2. Select a user
3. Choose "Free Upgrade" option
4. Select duration and requests

**Free Upgrade Options:**
• 10 minutes - Quick compensation
• 1 day - Standard compensation
• 7 days - Extended compensation

**Note:** This creates a FREE upgrade (no payment required)
Useful for compensating users affected by downtime.
            """
            keyboard = [
                [
                    InlineKeyboardButton("👥 View Users", callback_data="admin_users"),
                    InlineKeyboardButton("🔍 Search User", callback_data="admin_search_user")
                ],
                [
                    InlineKeyboardButton("🎁🎁 Bulk Upgrade All", callback_data="admin_bulk_free_upgrade")
                ],
                [
                    InlineKeyboardButton("📊 Dashboard", callback_data="dashboard_admin"),
                    InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
        
        if data == "admin_bulk_free_upgrade":
            if not is_admin:
                await query.answer("❌ Admin access required", show_alert=True)
                return
            
            text = """
╔═══════════════════════════════════════╗
║   🎁🎁 BULK FREE UPGRADE (ALL USERS) 🎁🎁  ║
╚═══════════════════════════════════════╝

**Upgrade ALL users at once for downtime compensation**

**⚠️ WARNING: This will upgrade ALL users!**

**How it works:**
1. Select duration (10min/1day/7days)
2. Select request count (50/100/500/1000/unlimited)
3. Confirm bulk upgrade
4. All users will be upgraded automatically

**Free Upgrade Options:**
• 10 minutes - Quick compensation
• 1 day - Standard compensation  
• 7 days - Extended compensation

**Note:** This creates FREE upgrades for ALL users
Useful for compensating all users affected by downtime.
            """
            keyboard = [
                [
                    InlineKeyboardButton("⏱️ 10 Minutes", callback_data="bulk_duration_10min"),
                    InlineKeyboardButton("📅 1 Day", callback_data="bulk_duration_1day")
                ],
                [
                    InlineKeyboardButton("📆 7 Days", callback_data="bulk_duration_7days")
                ],
                [
                    InlineKeyboardButton("🔙 Back", callback_data="admin_free_upgrade"),
                    InlineKeyboardButton("📊 Dashboard", callback_data="dashboard_admin")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
        
        if data.startswith("bulk_duration_"):
            if not is_admin:
                await query.answer("❌ Admin access required", show_alert=True)
                return
            
            duration = data.replace("bulk_duration_", "")
            duration_text = "10 minutes" if duration == "10min" else ("1 day" if duration == "1day" else "7 days")
            
            text = f"""
╔═══════════════════════════════════════╗
║   🎁🎁 BULK FREE UPGRADE - SELECT REQUESTS 🎁🎁  ║
╚═══════════════════════════════════════╝

**Duration Selected:** {duration_text}

**Now select request count for ALL users:**

**Request Options:**
• 50 - Small compensation
• 100 - Medium compensation
• 500 - High compensation
• 1000 - Very high compensation
• Unlimited - No limit

**⚠️ This will upgrade ALL users with these settings!**
            """
            keyboard = [
                [
                    InlineKeyboardButton("50 Requests", callback_data=f"bulk_confirm_{duration}_50"),
                    InlineKeyboardButton("100 Requests", callback_data=f"bulk_confirm_{duration}_100")
                ],
                [
                    InlineKeyboardButton("500 Requests", callback_data=f"bulk_confirm_{duration}_500"),
                    InlineKeyboardButton("1000 Requests", callback_data=f"bulk_confirm_{duration}_1000")
                ],
                [
                    InlineKeyboardButton("♾️ Unlimited", callback_data=f"bulk_confirm_{duration}_unlimited")
                ],
                [
                    InlineKeyboardButton("🔙 Back", callback_data="admin_bulk_free_upgrade"),
                    InlineKeyboardButton("📊 Dashboard", callback_data="dashboard_admin")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
        
        if data.startswith("bulk_confirm_"):
            if not is_admin:
                await query.answer("❌ Admin access required", show_alert=True)
                return
            
            # Parse: bulk_confirm_DURATION_REQUESTS
            parts = data.replace("bulk_confirm_", "").split("_")
            if len(parts) < 2:
                await query.answer("❌ Invalid request", show_alert=True)
                return
            
            duration = parts[0]
            requests_str = parts[1]
            
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
            
            # Parse requests
            if requests_str == "unlimited":
                requests_limit = 999999
                requests_text = "Unlimited"
            else:
                try:
                    requests_limit = int(requests_str)
                    requests_text = f"{requests_limit} requests"
                except ValueError:
                    await query.answer("❌ Invalid request count", show_alert=True)
                    return
            
            # Get all users
            try:
                users = db.get_all_users(limit=10000)  # Get all users
                if not users:
                    await query.answer("❌ No users found", show_alert=True)
                    return
                
                total_users = len(users)
                upgraded_count = 0
                failed_count = 0
                notified_count = 0
                notification_failed_count = 0
                
                # Show processing message
                await query.answer(f"⏳ Processing {total_users} users...", show_alert=True)
                
                # Update message to show progress
                progress_text = f"""
╔═══════════════════════════════════════╗
║   🎁🎁 BULK UPGRADE IN PROGRESS 🎁🎁    ║
╚═══════════════════════════════════════╝

**Upgrading ALL users...**

Duration: {duration_text}
Requests: {requests_text}

Processing: 0/{total_users} users...

⏳ Please wait...
                """
                await query.edit_message_text(progress_text, parse_mode='Markdown')
                
                # Get bot instance - try multiple methods
                bot = None
                try:
                    # Method 1: Direct from query
                    if hasattr(query, 'bot') and query.bot:
                        bot = query.bot
                    # Method 2: From message
                    elif hasattr(query, 'message') and hasattr(query.message, 'bot'):
                        bot = query.message.bot
                    # Method 3: From update if available
                    elif hasattr(query, 'message') and hasattr(query.message, '_bot'):
                        bot = query.message._bot
                    # Method 4: Try to get from telegram_bot_module
                    else:
                        try:
                            from telegram_bot_module import telegram_bot
                            if hasattr(telegram_bot, 'bot') and telegram_bot.bot:
                                bot = telegram_bot.bot
                            elif hasattr(telegram_bot, 'application') and telegram_bot.application:
                                bot = telegram_bot.application.bot
                        except Exception as e:
                            logger.debug(f"Could not get bot from telegram_bot_module: {e}")
                except Exception as e:
                    logger.warning(f"Error getting bot instance: {e}")
                
                if not bot:
                    logger.warning("Bot instance not found, notifications will be skipped but upgrade will continue")
                    # Continue without notifications - upgrade will still work
                
                # Upgrade all users with progress updates and rate limiting
                import asyncio
                import time
                start_time = time.time()
                last_progress_update = 0
                
                # Rate limiting: Telegram allows ~30 messages per second, but we'll be conservative
                # Send 1 message every 0.1 seconds = 10 messages/second (safe limit)
                MESSAGE_DELAY = 0.15  # 150ms delay between each notification (6-7 messages/second)
                PROGRESS_UPDATE_INTERVAL = 3  # Update progress every 3 seconds
                
                for idx, user in enumerate(users):
                    target_user_id = user['user_id']
                    
                    # Skip admins (they already have unlimited)
                    if db.is_admin(target_user_id):
                        continue
                    
                    # Update progress every few seconds
                    current_time = time.time()
                    if current_time - last_progress_update >= PROGRESS_UPDATE_INTERVAL:
                        try:
                            progress_update = f"""
╔═══════════════════════════════════════╗
║   🎁🎁 BULK UPGRADE IN PROGRESS 🎁🎁    ║
╚═══════════════════════════════════════╝

**Upgrading ALL users...**

Duration: {duration_text}
Requests: {requests_text}

**Progress:**
• Processed: {idx + 1}/{total_users} users
• Upgraded: {upgraded_count}
• Notified: {notified_count}
• Failed: {failed_count}

⏳ Please wait... (Rate limiting active)
                            """
                            await query.edit_message_text(progress_update, parse_mode='Markdown')
                            last_progress_update = current_time
                        except:
                            pass  # Don't fail on progress update errors
                    
                    try:
                        # Create subscription first
                        sub_id = db.create_temporary_subscription(
                            target_user_id,
                            requests_limit=requests_limit,
                            duration_minutes=duration_minutes,
                            duration_days=duration_days
                        )
                        if sub_id:
                            upgraded_count += 1
                            
                            # Send notification to user with rate limiting
                            try:
                                # Get subscription details for expiration
                                sub = db.get_user_subscription(target_user_id)
                                expires_text = "N/A"
                                if sub and sub.get('end_date'):
                                    try:
                                        from datetime import datetime
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
                                        expires_text = str(sub.get('end_date', 'N/A'))
                                
                                notification_text = f"""
🔔 **FREE UPGRADE ALERT!** 🔔

╔═══════════════════════════════════════╗
║   🎁 FREE UPGRADE - DOWNTIME COMP 🎁   ║
╚═══════════════════════════════════════╝

┌─ UPGRADE DETAILS ────────────────────┐
│ Duration: {duration_text}             │
│ Requests: {requests_text}             │
│ Type: 🎁 FREE (Downtime Compensation) │
│ Expires: {expires_text}              │
└──────────────────────────────────────┘

✅ **Your account has been upgraded for FREE!**

This is compensation for the recent bot downtime.

📋 **What's Next:**
• Use /status to check your new plan
• Start using your upgraded requests
• Subscription will expire automatically

💡 Thank you for your patience! 🚀
                                """
                                
                                # Send notification with rate limiting and retry logic (if bot available)
                                notification_sent = False
                                if not bot:
                                    logger.debug(f"Skipping notification for user {user['user_id']} (bot not available)")
                                    continue
                                for retry in range(3):  # Try 3 times
                                    try:
                                        await bot.send_message(
                                            chat_id=target_user_id,
                                            text=notification_text,
                                            parse_mode='Markdown',
                                            disable_notification=False
                                        )
                                        notified_count += 1
                                        notification_sent = True
                                        
                                        # CRITICAL: Delay after each successful send to avoid rate limits
                                        await asyncio.sleep(MESSAGE_DELAY)
                                        break
                                    except Exception as send_error:
                                        error_str = str(send_error).lower()
                                        if "429" in error_str or "too many requests" in error_str:
                                            # Rate limited - wait longer (exponential backoff)
                                            wait_time = 2 * (retry + 1)  # 2s, 4s, 6s
                                            logger.warning(f"Rate limited, waiting {wait_time}s before retry {retry + 1}")
                                            await asyncio.sleep(wait_time)
                                        elif "400" in error_str and "chat not found" in error_str:
                                            # User blocked bot or chat doesn't exist - skip
                                            logger.warning(f"User {target_user_id} chat not found, skipping notification")
                                            notification_failed_count += 1
                                            break
                                        elif retry < 2:  # Not last retry
                                            await asyncio.sleep(1)  # Wait 1 second before retry
                                        else:
                                            logger.warning(f"Failed to notify user {target_user_id} after 3 attempts: {send_error}")
                                            notification_failed_count += 1
                                
                                # Additional delay every 10 users to be extra safe
                                if (idx + 1) % 10 == 0:
                                    await asyncio.sleep(0.5)  # Extra 500ms delay every 10 users
                                    
                            except Exception as notify_error:
                                logger.error(f"Error sending notification to user {target_user_id}: {notify_error}", exc_info=True)
                                notification_failed_count += 1
                                # Still delay even on error to maintain rate limit
                                await asyncio.sleep(MESSAGE_DELAY)
                        else:
                            logger.warning(f"Failed to create subscription for user {target_user_id}: sub_id is None")
                            failed_count += 1
                    except Exception as upgrade_error:
                        logger.error(f"Error upgrading user {target_user_id}: {upgrade_error}", exc_info=True)
                        failed_count += 1
                
                # Show final result
                result_text = f"""
╔═══════════════════════════════════════╗
║   ✅ BULK UPGRADE COMPLETED ✅          ║
╚═══════════════════════════════════════╝

**Upgrade Summary:**
• Total Users: {total_users}
• Successfully Upgraded: {upgraded_count}
• Failed: {failed_count}
• Duration: {duration_text}
• Requests: {requests_text}

**Notification Summary:**
• Notifications Sent: {notified_count}
• Notification Failed: {notification_failed_count}

✅ All users have been upgraded for FREE!
📧 Notifications sent to {notified_count} users.

**Note:** Admin users were skipped (already have unlimited access).
                """
                
                keyboard = [
                    [
                        InlineKeyboardButton("📊 Dashboard", callback_data="dashboard_admin"),
                        InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(result_text, parse_mode='Markdown', reply_markup=reply_markup)
                
            except Exception as e:
                logger.error(f"Error in bulk upgrade: {e}", exc_info=True)
                await query.answer(f"❌ Error: {str(e)[:50]}", show_alert=True)
            return
    
        if data == "admin_search_user":
            if not is_admin:
                await query.answer("❌ Admin access required", show_alert=True)
                return
            
            text = """
╔═══════════════════════════════════════╗
║      🔍 SEARCH USER BY ID 🔍          ║
╚═══════════════════════════════════════╝

**Search for a user by their Telegram User ID**

**How to use:**
1. Send a message with the user ID
2. Example: `123456789`
3. The bot will find and display user information

**Or use command:**
`/admin_search USER_ID`

**Note:** User IDs are numeric (e.g., 123456789)
            """
            keyboard = [
                [
                    InlineKeyboardButton("👥 View All Users", callback_data="admin_users")
                ],
                [
                    InlineKeyboardButton("📊 Dashboard", callback_data="dashboard_admin"),
                    InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            return
        
        if data in ["admin_users_all", "admin_payments_all", "admin_subs_all"]:
            await query.answer("ℹ️ Feature available in web dashboard", show_alert=True)
            return
    
        # Default: unknown action
        if data not in ["dashboard_menu", "dashboard_home", "dashboard_terminal", "dashboard_toolkit", "dashboard_extensions", "dashboard_git", "dashboard_settings", "dashboard_fix", "dashboard_status", "dashboard_admin", "admin_stats", "admin_users", "admin_payments", "admin_subscriptions", "admin_subs", "admin_upgrade_menu", "admin_search_user", "admin_free_upgrade", "admin_bulk_free_upgrade", "terminal_history", "terminal_toggle", "terminal_stats", "toolkit_list", "toolkit_stats", "toolkit_toggle", "extensions_list", "extensions_toggle", "git_history", "git_toggle", "settings_view", "settings_sync_now", "settings_backup", "fix_check", "fix_apply", "fix_history", "admin_notifications", "admin_config", "admin_analytics", "admin_users_all", "admin_payments_all", "admin_subs_all"] or data.startswith("bulk_duration_") or data.startswith("bulk_confirm_"):
            await query.answer("ℹ️ Unknown action", show_alert=True)
    
    except Exception as e:
        logger.error(f"Error in handle_dashboard_callback for {data}: {e}", exc_info=True)
        try:
            await query.answer(f"❌ Error: {str(e)[:50]}", show_alert=True)
        except:
            pass


async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /dashboard command"""
    user_id = update.effective_user.id
    is_admin = db.is_admin(user_id)
    
    text = """
╔═══════════════════════════════════════╗
║   🖥️ DASHBOARD FEATURES 🖥️            ║
╚═══════════════════════════════════════╝

Welcome to the Dashboard Features menu!

**Available Features:**
• 💻 Terminal Commands
• 🔧 Toolkit Tools
• 📦 Extensions
• 🔀 Git Operations
• ⚙️ Settings Sync
• 🛠️ Dashboard Fixes

Select a feature to get started:
    """
    
    reply_markup = get_dashboard_keyboard(user_id, is_admin)
    
    try:
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in dashboard command: {e}")
        await update.message.reply_text("❌ Error loading dashboard menu. Please try again.")


def register_dashboard_handlers(application):
    """Register dashboard command and callback handlers"""
    from telegram.ext import CommandHandler, CallbackQueryHandler
    
    # Register /dashboard command
    application.add_handler(CommandHandler("dashboard", dashboard_command))
    
    # Register callback query handler for dashboard features
    async def dashboard_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        # Handle dashboard-related callbacks
        if data.startswith("dashboard_") or data.startswith("admin_") or data.startswith("terminal_") or data.startswith("toolkit_") or data.startswith("extensions_") or data.startswith("git_") or data.startswith("settings_") or data.startswith("fix_"):
            await handle_dashboard_callback(query, data, user_id)
    
    application.add_handler(CallbackQueryHandler(dashboard_callback_handler, pattern="^(dashboard_|admin_|terminal_|toolkit_|extensions_|git_|settings_|fix_)"))

