#!/usr/bin/env python3
"""Quick script to add admin - user ID from logs: 5202575644"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path=".hacx")

# Import database
try:
    from database_hybrid import Database
except ImportError:
    from database import Database

# User ID from Railway logs
USER_ID = 5202575644

print("="*60)
print("ADDING ADMIN...")
print("="*60)
print(f"User ID: {USER_ID}")
print()

try:
    db = Database()
    
    # Check if already admin
    if db.is_admin(USER_ID):
        print(f"✅ User {USER_ID} is already an admin!")
    else:
        # Add as admin
        print(f"🔄 Adding user {USER_ID} as admin...")
        db.add_admin(USER_ID)
        
        # Verify
        if db.is_admin(USER_ID):
            print(f"✅ Successfully added user {USER_ID} as admin!")
            print()
            print("You can now:")
            print("  - Use /admin command")
            print("  - Access admin dashboard")
            print("  - Manage users and subscriptions")
        else:
            print(f"❌ Failed to add user {USER_ID} as admin")
            
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

