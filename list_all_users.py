#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
List all users currently using the bot
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OUTPUT_FILE = "list_all_users_output.txt"

def collect_output():
    lines = []

    def add(line=""):
        print(line)
        lines.append(line)

    try:
        from database import Database

        db = Database()

        # Get total count
        stats = db.get_dashboard_stats()
        total_users = stats['total_users']

        # Get all users (no limit)
        all_users = db.get_all_users(limit=10000, offset=0)

        add("\n" + "="*70)
        add("  ALL USERS CURRENTLY USING THE BOT")
        add("="*70)
        add(f"\n📊 Total Users in Database: {total_users}")
        add(f"📋 Users Retrieved: {len(all_users)}")
        add("\n" + "-"*70)

        if not all_users:
            add("❌ No users found in database.")
        else:
            add(f"\n{'#':<5} {'User ID':<15} {'Name':<25} {'Username':<20} {'Status':<15}")
            add("-"*70)

            for i, user in enumerate(all_users, 1):
                user_id = user['user_id']
                name = user.get('first_name', 'N/A') or 'N/A'
                username = user.get('username', 'N/A') or 'N/A'
                status = user.get('current_status', 'free') or 'free'

                # Truncate long names/usernames
                name = name[:24] if len(name) > 24 else name
                username = username[:19] if len(username) > 19 else username

                add(f"{i:<5} {user_id:<15} {name:<25} @{username:<19} {status:<15}")

            add("-"*70)
            add(f"\n✅ Total: {len(all_users)} users")

        add("\n" + "="*70 + "\n")

        return True, "\n".join(lines)

    except Exception as e:
        error_lines = [f"\n❌ Error: {e}"]
        print(error_lines[0])
        import traceback
        tb = traceback.format_exc()
        print(tb)
        error_lines.append(tb)
        return False, "\n".join(error_lines)


if __name__ == "__main__":
    success, output = collect_output()
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"\n📄 Full report saved to {OUTPUT_FILE}")
        if success:
            print("Open this file to view all users.")
    except Exception as file_error:
        print(f"⚠️ Could not save output file: {file_error}")

