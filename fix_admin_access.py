#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix Admin Access - Ensures admins table exists and adds user as admin
Works with both PostgreSQL/Supabase and SQLite
"""

import os
import sys

# Try to load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not installed, continue without it (env vars from system will be used)
    pass

def print_header(text: str):
    """Print formatted header"""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)

def print_status(status: str, message: str):
    """Print status message"""
    if status == "OK":
        symbol = "[OK]"
    elif status == "ERROR":
        symbol = "[ERROR]"
    elif status == "WARNING":
        symbol = "[WARNING]"
    else:
        symbol = "[INFO]"
    print(f"{symbol} {message}")

def ensure_admins_table(db):
    """Ensure admins table exists"""
    print_header("Ensuring Admins Table Exists")
    
    try:
        # Initialize database (this creates tables if they don't exist)
        db.init_database()
        print_status("OK", "Database initialized - admins table should exist")
        
        # Verify table exists
        database_url = os.getenv("DATABASE_URL")
        if database_url and database_url.startswith("postgresql://"):
            # PostgreSQL
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'admins'
                )
            """)
            table_exists = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            
            if table_exists:
                print_status("OK", "Admins table verified in PostgreSQL/Supabase")
                return True
            else:
                print_status("ERROR", "Admins table still doesn't exist after initialization")
                return False
        else:
            # SQLite
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='admins'
            """)
            table_exists = cursor.fetchone() is not None
            cursor.close()
            conn.close()
            
            if table_exists:
                print_status("OK", "Admins table verified in SQLite")
                return True
            else:
                print_status("ERROR", "Admins table still doesn't exist after initialization")
                return False
                
    except Exception as e:
        print_status("ERROR", f"Error ensuring admins table: {e}")
        import traceback
        traceback.print_exc()
        return False

def add_user_as_admin(db, user_id):
    """Add user as admin"""
    print_header(f"Adding User {user_id} as Admin")
    
    try:
        # Check if already admin
        if db.is_admin(user_id):
            print_status("OK", f"User {user_id} is already an admin")
            return True
        
        # Add as admin
        print_status("INFO", f"Adding user {user_id} as admin...")
        db.add_admin(user_id)
        
        # Verify
        if db.is_admin(user_id):
            print_status("OK", f"Successfully added user {user_id} as admin")
            return True
        else:
            print_status("ERROR", f"Failed to add user {user_id} as admin (verification failed)")
            return False
            
    except Exception as e:
        print_status("ERROR", f"Error adding admin: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main fix function"""
    print_header("Fix Admin Access Tool")
    print("This script will:")
    print("  1. Ensure the admins table exists")
    print("  2. Add your user ID as an admin")
    print("  3. Verify admin access")
    
    # Get user ID from command line or ask
    if len(sys.argv) > 1:
        try:
            user_id = int(sys.argv[1])
        except ValueError:
            print_status("ERROR", f"Invalid user ID: {sys.argv[1]}")
            print("  Usage: python fix_admin_access.py [user_id]")
            return 1
    else:
        print("\nPlease enter your Telegram User ID:")
        print("(You can get it by messaging @userinfobot on Telegram)")
        try:
            user_id = int(input("User ID: "))
        except ValueError:
            print_status("ERROR", "Invalid user ID")
            return 1
    
    # Check database type
    database_url = os.getenv("DATABASE_URL")
    if database_url and database_url.startswith("postgresql://"):
        print_status("INFO", "Using PostgreSQL/Supabase database")
    else:
        print_status("WARNING", "Using SQLite database (not Supabase)")
        print("  Note: If you're using Supabase, make sure DATABASE_URL is set correctly")
    
    # Initialize database
    try:
        from database_hybrid import Database
        db = Database()
        print_status("OK", "Database connection successful")
    except Exception as e:
        print_status("ERROR", f"Database connection failed: {e}")
        print("\nTroubleshooting:")
        print("  1. Check if DATABASE_URL is set correctly in Railway")
        print("  2. Check if DATABASE_URL is in .env file")
        print("  3. Verify database credentials")
        return 1
    
    # Ensure admins table exists
    if not ensure_admins_table(db):
        print_status("ERROR", "Failed to ensure admins table exists")
        print("\nTroubleshooting:")
        print("  1. Check database connection")
        print("  2. Check database permissions")
        print("  3. Try running restore_supabase_database.py if using Supabase")
        return 1
    
    # Add user as admin
    if not add_user_as_admin(db, user_id):
        print_status("ERROR", "Failed to add user as admin")
        return 1
    
    # Success
    print_header("Success!")
    print_status("OK", f"User {user_id} is now an admin")
    print("\nNext steps:")
    print("  1. Restart the bot on Railway (if deployed)")
    print("  2. Try /admin command in Telegram")
    print("  3. If it still doesn't work, check Railway logs for errors")
    
    return 0

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n[WARNING] Fix interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
