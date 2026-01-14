#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto migration helper.
Runs migrate_to_postgres without prompts and handles errors.
"""

import os
import sys
from dotenv import load_dotenv

try:
    # Import migrate function
    from migrate_to_postgres import migrate_sqlite_to_postgres
except ImportError as exc:
    print(f"❌ Could not import migrate_to_postgres: {exc}")
    sys.exit(1)

def main():
    # Prefer .hacx
    if os.path.exists(".hacx"):
        load_dotenv(".hacx")
    else:
        load_dotenv()

    sqlite_db = "smg_forcer.db"
    postgres_url = os.getenv("DATABASE_URL")

    print("=" * 70)
    print("  Automated SQLite → Supabase Migration")
    print("=" * 70)

    if not postgres_url:
        print("❌ DATABASE_URL not found in environment (.hacx/.env)")
        print("   Please set it before running this script.")
        sys.exit(1)

    if not os.path.exists(sqlite_db):
        print(f"❌ SQLite database not found: {sqlite_db}")
        print("   Make sure you're in the correct project folder.")
        sys.exit(1)

    print(f"\nSQLite DB: {sqlite_db}")
    print(f"PostgreSQL: {postgres_url[:60]}...")
    print("\n⚠️  Starting migration without prompt...")

    success = migrate_sqlite_to_postgres(sqlite_db, postgres_url)

    if success:
        print("\n✅ Migration completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Migration failed. Check logs above for details.")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Migration cancelled by user.")
        sys.exit(1)

