#!/usr/bin/env python3
"""Directly add admin to database"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path=".hacx")

# Import database
try:
    from database_hybrid import Database
    print("Using hybrid database (auto-detects SQLite/PostgreSQL)")
except ImportError:
    from database import Database
    print("Using SQLite database")

# User ID from Railway logs
USER_ID = 5202575644

print("="*60)
print("ADDING ADMIN TO DATABASE")
print("="*60)
print(f"User ID: {USER_ID}")
print()

# Check which database we're using
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    print(f"✅ DATABASE_URL found - Using PostgreSQL/Supabase")
    print(f"   Host: {DATABASE_URL.split('@')[1].split('/')[0] if '@' in DATABASE_URL else 'N/A'}")
else:
    print("⚠️  DATABASE_URL not found - Using SQLite (local)")
print()

try:
    print("🔄 Connecting to database...")
    db = Database()
    print("✅ Connected!")
    print()
    
    # Check if already admin
    print(f"🔍 Checking if user {USER_ID} is already admin...")
    if db.is_admin(USER_ID):
        print(f"✅ User {USER_ID} is already an admin!")
        print()
        print("You can now use:")
        print("  - /admin command in Telegram")
        print("  - Admin dashboard")
        print("  - All admin features")
    else:
        # Add as admin
        print(f"🔄 Adding user {USER_ID} as admin...")
        db.add_admin(USER_ID)
        print("✅ Admin added!")
        
        # Verify
        print(f"🔍 Verifying...")
        if db.is_admin(USER_ID):
            print(f"✅ Successfully added user {USER_ID} as admin!")
            print()
            print("="*60)
            print("SUCCESS! You are now an admin!")
            print("="*60)
            print()
            print("You can now:")
            print("  ✅ Use /admin command in Telegram")
            print("  ✅ Access admin dashboard")
            print("  ✅ Manage users and subscriptions")
            print("  ✅ View statistics and payments")
            print("  ✅ Upgrade users manually")
        else:
            print(f"❌ Failed to verify admin status")
            
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("="*60)

