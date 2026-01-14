#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automated Dashboard Features Integration Script
Adds dashboard features with inline keyboards to the Telegram bot
"""

import os
import re
import shutil
from pathlib import Path

def backup_file(filepath):
    """Create backup of file"""
    backup_path = f"{filepath}.backup2"
    if os.path.exists(filepath):
        shutil.copy2(filepath, backup_path)
        print(f"✅ Backed up {filepath} to {backup_path}")
        return True
    return False

def add_dashboard_button_to_menu():
    """Add dashboard button to main menu in start() function"""
    filepath = "telegram_bot.py"
    
    if not os.path.exists(filepath):
        print(f"❌ {filepath} not found. Please restore from backup first.")
        return False
    
    # Read file
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if already integrated
    if "dashboard_menu" in content and "🖥️ Dashboard" in content:
        print("✅ Dashboard button already integrated!")
        return True
    
    # Find the keyboard section in start() function
    # Look for the keyboard array pattern
    pattern = r'(\s+keyboard = \[.*?\]\s+keyboard\.append\(get_support_button_row\(\)\))'
    
    # More specific pattern for the keyboard
    keyboard_pattern = r'(keyboard = \[\s+\[\s+InlineKeyboardButton\("📊 My Status"'
    
    # Try to find and replace the keyboard section
    old_keyboard = """        keyboard = [
            [
                InlineKeyboardButton("📊 My Status", callback_data="menu_status"),
                InlineKeyboardButton("💎 Plans", callback_data="menu_plans")
            ],
            [
                InlineKeyboardButton("🎁 Referral", callback_data="menu_referral"),
                InlineKeyboardButton("🆕 New Chat", callback_data="menu_new")
            ],
            [
                InlineKeyboardButton("❓ Help", callback_data="menu_help"),
                InlineKeyboardButton("💳 Subscribe", callback_data="menu_subscribe")
            ]
        ]"""
    
    new_keyboard = """        keyboard = [
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
        ]"""
    
    if old_keyboard in content:
        content = content.replace(old_keyboard, new_keyboard)
        print("✅ Added Dashboard button to main menu")
    else:
        print("⚠️  Could not find exact keyboard pattern. Manual integration may be needed.")
        print("   See INTEGRATE_DASHBOARD_KEYBOARDS.md for manual steps.")
        return False
    
    # Add import at the top
    import_pattern = r'(from telegram import.*?\n)'
    if 'from dashboard_features import' not in content:
        # Find the last import statement
        imports_end = content.find('from database')
        if imports_end == -1:
            imports_end = content.find('from HacxGPT')
        
        if imports_end > 0:
            # Find the end of that import line
            line_end = content.find('\n', imports_end)
            if line_end > 0:
                insert_pos = line_end + 1
                import_line = "from dashboard_features import handle_dashboard_callback, dashboard_command, register_dashboard_handlers\n"
                content = content[:insert_pos] + import_line + content[insert_pos:]
                print("✅ Added dashboard_features import")
    
    # Add dashboard callback handling in button_callback function
    if 'async def button_callback' in content:
        # Check if already added
        if 'if data.startswith("dashboard_")' not in content:
            # Find the button_callback function start
            callback_start = content.find('async def button_callback')
            if callback_start > 0:
                # Find the first line after function definition
                first_line = content.find('\n', callback_start)
                if first_line > 0:
                    # Find the indentation level
                    indent = 0
                    for i in range(first_line + 1, min(first_line + 100, len(content))):
                        if content[i] == ' ':
                            indent += 1
                        elif content[i] == '\t':
                            indent += 1
                        else:
                            break
                    
                    indent_str = '    '  # 4 spaces
                    
                    # Add dashboard callback handling
                    dashboard_handler = f"""{indent_str}# Handle dashboard callbacks FIRST
{indent_str}if data.startswith("dashboard_") or data.startswith("admin_") or \\
{indent_str}   data.startswith("terminal_") or data.startswith("toolkit_") or \\
{indent_str}   data.startswith("extensions_") or data.startswith("git_") or \\
{indent_str}   data.startswith("settings_") or data.startswith("fix_"):
{indent_str}    await handle_dashboard_callback(query, data, user_id)
{indent_str}    return

"""
                    
                    # Insert after query.answer()
                    answer_pos = content.find('await query.answer()', first_line)
                    if answer_pos > 0:
                        answer_line_end = content.find('\n', answer_pos)
                        if answer_line_end > 0:
                            insert_pos = answer_line_end + 1
                            content = content[:insert_pos] + dashboard_handler + content[insert_pos:]
                            print("✅ Added dashboard callback handling")
    
    # Add dashboard handler registration in main()
    if 'def main():' in content:
        # Check if already registered
        if 'register_dashboard_handlers' not in content or 'application.add_handler(CommandHandler("dashboard"' not in content:
            # Find where handlers are registered
            handler_pos = content.find('application.add_handler(CommandHandler("admin"')
            if handler_pos > 0:
                # Find the end of that line
                line_end = content.find('\n', handler_pos)
                if line_end > 0:
                    insert_pos = line_end + 1
                    dashboard_registration = '    # Register dashboard handlers\n    register_dashboard_handlers(application)\n'
                    content = content[:insert_pos] + dashboard_registration + content[insert_pos:]
                    print("✅ Added dashboard handler registration")
    
    # Write updated content
    backup_file(filepath)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Successfully integrated dashboard features into {filepath}")
    return True

def main():
    print("=" * 60)
    print("Dashboard Features Integration Script")
    print("=" * 60)
    print()
    
    # Check if telegram_bot.py exists
    if not os.path.exists("telegram_bot.py"):
        if os.path.exists("telegram_bot.py.backup"):
            print("📋 Restoring telegram_bot.py from backup...")
            shutil.copy2("telegram_bot.py.backup", "telegram_bot.py")
            print("✅ Restored telegram_bot.py")
        else:
            print("❌ telegram_bot.py not found and no backup available!")
            print("   Please ensure telegram_bot.py exists before running this script.")
            return
    
    # Check if dashboard_features.py exists
    if not os.path.exists("dashboard_features.py"):
        print("❌ dashboard_features.py not found!")
        print("   Please ensure dashboard_features.py exists in the same directory.")
        return
    
    print("✅ dashboard_features.py found")
    print()
    
    # Integrate dashboard features
    print("🔄 Integrating dashboard features...")
    if add_dashboard_button_to_menu():
        print()
        print("=" * 60)
        print("✅ INTEGRATION COMPLETE!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Review the changes in telegram_bot.py")
        print("2. Test the bot: python telegram_bot.py")
        print("3. Use /start to see the new Dashboard button")
        print("4. Click '🖥️ Dashboard' to access features")
        print()
        print("For manual integration, see: INTEGRATE_DASHBOARD_KEYBOARDS.md")
    else:
        print()
        print("⚠️  Automatic integration had issues.")
        print("   Please follow manual integration steps in:")
        print("   INTEGRATE_DASHBOARD_KEYBOARDS.md")

if __name__ == "__main__":
    main()

