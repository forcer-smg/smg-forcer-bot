#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Final user count check - guaranteed to work"""

import sqlite3
import os

DB = "smg_forcer.db"
OUT = "FINAL_USER_COUNT.txt"

if os.path.exists(DB):
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    cursor.execute("SELECT user_id, username, first_name, created_at FROM users ORDER BY created_at DESC")
    users = cursor.fetchall()
    conn.close()
    
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write("="*70 + "\n")
        f.write("  FINAL USER COUNT VERIFICATION\n")
        f.write("="*70 + "\n\n")
        f.write(f"TOTAL USERS: {count}\n\n")
        f.write("ALL USERS:\n")
        f.write("-"*70 + "\n")
        for i, (uid, uname, fname, created) in enumerate(users, 1):
            f.write(f"{i}. ID: {uid} | Name: {fname or 'N/A'} | Username: @{uname or 'N/A'} | Created: {created or 'N/A'}\n")
        f.write("-"*70 + "\n")
        f.write(f"\n✅ CONFIRMED: {count} Telegram users have interacted with the bot\n")
    
    print(f"✅ Total users: {count}")
    print(f"✅ Report saved to: {OUT}")
    for i, (uid, uname, fname, created) in enumerate(users, 1):
        print(f"  {i}. {fname or 'N/A'} (@{uname or 'N/A'}) - ID: {uid}")
else:
    print(f"❌ Database not found: {DB}")

