#!/usr/bin/env python3
"""
Add yourself as admin to the Telegram bot
Run this script and provide your Telegram user ID
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path=".hacx")

# Import database
try:
    from database_hybrid import Database
except ImportError:
    from database import Database

def get_user_id_from_telegram():
    """Instructions to get Telegram user ID"""
    print("\n" + "="*60)
    print("HOW TO GET YOUR TELEGRAM USER ID:")
    print("="*60)
    print("\nOption 1: Use @userinfobot on Telegram")
    print("  1. Open Telegram")
    print("  2. Search for @userinfobot")
    print("  3. Start a chat with it")
    print("  4. It will show your user ID")
    print("\nOption 2: Check bot logs")
    print("  - Look for your user_id in Railway logs")
    print("  - It's the number that appears when you send /start")
    print("\nOption 3: Use @getidsbot")
    print("  1. Search for @getidsbot on Telegram")
    print("  2. Start a chat")
    print("  3. It will show your ID")
    print("="*60 + "\n")

def add_admin(user_id):
    """Add user as admin"""
    try:
        db = Database()
        
        # Check if already admin
        if db.is_admin(user_id):
            print(f"✅ User {user_id} is already an admin!")
            return True
        
        # Add as admin
        db.add_admin(user_id)
        
        # Verify
        if db.is_admin(user_id):
            print(f"✅ Successfully added user {user_id} as admin!")
            return True
        else:
            print(f"❌ Failed to add user {user_id} as admin")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n" + "="*60)
    print("ADD ADMIN TO TELEGRAM BOT")
    print("="*60)
    
    # Show instructions
    get_user_id_from_telegram()
    
    # Get user ID
    user_id_input = input("Enter your Telegram User ID: ").strip()
    
    if not user_id_input:
        print("❌ User ID cannot be empty!")
        return
    
    try:
        user_id = int(user_id_input)
    except ValueError:
        print("❌ Invalid user ID! Must be a number.")
        return
    
    # Confirm
    print(f"\n⚠️  You are about to add user ID {user_id} as admin.")
    confirm = input("Continue? (yes/no): ").strip().lower()
    
    if confirm not in ['yes', 'y']:
        print("❌ Cancelled.")
        return
    
    # Add admin
    print(f"\n🔄 Adding user {user_id} as admin...")
    success = add_admin(user_id)
    
    if success:
        print("\n✅ Done! You can now use admin commands in the bot.")
        print("   Try: /admin or use the admin dashboard")
    else:
        print("\n❌ Failed to add admin. Check the error above.")

if __name__ == "__main__":
    main()
