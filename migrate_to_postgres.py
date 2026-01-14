#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration script: SQLite → PostgreSQL
Migrates all data from SQLite database to PostgreSQL/Supabase
"""

import sqlite3
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    print("❌ psycopg2 not installed. Install with: pip install psycopg2-binary")
    sys.exit(1)


def migrate_sqlite_to_postgres(sqlite_db: str, postgres_url: str):
    """
    Migrate data from SQLite to PostgreSQL
    
    Args:
        sqlite_db: Path to SQLite database file
        postgres_url: PostgreSQL connection string
    """
    print("="*70)
    print("  SQLite → PostgreSQL Migration")
    print("="*70)
    
    if not os.path.exists(sqlite_db):
        print(f"❌ SQLite database not found: {sqlite_db}")
        return False
    
    # Connect to SQLite
    print(f"\n[1] Connecting to SQLite: {sqlite_db}")
    sqlite_conn = sqlite3.connect(sqlite_db)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()
    
    # Connect to PostgreSQL
    print(f"[2] Connecting to PostgreSQL...")
    try:
        pg_conn = psycopg2.connect(postgres_url)
        pg_cursor = pg_conn.cursor()
        print("✅ Connected to PostgreSQL")
    except Exception as e:
        print(f"❌ Failed to connect to PostgreSQL: {e}")
        return False
    
    try:
        # Migrate users
        print("\n[3] Migrating users...")
        sqlite_cursor.execute("SELECT * FROM users")
        users = sqlite_cursor.fetchall()
        
        if users:
            user_data = []
            for row in users:
                user_data.append((
                    row['user_id'],
                    row['username'],
                    row['first_name'],
                    row['created_at'],
                    row['referral_code'],
                    row['referred_by'],
                    row['total_referrals'] if 'total_referrals' in row.keys() else 0,
                    row['referral_earnings'] if 'referral_earnings' in row.keys() else 0.0,
                    row['is_blocked'] if 'is_blocked' in row.keys() else 0
                ))
            
            execute_values(
                pg_cursor,
                """
                INSERT INTO users (user_id, username, first_name, created_at, referral_code, 
                                 referred_by, total_referrals, referral_earnings, is_blocked)
                VALUES %s
                ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    referral_code = EXCLUDED.referral_code,
                    referred_by = EXCLUDED.referred_by,
                    total_referrals = EXCLUDED.total_referrals,
                    referral_earnings = EXCLUDED.referral_earnings,
                    is_blocked = EXCLUDED.is_blocked
                """,
                user_data
            )
            print(f"✅ Migrated {len(users)} users")
        else:
            print("⚠️  No users to migrate")
        
        # Migrate subscriptions
        print("\n[4] Migrating subscriptions...")
        sqlite_cursor.execute("SELECT * FROM subscriptions")
        subs = sqlite_cursor.fetchall()
        
        if subs:
            sub_data = []
            for row in subs:
                sub_data.append((
                    row['user_id'],
                    row['plan_type'],
                    row['status'],
                    row['requests_used'] if 'requests_used' in row.keys() else 0,
                    row['requests_limit'],
                    row['start_date'],
                    row['end_date'],
                    row['created_at']
                ))
            
            execute_values(
                pg_cursor,
                """
                INSERT INTO subscriptions (user_id, plan_type, status, requests_used, 
                                         requests_limit, start_date, end_date, created_at)
                VALUES %s
                """,
                sub_data
            )
            print(f"✅ Migrated {len(subs)} subscriptions")
        
        # Migrate payments
        print("\n[5] Migrating payments...")
        sqlite_cursor.execute("SELECT * FROM payments")
        payments = sqlite_cursor.fetchall()
        
        if payments:
            payment_data = []
            for row in payments:
                payment_data.append((
                    row['user_id'],
                    row['plan_type'],
                    row['amount'],
                    row['currency'] if 'currency' in row.keys() else 'USD',
                    row['payment_id'],
                    row['oxapay_invoice_id'],
                    row['status'],
                    row['created_at'],
                    row['completed_at']
                ))
            
            execute_values(
                pg_cursor,
                """
                INSERT INTO payments (user_id, plan_type, amount, currency, payment_id,
                                    oxapay_invoice_id, status, created_at, completed_at)
                VALUES %s
                ON CONFLICT (payment_id) DO NOTHING
                """,
                payment_data
            )
            print(f"✅ Migrated {len(payments)} payments")
        
        # Migrate daily_usage
        print("\n[6] Migrating daily usage...")
        sqlite_cursor.execute("SELECT * FROM daily_usage")
        usage = sqlite_cursor.fetchall()
        
        if usage:
            usage_data = []
            for row in usage:
                usage_data.append((
                    row['user_id'],
                    row['date'],
                    row['message_count'] if 'message_count' in row.keys() else 0
                ))
            
            execute_values(
                pg_cursor,
                """
                INSERT INTO daily_usage (user_id, date, message_count)
                VALUES %s
                ON CONFLICT (user_id, date) DO UPDATE SET
                    message_count = EXCLUDED.message_count
                """,
                usage_data
            )
            print(f"✅ Migrated {len(usage)} daily usage records")
        
        # Migrate admins
        print("\n[7] Migrating admins...")
        sqlite_cursor.execute("SELECT * FROM admins")
        admins = sqlite_cursor.fetchall()
        
        if admins:
            admin_data = [(row['user_id'], row['created_at']) for row in admins]
            
            execute_values(
                pg_cursor,
                """
                INSERT INTO admins (user_id, created_at)
                VALUES %s
                ON CONFLICT (user_id) DO NOTHING
                """,
                admin_data
            )
            print(f"✅ Migrated {len(admins)} admins")
        
        # Commit all changes
        pg_conn.commit()
        
        print("\n" + "="*70)
        print("✅ Migration completed successfully!")
        print("="*70)
        
        return True
        
    except Exception as e:
        pg_conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        sqlite_cursor.close()
        sqlite_conn.close()
        pg_cursor.close()
        pg_conn.close()


if __name__ == "__main__":
    # Load environment variables (.hacx preferred)
    if os.path.exists(".hacx"):
        load_dotenv(".hacx")
    else:
        load_dotenv()

    sqlite_db = "smg_forcer.db"
    postgres_url = os.getenv("DATABASE_URL")
    
    if not postgres_url:
        print("❌ DATABASE_URL environment variable not set")
        print("\nSet it like this:")
        print("  export DATABASE_URL='postgresql://user:password@host:port/database'")
        print("\nOr for Supabase:")
        print("  export DATABASE_URL='postgresql://postgres:password@db.xxx.supabase.co:5432/postgres'")
        sys.exit(1)
    
    print(f"\nSQLite DB: {sqlite_db}")
    print(f"PostgreSQL URL: {postgres_url[:50]}...")
    
    confirm = input("\n⚠️  This will migrate all data. Continue? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Migration cancelled.")
        sys.exit(0)
    
    success = migrate_sqlite_to_postgres(sqlite_db, postgres_url)
    sys.exit(0 if success else 1)

