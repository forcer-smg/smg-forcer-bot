#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Setup Supabase Tables for Settings Sync
Creates required tables in Supabase database
"""

import os
import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Supabase connection details
SUPABASE_HOST = "db.yllsquazrwgbndgonxti.supabase.co"
SUPABASE_PORT = 6543
SUPABASE_DB = "postgres"
SUPABASE_USER = "postgres"
SUPABASE_PASSWORD = "Timewilltell420!"

# Supabase URL for API
SUPABASE_URL = "https://yllsquazrwgbndgonxti.supabase.co"

def create_tables():
    """Create required tables in Supabase"""
    print("=" * 60)
    print("Setting up Supabase Tables for Settings Sync")
    print("=" * 60)
    print()
    
    try:
        # Connect to Supabase PostgreSQL
        print(f"[1/3] Connecting to Supabase database...")
        print(f"      Host: {SUPABASE_HOST}")
        print(f"      Port: {SUPABASE_PORT}")
        print(f"      Database: {SUPABASE_DB}")
        
        conn = psycopg2.connect(
            host=SUPABASE_HOST,
            port=SUPABASE_PORT,
            database=SUPABASE_DB,
            user=SUPABASE_USER,
            password=SUPABASE_PASSWORD
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        print("      ✅ Connected successfully!")
        print()
        
        # Create user_settings table
        print("[2/3] Creating user_settings table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id BIGINT PRIMARY KEY,
                settings JSONB NOT NULL DEFAULT '{}',
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)
        print("      ✅ user_settings table created/verified")
        
        # Create desktop_registrations table
        print("[3/3] Creating desktop_registrations table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS desktop_registrations (
                user_id BIGINT NOT NULL,
                device_id TEXT NOT NULL,
                app_version TEXT,
                registered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                PRIMARY KEY (user_id, device_id)
            );
        """)
        print("      ✅ desktop_registrations table created/verified")
        
        # Create indexes for better performance
        print()
        print("[+] Creating indexes...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_settings_user_id 
            ON user_settings(user_id);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_desktop_registrations_user_id 
            ON desktop_registrations(user_id);
        """)
        print("      ✅ Indexes created/verified")
        
        # Verify tables exist
        print()
        print("[+] Verifying tables...")
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('user_settings', 'desktop_registrations');
        """)
        tables = cursor.fetchall()
        print(f"      Found {len(tables)} tables:")
        for table in tables:
            print(f"      - {table[0]}")
        
        cursor.close()
        conn.close()
        
        print()
        print("=" * 60)
        print("✅ SUPABASE TABLES SETUP COMPLETE!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Get your Supabase anon key from:")
        print("   https://supabase.com/dashboard/project/yllsquazrwgbndgonxti/settings/api")
        print()
        print("2. Add to Railway Variables:")
        print(f"   SUPABASE_URL={SUPABASE_URL}")
        print("   SUPABASE_KEY=your_anon_key_here")
        print()
        print("3. Railway will auto-redeploy")
        print()
        
        return True
        
    except psycopg2.OperationalError as e:
        print(f"❌ Connection error: {e}")
        print()
        print("Check:")
        print("- Database host and port are correct")
        print("- Password is correct")
        print("- Supabase project is active (not paused)")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = create_tables()
    sys.exit(0 if success else 1)

