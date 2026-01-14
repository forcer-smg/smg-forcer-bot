#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnose and fix common issues with telegram_bot.py
"""

import sys
import os
import traceback

def print_section(title):
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)

def check_and_fix():
    issues_found = []
    fixes_applied = []
    
    print_section("DIAGNOSING TELEGRAM BOT ISSUES")
    
    # Check 1: Python version
    print("\n[1] Checking Python version...")
    if sys.version_info < (3, 7):
        issues_found.append("Python 3.7+ required")
        print("   ❌ Python version too old")
    else:
        print(f"   ✅ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    
    # Check 2: Required files
    print("\n[2] Checking required files...")
    required_files = [
        "telegram_bot.py",
        "database.py",
        "oxapay.py",
        "HacxGPT.py"
    ]
    for file in required_files:
        if os.path.exists(file):
            print(f"   ✅ {file}")
        else:
            issues_found.append(f"Missing file: {file}")
            print(f"   ❌ {file} not found")
    
    # Check 3: Imports
    print("\n[3] Testing imports...")
    try:
        import telegram
        print("   ✅ python-telegram-bot")
    except ImportError:
        issues_found.append("Missing: python-telegram-bot")
        print("   ❌ python-telegram-bot not installed")
        print("      Fix: pip install python-telegram-bot")
    
    try:
        import dotenv
        print("   ✅ python-dotenv")
    except ImportError:
        issues_found.append("Missing: python-dotenv")
        print("   ❌ python-dotenv not installed")
        print("      Fix: pip install python-dotenv")
    
    # Check 4: Module imports
    print("\n[4] Testing module imports...")
    try:
        from HacxGPT import Config
        print("   ✅ HacxGPT")
    except Exception as e:
        issues_found.append(f"HacxGPT import error: {e}")
        print(f"   ❌ HacxGPT: {e}")
    
    try:
        from database import Database
        print("   ✅ database")
    except Exception as e:
        issues_found.append(f"database import error: {e}")
        print(f"   ❌ database: {e}")
        traceback.print_exc()
    
    try:
        from oxapay import OxaPay
        print("   ✅ oxapay")
    except Exception as e:
        issues_found.append(f"oxapay import error: {e}")
        print(f"   ❌ oxapay: {e}")
        traceback.print_exc()
    
    # Check 5: Environment file
    print("\n[5] Checking environment configuration...")
    try:
        from HacxGPT import Config
        env_file = Config.ENV_FILE
        if os.path.exists(env_file):
            print(f"   ✅ Environment file found: {env_file}")
            
            # Check for bot token
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=env_file)
            token = os.getenv("TELEGRAM_BOT_TOKEN")
            if not token:
                issues_found.append("TELEGRAM_BOT_TOKEN not set")
                print("   ❌ TELEGRAM_BOT_TOKEN not found in environment file")
                print(f"      Please add TELEGRAM_BOT_TOKEN=your_token to {env_file}")
            else:
                print("   ✅ TELEGRAM_BOT_TOKEN is set")
            
            # Check for API keys
            api_keys_found = 0
            for key_name in Config.DEEPSEEK_API_KEYS:
                key = os.getenv(key_name)
                if key:
                    api_keys_found += 1
                    print(f"   ✅ {key_name} is set")
            
            if api_keys_found == 0:
                issues_found.append("No DeepSeek API keys found")
                print("   ❌ No DeepSeek API keys found")
                print(f"      Please add at least one key from: {Config.DEEPSEEK_API_KEYS}")
        else:
            issues_found.append(f"Environment file not found: {env_file}")
            print(f"   ❌ Environment file not found: {env_file}")
    except Exception as e:
        issues_found.append(f"Error checking environment: {e}")
        print(f"   ❌ Error: {e}")
    
    # Check 6: Database
    print("\n[6] Testing database...")
    try:
        from database import Database
        db = Database()
        print("   ✅ Database initialized successfully")
    except Exception as e:
        issues_found.append(f"Database error: {e}")
        print(f"   ❌ Database error: {e}")
        traceback.print_exc()
    
    # Check 7: Syntax check
    print("\n[7] Checking syntax...")
    try:
        compile(open('telegram_bot.py').read(), 'telegram_bot.py', 'exec')
        print("   ✅ No syntax errors")
    except SyntaxError as e:
        issues_found.append(f"Syntax error: {e}")
        print(f"   ❌ Syntax error: {e}")
        print(f"      Line {e.lineno}: {e.text}")
    
    # Summary
    print_section("SUMMARY")
    
    if issues_found:
        print("\n❌ ISSUES FOUND:")
        for i, issue in enumerate(issues_found, 1):
            print(f"   {i}. {issue}")
        
        print("\n💡 COMMON FIXES:")
        print("   1. Install missing packages:")
        print("      pip install python-telegram-bot python-dotenv")
        print("\n   2. Check your .hacx file has:")
        print("      TELEGRAM_BOT_TOKEN=your_bot_token")
        print("      SMG-Forcer-API=your_deepseek_api_key")
        print("\n   3. Make sure all required files are in the same directory")
        print("\n   4. Check file permissions")
    else:
        print("\n✅ NO ISSUES FOUND!")
        print("\nThe bot should be able to run. Try:")
        print("   python telegram_bot.py")
        print("\nOr use the batch file:")
        print("   run_bot.bat")
    
    if fixes_applied:
        print("\n🔧 FIXES APPLIED:")
        for fix in fixes_applied:
            print(f"   - {fix}")
    
    print("\n" + "="*60 + "\n")
    
    return len(issues_found) == 0

if __name__ == "__main__":
    success = check_and_fix()
    sys.exit(0 if success else 1)

