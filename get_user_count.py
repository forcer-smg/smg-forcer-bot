#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quick script to get user count"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from database import Database
    
    db = Database()
    stats = db.get_dashboard_stats()
    
    print("\n" + "="*50)
    print("  SMG-Forcer Telegram Bot - User Count")
    print("="*50)
    print(f"\n👥 Total Users: {stats['total_users']}")
    print(f"✅ Active Subscriptions: {stats['active_subscriptions']}")
    print(f"🆕 New Users Today: {stats['today_new_users']}")
    print(f"💰 Total Revenue: ${stats['total_revenue']:.2f} USD")
    print("\n" + "="*50)
    print(f"\n✅ Currently using the bot: {stats['total_users']} total users")
    print("="*50 + "\n")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

