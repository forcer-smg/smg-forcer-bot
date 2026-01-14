#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix telegram_bot.py by restoring from backup and integrating dashboard features
"""

import shutil
import os

def restore_bot_file():
    """Restore telegram_bot.py from backup"""
    if os.path.exists('telegram_bot.py.backup'):
        print("Restoring telegram_bot.py from backup...")
        shutil.copy2('telegram_bot.py.backup', 'telegram_bot.py')
        print("✅ Restored telegram_bot.py")
        return True
    else:
        print("❌ telegram_bot.py.backup not found!")
        return False

def integrate_dashboard_features():
    """Add dashboard features to telegram_bot.py"""
    if not os.path.exists('telegram_bot.py'):
        print("❌ telegram_bot.py not found!")
        return False
    
    with open('telegram_bot.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if dashboard features are already integrated
    if 'from dashboard_features import' in content:
        print("✅ Dashboard features already integrated")
        return True
    
    # Add import after other imports
    import_pos = content.find('from oxapay import OxaPay')
    if import_pos > 0:
        line_end = content.find('\n', import_pos)
        if line_end > 0:
            insert_pos = line_end + 1
            import_line = "from dashboard_features import handle_dashboard_callback, dashboard_command, register_dashboard_handlers\n"
            content = content[:insert_pos] + import_line + content[insert_pos:]
            print("✅ Added dashboard_features import")
    
    # Add dashboard handler registration in main()
    handler_pos = content.find('application.add_handler(CommandHandler("admin_upgrade", admin_upgrade))')
    if handler_pos > 0:
        line_end = content.find('\n', handler_pos)
        if line_end > 0:
            insert_pos = line_end + 1
            dashboard_registration = '    # Register dashboard handlers\n    register_dashboard_handlers(application)\n'
            content = content[:insert_pos] + dashboard_registration + content[insert_pos:]
            print("✅ Added dashboard handler registration")
    
    # Add dashboard callback handling in button_callback
    if 'async def button_callback' in content:
        callback_start = content.find('async def button_callback')
        if callback_start > 0:
            # Find query.answer() call
            answer_pos = content.find('await query.answer()', callback_start)
            if answer_pos > 0:
                answer_line_end = content.find('\n', answer_pos)
                if answer_line_end > 0:
                    insert_pos = answer_line_end + 1
                    dashboard_handler = """    # Handle dashboard callbacks FIRST
    if data.startswith("dashboard_") or data.startswith("admin_") or \\
       data.startswith("terminal_") or data.startswith("toolkit_") or \\
       data.startswith("extensions_") or data.startswith("git_") or \\
       data.startswith("settings_") or data.startswith("fix_"):
        await handle_dashboard_callback(query, data, user_id)
        return

"""
                    content = content[:insert_pos] + dashboard_handler + content[insert_pos:]
                    print("✅ Added dashboard callback handling")
    
    # Add dashboard button to start menu
    if 'InlineKeyboardButton("❓ Help"' in content:
        old_help = 'InlineKeyboardButton("❓ Help", callback_data="menu_help"),\n                InlineKeyboardButton("💳 Subscribe", callback_data="menu_subscribe")'
        new_help = 'InlineKeyboardButton("🖥️ Dashboard", callback_data="dashboard_menu"),\n                InlineKeyboardButton("❓ Help", callback_data="menu_help")\n            ],\n            [\n                InlineKeyboardButton("💳 Subscribe", callback_data="menu_subscribe")'
        if old_help in content:
            content = content.replace(old_help, new_help)
            print("✅ Added Dashboard button to main menu")
    
    # Write updated content
    with open('telegram_bot.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Dashboard features integrated")
    return True

if __name__ == '__main__':
    print("=" * 60)
    print("Fixing telegram_bot.py")
    print("=" * 60)
    print()
    
    if restore_bot_file():
        if integrate_dashboard_features():
            print()
            print("=" * 60)
            print("✅ FIX COMPLETE!")
            print("=" * 60)
            print()
            print("Next steps:")
            print("1. Commit the fix: git add telegram_bot.py")
            print("2. Commit: git commit -m 'Fix bot file and integrate dashboard'")
            print("3. Push: git push origin main")
        else:
            print("⚠️  Could not integrate dashboard features")
    else:
        print("❌ Could not restore bot file")

