#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Connect to Supabase and manage admins
Uses direct PostgreSQL connection string
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

# Supabase connection string template
SUPABASE_URL_TEMPLATE = "postgresql://postgres:{password}@db.yllsquazrwgbndgonxti.supabase.co:5432/postgres"

def get_connection(password: str = None, connection_string: str = None):
    """Get Supabase PostgreSQL connection"""
    if connection_string:
        # Use provided connection string directly
        database_url = connection_string
    elif password:
        # Replace password in template
        database_url = SUPABASE_URL_TEMPLATE.format(password=password)
    else:
        # Try to get from environment variable
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL not set and no password/connection string provided!")
            logger.info("Usage options:")
            logger.info("  1. python connect_supabase_admin.py [password] [user_id]")
            logger.info("  2. python connect_supabase_admin.py [full_connection_string] [user_id]")
            logger.info("  3. Set DATABASE_URL environment variable")
            sys.exit(1)
    
    try:
        conn = psycopg2.connect(database_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)

def check_admins(conn):
    """Check all admins in the database"""
    logger.info("=" * 60)
    logger.info("CHECKING ADMINS IN SUPABASE")
    logger.info("=" * 60)
    logger.info("")
    
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
            SELECT a.user_id, u.username, u.first_name, u.created_at, a.created_at as admin_since
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
                user_id, username, first_name, user_created, admin_since = admin
                logger.info(f"  - User ID: {user_id}")
                logger.info(f"    Username: @{username or 'N/A'}")
                logger.info(f"    Name: {first_name or 'N/A'}")
                logger.info(f"    User Created: {user_created}")
                logger.info(f"    Admin Since: {admin_since}")
                logger.info("")
        
        return admins
        
    except Exception as e:
        logger.error(f"Error checking admins: {e}")
        import traceback
        traceback.print_exc()
        return []

def add_admin(conn, user_id: int):
    """Add a user as admin"""
    logger.info("=" * 60)
    logger.info(f"ADDING USER {user_id} AS ADMIN")
    logger.info("=" * 60)
    logger.info("")
    
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
        
        logger.info(f"[SUCCESS] User {user_id} added as admin!")
        logger.info("")
        return True
        
    except Exception as e:
        logger.error(f"Error adding admin: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_user_admin_status(conn, user_id: int):
    """Check if a specific user is an admin"""
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT 1 FROM admins WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        return result is not None
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False

if __name__ == "__main__":
    print("")
    print("=" * 60)
    print("SUPABASE ADMIN MANAGER")
    print("=" * 60)
    print("")
    
    # Get connection string/password and user_id from command line
    connection_string = None
    password = None
    user_id_to_add = None
    
    if len(sys.argv) > 1:
        arg1 = sys.argv[1]
        # Check if it's a full connection string (starts with postgresql://)
        if arg1.startswith("postgresql://"):
            connection_string = arg1
        else:
            password = arg1
    
    if len(sys.argv) > 2:
        try:
            user_id_to_add = int(sys.argv[2])
        except ValueError:
            logger.error(f"Invalid user ID: {sys.argv[2]}")
            sys.exit(1)
    
    # Connect to database
    logger.info("Connecting to Supabase...")
    conn = get_connection(password=password, connection_string=connection_string)
    logger.info("Connected successfully!")
    logger.info("")
    
    # Check current admins
    admins = check_admins(conn)
    
    # Check specific user if provided
    if user_id_to_add:
        logger.info("")
        logger.info("=" * 60)
        is_admin = check_user_admin_status(conn, user_id_to_add)
        if is_admin:
            logger.info(f"User {user_id_to_add} IS an admin")
        else:
            logger.info(f"User {user_id_to_add} is NOT an admin")
            logger.info("")
            logger.info("Adding user as admin...")
            add_admin(conn, user_id_to_add)
            logger.info("")
            logger.info("Verifying...")
            check_admins(conn)
    else:
        logger.info("")
        logger.info("=" * 60)
        logger.info("To add an admin, run:")
        logger.info(f"  python connect_supabase_admin.py [password] [user_id]")
        logger.info("")
        logger.info("Example:")
        logger.info(f"  python connect_supabase_admin.py your_password 5202575644")
        logger.info("")
        logger.info("Or set DATABASE_URL environment variable and run:")
        logger.info(f"  python connect_supabase_admin.py [user_id]")
    
    conn.close()
    logger.info("")
    logger.info("Connection closed.")
