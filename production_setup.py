#!/usr/bin/env python3
"""
Production Setup and Verification Script
Checks all requirements before deployment
"""

import os
import sys
from pathlib import Path

print("\n" + "="*60)
print("PRODUCTION SETUP VERIFICATION")
print("="*60 + "\n")

errors = []
warnings = []
checks_passed = 0

# Check 1: Environment File
print("1. Checking Environment File (.hacx)...")
env_file = Path(".hacx")
if env_file.exists():
    print("   ✅ .hacx file exists")
    checks_passed += 1
    
    # Check required variables
    from dotenv import load_dotenv
    load_dotenv(env_file)
    
    required_vars = {
        "TELEGRAM_BOT_TOKEN": "Telegram Bot Token",
        "SMG-Forcer-API": "DeepSeek API Key (Primary)",
    }
    
    optional_vars = {
        "OXAPAY_API_KEY": "OxaPay API Key",
        "OXAPAY_MERCHANT_ID": "OxaPay Merchant ID",
        "DEEPSEEK_API_KEY_2": "DeepSeek API Key (Backup 2)",
        "DEEPSEEK_API_KEY_3": "DeepSeek API Key (Backup 3)",
    }
    
    print("\n   Required Variables:")
    for var, desc in required_vars.items():
        value = os.getenv(var)
        if value:
            masked = value[:10] + "..." if len(value) > 10 else value
            print(f"      ✅ {var}: {masked}")
            checks_passed += 1
        else:
            print(f"      ❌ {var}: NOT SET")
            errors.append(f"Missing required variable: {var} ({desc})")
    
    print("\n   Optional Variables:")
    for var, desc in optional_vars.items():
        value = os.getenv(var)
        if value:
            masked = value[:10] + "..." if len(value) > 10 else value
            print(f"      ✅ {var}: {masked}")
        else:
            print(f"      ⚠️  {var}: Not set ({desc})")
            warnings.append(f"Optional variable not set: {var}")
else:
    print("   ❌ .hacx file NOT FOUND")
    errors.append(".hacx file not found - create it with required environment variables")

# Check 2: Python Dependencies
print("\n2. Checking Python Dependencies...")
required_packages = [
    ("telegram", "python-telegram-bot"),
    ("dotenv", "python-dotenv"),
    ("openai", "openai"),
    ("rich", "rich"),
]

for import_name, pip_name in required_packages:
    try:
        __import__(import_name)
        print(f"   ✅ {pip_name}")
        checks_passed += 1
    except ImportError:
        print(f"   ❌ {pip_name} - NOT INSTALLED")
        errors.append(f"Missing package: {pip_name}")

# Check 3: Database
print("\n3. Checking Database...")
try:
    from database import Database
    db = Database()
    conn = db.get_connection()
    conn.close()
    print("   ✅ Database connection works")
    checks_passed += 1
    
    # Check if database file exists
    db_file = Path("smg_forcer.db")
    if db_file.exists():
        size = db_file.stat().st_size / 1024  # KB
        print(f"   ✅ Database file exists ({size:.2f} KB)")
    else:
        print("   ⚠️  Database file will be created on first run")
        warnings.append("Database file doesn't exist yet (will be created)")
except Exception as e:
    print(f"   ❌ Database error: {e}")
    errors.append(f"Database error: {e}")

# Check 4: Core Files
print("\n4. Checking Core Files...")
required_files = [
    "telegram_bot.py",
    "database.py",
    "HacxGPT.py",
    "oxapay.py",
]

for file in required_files:
    if Path(file).exists():
        print(f"   ✅ {file}")
        checks_passed += 1
    else:
        print(f"   ❌ {file} - NOT FOUND")
        errors.append(f"Missing file: {file}")

# Check 5: Code Compilation
print("\n5. Checking Code Compilation...")
try:
    import py_compile
    py_compile.compile("telegram_bot.py", doraise=True)
    print("   ✅ telegram_bot.py compiles")
    checks_passed += 1
    
    py_compile.compile("database.py", doraise=True)
    print("   ✅ database.py compiles")
    checks_passed += 1
except py_compile.PyCompileError as e:
    print(f"   ❌ Compilation error: {e}")
    errors.append(f"Code compilation error: {e}")

# Check 6: Admin Setup
print("\n6. Checking Admin Setup...")
admins_file = Path("admins.txt")
if admins_file.exists():
    with open(admins_file, 'r') as f:
        admin_lines = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
    if admin_lines:
        print(f"   ✅ admins.txt exists with {len(admin_lines)} admin(s)")
        checks_passed += 1
    else:
        print("   ⚠️  admins.txt exists but is empty")
        warnings.append("No admins configured in admins.txt")
else:
    print("   ⚠️  admins.txt not found (use add_admin.py or create admins.txt)")
    warnings.append("admins.txt not found - use add_admin.py to add admins")

# Summary
print("\n" + "="*60)
print("VERIFICATION SUMMARY")
print("="*60)
print(f"\n✅ Checks Passed: {checks_passed}")
print(f"⚠️  Warnings: {len(warnings)}")
print(f"❌ Errors: {len(errors)}")

if warnings:
    print("\n⚠️  WARNINGS:")
    for i, warning in enumerate(warnings, 1):
        print(f"   {i}. {warning}")

if errors:
    print("\n❌ ERRORS (MUST FIX BEFORE PRODUCTION):")
    for i, error in enumerate(errors, 1):
        print(f"   {i}. {error}")
    print("\n❌ NOT READY FOR PRODUCTION - Fix errors above")
    sys.exit(1)
else:
    print("\n✅ READY FOR PRODUCTION!")
    if warnings:
        print("⚠️  Review warnings above for optimal setup")
    print("="*60 + "\n")

