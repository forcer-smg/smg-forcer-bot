#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Restore Supabase Database Schema
Recreates all required tables with correct structure
"""

import os
import sys
import logging
from datetime import datetime

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

def restore_database_schema():
    """Restore complete database schema"""
    logger.info("=" * 60)
    logger.info("RESTORING SUPABASE DATABASE SCHEMA")
    logger.info("=" * 60)
    logger.info("")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Users table
        logger.info("[1/6] Creating users table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                referral_code TEXT UNIQUE,
                referred_by BIGINT,
                total_referrals INTEGER DEFAULT 0,
                referral_earnings REAL DEFAULT 0.0,
                is_blocked INTEGER DEFAULT 0,
                user_mode TEXT DEFAULT 'auto',
                FOREIGN KEY (referred_by) REFERENCES users(user_id)
            )
        """)
        
        # Add columns if they don't exist
        for column, col_type, default in [
            ('is_blocked', 'INTEGER', '0'),
            ('user_mode', 'TEXT', "'auto'")
        ]:
            try:
                cursor.execute(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='users' AND column_name='{column}'
                """)
                if not cursor.fetchone():
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {column} {col_type} DEFAULT {default}")
                    logger.info(f"      Added {column} column")
            except Exception as e:
                logger.debug(f"Column {column} check: {e}")
        
        logger.info("      ✅ users table ready")
        
        # 2. Subscriptions table
        logger.info("[2/6] Creating subscriptions table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                plan_type TEXT,
                status TEXT,
                requests_used INTEGER DEFAULT 0,
                requests_limit INTEGER,
                start_date TIMESTAMP,
                end_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        logger.info("      ✅ subscriptions table ready")
        
        # 3. Payments table
        logger.info("[3/6] Creating payments table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                plan_type TEXT,
                amount REAL,
                currency TEXT DEFAULT 'USD',
                payment_id TEXT UNIQUE,
                oxapay_invoice_id TEXT,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        logger.info("      ✅ payments table ready")
        
        # 4. Daily usage table
        logger.info("[4/6] Creating daily_usage table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_usage (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                date DATE,
                message_count INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, date)
            )
        """)
        logger.info("      ✅ daily_usage table ready")
        
        # 5. Referral transactions table
        logger.info("[5/6] Creating referral_transactions table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS referral_transactions (
                id SERIAL PRIMARY KEY,
                referrer_id BIGINT,
                referred_id BIGINT,
                amount REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                FOREIGN KEY (referred_id) REFERENCES users(user_id)
            )
        """)
        logger.info("      ✅ referral_transactions table ready")
        
        # 6. Admins table
        logger.info("[6/6] Creating admins table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id BIGINT PRIMARY KEY,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        logger.info("      ✅ admins table ready")
        
        # Create indexes for performance
        logger.info("")
        logger.info("[+] Creating indexes...")
        indexes = [
            ("idx_subscriptions_user_id", "subscriptions", "user_id"),
            ("idx_payments_user_id", "payments", "user_id"),
            ("idx_daily_usage_user_id", "daily_usage", "user_id"),
            ("idx_daily_usage_date", "daily_usage", "date"),
            ("idx_referral_transactions_referrer", "referral_transactions", "referrer_id"),
            ("idx_users_referral_code", "users", "referral_code"),
        ]
        
        for idx_name, table, column in indexes:
            try:
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS {idx_name} 
                    ON {table}({column})
                """)
                logger.info(f"      ✅ {idx_name}")
            except Exception as e:
                logger.warning(f"      ⚠️  {idx_name}: {e}")
        
        # Verify tables
        logger.info("")
        logger.info("[+] Verifying tables...")
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        tables = cursor.fetchall()
        logger.info(f"      Found {len(tables)} tables:")
        for table in tables:
            logger.info(f"      - {table[0]}")
        
        cursor.close()
        conn.close()
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ DATABASE SCHEMA RESTORED SUCCESSFULLY!")
        logger.info("=" * 60)
        logger.info("")
        logger.info("All required tables have been created/verified:")
        logger.info("  ✅ users")
        logger.info("  ✅ subscriptions")
        logger.info("  ✅ payments")
        logger.info("  ✅ daily_usage")
        logger.info("  ✅ referral_transactions")
        logger.info("  ✅ admins")
        logger.info("")
        logger.info("Note: This script preserves existing data.")
        logger.info("It only creates tables/columns if they don't exist.")
        logger.info("")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error restoring database: {e}")
        import traceback
        traceback.print_exc()
        cursor.close()
        conn.close()
        return False

if __name__ == "__main__":
    print("")
    print("⚠️  WARNING: This will modify your Supabase database!")
    print("   It will create tables if they don't exist.")
    print("   Existing data will be preserved.")
    print("")
    response = input("Continue? (yes/no): ").strip().lower()
    
    if response != 'yes':
        print("❌ Cancelled")
        sys.exit(0)
    
    success = restore_database_schema()
    sys.exit(0 if success else 1)
