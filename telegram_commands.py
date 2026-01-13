"""
Telegram Bot Commands Handler
Commands to add to your Telegram bot for desktop app integration
"""

def handle_desktop_command(bot, message):
    """Handle /desktop command - Get desktop app download link"""
    from telegram_bot import github_release
    
    release = github_release.get_latest_release()
    if not release:
        bot.reply_to(message, "❌ Failed to get latest release information.")
        return
    
    assets = github_release.get_release_assets(release)
    
    reply = f"""🖥️ **Auto_Punch IDE Desktop**

📦 **Latest Version:** {assets['version']}
📅 **Released:** {assets['published_at'][:10] if assets['published_at'] else 'N/A'}

📥 **Download:**
"""
    
    if assets['exe_url']:
        reply += f"• [EXE Installer]({assets['exe_url']})\n"
    if assets['msi_url']:
        reply += f"• [MSI Installer]({assets['msi_url']})\n"
    
    if not assets['exe_url'] and not assets['msi_url']:
        reply += f"• [View Release]({release.get('html_url', '#')})\n"
    
    reply += "\n💡 The desktop app runs locally without a browser!"
    
    bot.reply_to(message, reply, parse_mode='Markdown')


def handle_desktop_update_command(bot, message):
    """Handle /desktop-update command - Check for desktop app updates"""
    from telegram_bot import github_release, settings_sync
    
    # Get user's current version (if registered)
    user_id = message.from_user.id
    user_settings = settings_sync.get_settings(user_id)
    current_version = user_settings.get('desktop_version', 'Unknown')
    
    # Get latest release
    release = github_release.get_latest_release()
    if not release:
        bot.reply_to(message, "❌ Failed to check for updates.")
        return
    
    latest_version = release.get('tag_name', 'Unknown')
    
    if current_version == 'Unknown':
        reply = f"""🆕 **Update Check**

📦 **Latest Version:** {latest_version}
📱 **Your Version:** Not registered

💡 Register your desktop app to track updates automatically.
Use `/desktop` to download the latest version."""
    elif current_version < latest_version:
        assets = github_release.get_release_assets(release)
        download_url = assets['exe_url'] or assets['msi_url'] or release.get('html_url', '#')
        
        reply = f"""🆕 **Update Available!**

📦 **Latest Version:** {latest_version}
📱 **Your Version:** {current_version}

📥 [Download Update]({download_url})

{release.get('body', '')[:200]}..."""
    else:
        reply = f"""✅ **You're Up to Date!**

📦 **Current Version:** {current_version}
📱 **Latest Version:** {latest_version}

No updates available."""
    
    bot.reply_to(message, reply, parse_mode='Markdown')


def handle_desktop_status_command(bot, message):
    """Handle /desktop-status command - Check desktop app status"""
    from telegram_bot import telegram_bot
    
    if telegram_bot.enabled:
        status = "✅ Connected"
        details = "Telegram integration is active and ready."
    else:
        status = "⚠️ Not Configured"
        details = "Telegram bot token and chat ID not set."
    
    reply = f"""🖥️ **Desktop App Status**

**Status:** {status}
{details}

**Features:**
• Desktop app notifications
• Settings sync
• Update notifications
• GitHub release webhooks"""
    
    bot.reply_to(message, reply, parse_mode='Markdown')


def handle_sync_settings_command(bot, message):
    """Handle /sync-settings command - Sync settings between web and desktop"""
    from telegram_bot import settings_sync
    
    user_id = message.from_user.id
    
    if not settings_sync.enabled:
        bot.reply_to(message, "❌ Settings sync not configured. Supabase credentials required.")
        return
    
    # Get current settings
    settings = settings_sync.get_settings(user_id)
    
    if settings:
        reply = f"""⚙️ **Settings Sync**

✅ Settings found for your account.

**Synced Settings:**
{', '.join(settings.keys()) if settings else 'None'}

💡 Your desktop app will automatically load these settings."""
    else:
        reply = """⚙️ **Settings Sync**

ℹ️ No settings found. Settings will be synced automatically when you:
• Change settings in the web version
• Change settings in the desktop app"""
    
    bot.reply_to(message, reply, parse_mode='Markdown')


# Command mapping for easy integration
COMMANDS = {
    'desktop': handle_desktop_command,
    'desktop-update': handle_desktop_update_command,
    'desktop-status': handle_desktop_status_command,
    'sync-settings': handle_sync_settings_command,
}


def register_commands(bot):
    """Register all commands with the bot"""
    @bot.message_handler(commands=['desktop'])
    def desktop_cmd(message):
        handle_desktop_command(bot, message)
    
    @bot.message_handler(commands=['desktop-update'])
    def desktop_update_cmd(message):
        handle_desktop_update_command(bot, message)
    
    @bot.message_handler(commands=['desktop-status'])
    def desktop_status_cmd(message):
        handle_desktop_status_command(bot, message)
    
    @bot.message_handler(commands=['sync-settings'])
    def sync_settings_cmd(message):
        handle_sync_settings_command(bot, message)

