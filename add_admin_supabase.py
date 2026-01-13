#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Add Admin to Supabase Database
Uses DATABASE_URL from environment (Railway) to add admin directly
"""

import os
import sys

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    print("[ERROR] psycopg2 not installed. Install with: pip install psycopg2-binary")
    sys.exit(1)

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

def add_admin_to_supabase(database_url: str, user_id: int):
    """Add admin to Supabase database"""
    print(f"\n{'='*60}")
    print(f"  Adding Admin to Supabase")
    print(f"{'='*60}\n")
    
    try:
        # Connect to Supabase
        print_status("INFO", "Connecting to Supabase...")
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        # Ensure admins table exists
        print_status("INFO", "Checking admins table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id BIGINT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        print_status("OK", "Admins table exists")
        
        # Check if already admin
        cursor.execute("SELECT 1 FROM admins WHERE user_id = %s", (user_id,))
        if cursor.fetchone():
            print_status("OK", f"User {user_id} is already an admin")
            cursor.close()
            conn.close()
            return True
        
        # Add as admin
        print_status("INFO", f"Adding user {user_id} as admin...")
        cursor.execute("""
            INSERT INTO admins (user_id) 
            VALUES (%s)
            ON CONFLICT (user_id) DO NOTHING
        """, (user_id,))
        conn.commit()
        
        # Verify
        cursor.execute("SELECT 1 FROM admins WHERE user_id = %s", (user_id,))
        if cursor.fetchone():
            print_status("OK", f"Successfully added user {user_id} as admin in Supabase!")
            cursor.close()
            conn.close()
            return True
        else:
            print_status("ERROR", "Failed to add admin (verification failed)")
            cursor.close()
            conn.close()
            return False
            
    except Exception as e:
        print_status("ERROR", f"Error adding admin: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main function"""
    print(f"\n{'='*60}")
    print(f"  Add Admin to Supabase")
    print(f"{'='*60}\n")
    
    # Get user ID
    if len(sys.argv) > 1:
        try:
            user_id = int(sys.argv[1])
        except ValueError:
            print_status("ERROR", f"Invalid user ID: {sys.argv[1]}")
            print("  Usage: python add_admin_supabase.py [user_id] [DATABASE_URL]")
            print("  Or set DATABASE_URL environment variable")
            return 1
    else:
        print("Please enter your Telegram User ID:")
        try:
            user_id = int(input("User ID: "))
        except ValueError:
            print_status("ERROR", "Invalid user ID")
            return 1
    
    # Get DATABASE_URL
    if len(sys.argv) > 2:
        database_url = sys.argv[2]
    else:
        database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        print_status("ERROR", "DATABASE_URL not found!")
        print("\nOptions:")
        print("  1. Set DATABASE_URL environment variable")
        print("  2. Pass it as argument: python add_admin_supabase.py [user_id] [DATABASE_URL]")
        print("\nTo get DATABASE_URL from Railway:")
        print("  1. Go to Railway → Your Project → Variables")
        print("  2. Copy the DATABASE_URL value")
        print("  3. Set it as environment variable or pass as argument")
        return 1
    
    # Verify it's PostgreSQL
    if not database_url.startswith("postgresql://"):
        print_status("ERROR", "DATABASE_URL doesn't look like a PostgreSQL connection string")
        print(f"  Got: {database_url[:50]}...")
        return 1
    
    print_status("OK", f"Using DATABASE_URL: {database_url[:50]}...")
    
    # Add admin
    success = add_admin_to_supabase(database_url, user_id)
    
    if success:
        print(f"\n{'='*60}")
        print(f"  Success!")
        print(f"{'='*60}\n")
        print_status("OK", f"User {user_id} is now an admin in Supabase")
        print("\nNext steps:")
        print("  1. The bot on Railway should automatically use this admin")
        print("  2. Try /admin command in Telegram")
        print("  3. If it still doesn't work, restart the bot on Railway")
        return 0
    else:
        print_status("ERROR", "Failed to add admin")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n[WARNING] Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
