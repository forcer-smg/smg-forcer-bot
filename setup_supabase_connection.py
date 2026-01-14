#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick setup for Supabase connection
"""

import os
from dotenv import load_dotenv

# Your Supabase details
PROJECT_REF = "yllsquazrwgbndgonxti"
PASSWORD = "Timewilltell420!"

# Build connection string
CONNECTION_STRING = f"postgresql://postgres:{PASSWORD}@db.{PROJECT_REF}.supabase.co:5432/postgres"

print("="*70)
print("  Setting Up Supabase Connection")
print("="*70)
print(f"\nProject Reference: {PROJECT_REF}")
print(f"\nConnection String:")
print(f"  {CONNECTION_STRING}")

# Save to .hacx file
env_file = '.hacx'
if not os.path.exists(env_file):
    env_file = '.env'

# Read existing content
content = ""
if os.path.exists(env_file):
    with open(env_file, 'r') as f:
        content = f.read()

# Update or add DATABASE_URL
if 'DATABASE_URL=' in content:
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if line.startswith('DATABASE_URL='):
            lines[i] = f'DATABASE_URL={CONNECTION_STRING}'
            break
    content = '\n'.join(lines)
else:
    content += f'\nDATABASE_URL={CONNECTION_STRING}\n'

# Write back
with open(env_file, 'w') as f:
    f.write(content)

print(f"\n✅ Connection string saved to {env_file}")

# Test connection
print("\n🔍 Testing connection...")
try:
    import psycopg2
    conn = psycopg2.connect(CONNECTION_STRING)
    conn.close()
    print("✅ Connection successful!")
    print("\n✅ Supabase is ready to use!")
except ImportError:
    print("⚠️  psycopg2 not installed. Install with: pip install psycopg2-binary")
    print("   But connection string is saved!")
except Exception as e:
    print(f"❌ Connection test failed: {e}")
    print("   Connection string is saved, but please verify:")
    print("   - Password is correct")
    print("   - Project reference is correct")
    print("   - Supabase project is active")

print("\n" + "="*70)
print("  Next Steps:")
print("="*70)
print("1. Test connection: python -c \"import os; from dotenv import load_dotenv; load_dotenv(); import psycopg2; conn = psycopg2.connect(os.getenv('DATABASE_URL')); print('OK'); conn.close()\"")
print("2. Migrate data: python migrate_to_postgres.py")
print("3. Test bot: python telegram_bot.py")
print("="*70 + "\n")

