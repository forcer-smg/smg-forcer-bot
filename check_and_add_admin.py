#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check and Add Admin to Supabase
Connects to Supabase and checks/adds admin users
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logger.error("psycopg2 not installed. Install with: pip install psycopg2-binary")
    sys.exit(1)

def get_connection():
    """Get Supabase PostgreSQL connection"""
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        logger.error("DATABASE_URL environment variable not set!")
        logger.error("Set it in Railway Variables or .env file")
        sys.exit(1)
    
    try:
        conn = psycopg2.connect(database_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)

def check_admins():
    """Check all admins in the database"""
    logger.info("=" * 60)
    logger.info("CHECKING ADMINS IN SUPABASE")
    logger.info("=" * 60)
    logger.info("")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Check if admins table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'admins'
            )
        """)
        table_exists = cursor.fetchone()[0]
        
        if not table_exists:
            logger.error("Admins table does not exist!")
            logger.info("Run restore_supabase_database.py first to create tables")
            return []
        
        # Get all admins
        cursor.execute("""
            SELECT a.user_id, u.username, u.first_name, a.created_at
            FROM admins a
            LEFT JOIN users u ON a.user_id = u.user_id
            ORDER BY a.created_at DESC
        """)
        
        admins = cursor.fetchall()
        
        logger.info(f"Found {len(admins)} admin(s):")
        logger.info("")
        
        if not admins:
            logger.warning("No admins found in database!")
        else:
            for admin in admins:
                user_id, username, first_name, created_at = admin
                logger.info(f"  - User ID: {user_id}")
                logger.info(f"    Username: @{username or 'N/A'}")
                logger.info(f"    Name: {first_name or 'N/A'}")
                logger.info(f"    Added: {created_at}")
                logger.info("")
        
        cursor.close()
        conn.close()
        
        return admins
        
    except Exception as e:
        logger.error(f"Error checking admins: {e}")
        import traceback
        traceback.print_exc()
        cursor.close()
        conn.close()
        return []

def add_admin(user_id: int):
    """Add a user as admin"""
    logger.info("=" * 60)
    logger.info(f"ADDING USER {user_id} AS ADMIN")
    logger.info("=" * 60)
    logger.info("")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # First, ensure user exists in users table
        cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
        user_exists = cursor.fetchone()
        
        if not user_exists:
            logger.warning(f"User {user_id} does not exist in users table. Creating user...")
            cursor.execute("""
                INSERT INTO users (user_id, username, first_name, created_at)
                VALUES (%s, 'admin', 'Admin User', CURRENT_TIMESTAMP)
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id,))
            logger.info(f"Created user {user_id}")
        
        # Check if already admin
        cursor.execute("SELECT user_id FROM admins WHERE user_id = %s", (user_id,))
        already_admin = cursor.fetchone()
        
        if already_admin:
            logger.warning(f"User {user_id} is already an admin!")
            return False
        
        # Add as admin
        cursor.execute("""
            INSERT INTO admins (user_id, created_at)
            VALUES (%s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id) DO NOTHING
        """, (user_id,))
        
        cursor.close()
        conn.close()
        
        logger.info(f"[SUCCESS] User {user_id} added as admin!")
        logger.info("")
        return True
        
    except Exception as e:
        logger.error(f"Error adding admin: {e}")
        import traceback
        traceback.print_exc()
        cursor.close()
        conn.close()
        return False

if __name__ == "__main__":
    print("")
    print("=" * 60)
    print("SUPABASE ADMIN MANAGER")
    print("=" * 60)
    print("")
    
    # First, check current admins
    admins = check_admins()
    
    print("")
    print("=" * 60)
    
    # Ask if user wants to add an admin
    if len(sys.argv) > 1:
        try:
            user_id = int(sys.argv[1])
            print(f"")
            print(f"Adding user {user_id} as admin...")
            print("")
            success = add_admin(user_id)
            if success:
                print("")
                print("Verifying admin was added...")
                print("")
                check_admins()
        except ValueError:
            print(f"Invalid user ID: {sys.argv[1]}")
            print("Usage: python check_and_add_admin.py [user_id]")
    else:
        print("")
        print("To add an admin, run:")
        print("  python check_and_add_admin.py [your_telegram_user_id]")
        print("")
        print("To find your Telegram user ID:")
        print("  1. Send /myid to the bot")
        print("  2. Or use @userinfobot on Telegram")
        print("")
