#!/usr/bin/env python3
"""
Diagnostic script to check database connection configuration
Helps identify why Supabase data is not being used in deployment
"""

import os
import sys

# Try to load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not installed, continue with system environment variables only
    pass

def check_environment():
    """Check environment variables and database connection"""
    print("=" * 60)
    print("DATABASE CONNECTION DIAGNOSTIC")
    print("=" * 60)
    print()
    
    # Check DATABASE_URL
    database_url = os.getenv("DATABASE_URL")
    print("1. DATABASE_URL (PostgreSQL Connection String):")
    if database_url:
        if database_url.startswith("postgresql://"):
            print(f"   [OK] Found: {database_url[:50]}...")
            print("   [OK] Format is correct (postgresql://)")
            
            # Extract host info
            try:
                if "@" in database_url:
                    host_part = database_url.split("@")[1].split("/")[0]
                    print(f"   Host: {host_part}")
            except:
                pass
        else:
            print(f"   [WARNING] Found but wrong format: {database_url[:50]}...")
            print("   [ERROR] Should start with 'postgresql://'")
    else:
        print("   [ERROR] NOT SET - This is the problem!")
        print("   [INFO] The code checks DATABASE_URL to use PostgreSQL/Supabase")
        print("   [INFO] Without it, the bot falls back to SQLite (local database)")
    
    print()
    
    # Check SUPABASE_URL
    supabase_url = os.getenv("SUPABASE_URL")
    print("2. SUPABASE_URL (Supabase API URL):")
    if supabase_url:
        print(f"   [OK] Found: {supabase_url}")
        print("   [INFO] This is for API access, not database connection")
    else:
        print("   [WARNING] Not set (optional for API features)")
    
    print()
    
    # Check SUPABASE_KEY
    supabase_key = os.getenv("SUPABASE_KEY")
    print("3. SUPABASE_KEY (Supabase API Key):")
    if supabase_key:
        print(f"   [OK] Found: {supabase_key[:20]}...")
        print("   [INFO] This is for API access, not database connection")
    else:
        print("   [WARNING] Not set (optional for API features)")
    
    print()
    
    # Check which database will be used
    print("4. Database Selection Logic:")
    print("   The code uses 'database_hybrid.py' which checks:")
    print("   - If DATABASE_URL exists and starts with 'postgresql://' -> Use PostgreSQL/Supabase")
    print("   - Otherwise -> Use SQLite (local database)")
    print()
    
    if database_url and database_url.startswith("postgresql://"):
        print("   [OK] RESULT: Will use PostgreSQL/Supabase database")
        print("   [OK] Your existing Supabase data will be used")
    else:
        print("   [ERROR] RESULT: Will use SQLite (local database)")
        print("   [ERROR] Your existing Supabase data will NOT be used")
        print()
        print("   [SOLUTION]")
        print("   1. Get your Supabase PostgreSQL connection string:")
        print("      - Go to Supabase Dashboard -> Settings -> Database")
        print("      - Find 'Connection string' -> 'URI'")
        print("      - Format: postgresql://postgres:[PASSWORD]@db.xxx.supabase.co:5432/postgres")
        print()
        print("   2. Add to Railway as environment variable:")
        print("      - Name: DATABASE_URL")
        print("      - Value: postgresql://postgres:[PASSWORD]@db.xxx.supabase.co:5432/postgres")
        print()
        print("   3. Railway will auto-redeploy after adding the variable")
    
    print()
    print("=" * 60)
    
    # Try to test connection if DATABASE_URL is set
    if database_url and database_url.startswith("postgresql://"):
        print()
        print("Testing PostgreSQL connection...")
        try:
            import psycopg2
            conn = psycopg2.connect(database_url)
            cursor = conn.cursor()
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]
            print(f"   [OK] Connection successful!")
            print(f"   Database: {version[:50]}...")
            cursor.close()
            conn.close()
        except ImportError:
            print("   [WARNING] psycopg2 not installed (pip install psycopg2-binary)")
        except Exception as e:
            print(f"   [ERROR] Connection failed: {e}")
            print("   [INFO] Check your DATABASE_URL format and credentials")
    
    print()
    print("=" * 60)

if __name__ == "__main__":
    check_environment()
