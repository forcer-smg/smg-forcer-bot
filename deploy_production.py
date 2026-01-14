#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Production Deployment Helper Script
Guides you through the complete deployment process
"""

import os
import sys
import subprocess
import json

def print_step(step_num, title):
    print("\n" + "="*70)
    print(f"  STEP {step_num}: {title}")
    print("="*70)

def check_requirements():
    """Check if required packages are installed"""
    print_step(1, "Checking Requirements")
    
    required = {
        'python-telegram-bot': 'python-telegram-bot',
        'python-dotenv': 'python-dotenv',
        'psycopg2': 'psycopg2-binary'
    }
    
    missing = []
    for package, install_name in required.items():
        try:
            __import__(package.replace('-', '_'))
            print(f"✅ {package} installed")
        except ImportError:
            print(f"❌ {package} NOT installed")
            missing.append(install_name)
    
    if missing:
        print(f"\n⚠️  Missing packages: {', '.join(missing)}")
        install = input(f"\nInstall missing packages? (y/n): ")
        if install.lower() == 'y':
            print(f"\nInstalling: pip install {' '.join(missing)}")
            subprocess.run([sys.executable, '-m', 'pip', 'install'] + missing)
            print("✅ Installation complete!")
        else:
            print("⚠️  Please install missing packages before continuing")
            return False
    
    return True

def check_current_setup():
    """Check current bot setup"""
    print_step(2, "Checking Current Setup")
    
    # Check if SQLite database exists
    if os.path.exists('smg_forcer.db'):
        print("✅ SQLite database found: smg_forcer.db")
        
        # Get user count
        try:
            import sqlite3
            conn = sqlite3.connect('smg_forcer.db')
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            conn.close()
            print(f"   📊 Current users: {user_count}")
        except:
            print("   ⚠️  Could not read database")
    else:
        print("⚠️  No SQLite database found (this is OK if starting fresh)")
    
    # Check environment file
    env_files = ['.hacx', '.env']
    env_found = False
    for env_file in env_files:
        if os.path.exists(env_file):
            print(f"✅ Environment file found: {env_file}")
            env_found = True
            break
    
    if not env_found:
        print("⚠️  No environment file found (.hacx or .env)")
    
    # Check bot token
    from dotenv import load_dotenv
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if token:
        masked = token[:10] + "..." + token[-5:] if len(token) > 15 else "***"
        print(f"✅ Bot token configured: {masked}")
    else:
        print("❌ Bot token not found in environment")
        return False
    
    return True

def setup_supabase():
    """Guide user through Supabase setup"""
    print_step(3, "Setting Up Supabase Database")
    
    print("\n📋 Supabase Setup Instructions:")
    print("1. Go to https://supabase.com and create a free account")
    print("2. Click 'New Project'")
    print("3. Fill in project details:")
    print("   - Name: smg-forcer-bot (or any name)")
    print("   - Database Password: (choose a strong password - SAVE IT!)")
    print("   - Region: Choose closest to you")
    print("4. Wait for project to be created (~2 minutes)")
    print("5. Go to Settings → Database")
    print("6. Find 'Connection string' → 'URI'")
    print("7. Copy the connection string")
    print("\n   Format: postgresql://postgres:[PASSWORD]@db.xxx.supabase.co:5432/postgres")
    
    input("\nPress Enter when you have your Supabase connection string...")
    
    db_url = input("\nPaste your Supabase DATABASE_URL: ").strip()
    
    if not db_url or not db_url.startswith('postgresql://'):
        print("❌ Invalid DATABASE_URL format")
        return None
    
    # Save to .env file
    env_file = '.env'
    if os.path.exists('.hacx'):
        env_file = '.hacx'
    
    # Read existing file
    env_content = ""
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            env_content = f.read()
    
    # Add or update DATABASE_URL
    if 'DATABASE_URL=' in env_content:
        lines = env_content.split('\n')
        for i, line in enumerate(lines):
            if line.startswith('DATABASE_URL='):
                lines[i] = f'DATABASE_URL={db_url}'
                break
        env_content = '\n'.join(lines)
    else:
        env_content += f'\nDATABASE_URL={db_url}\n'
    
    with open(env_file, 'w') as f:
        f.write(env_content)
    
    print(f"✅ DATABASE_URL saved to {env_file}")
    
    # Test connection
    print("\n🔍 Testing database connection...")
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        conn.close()
        print("✅ Database connection successful!")
        return db_url
    except ImportError:
        print("⚠️  psycopg2 not installed. Install with: pip install psycopg2-binary")
        return None
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("   Please check your DATABASE_URL and try again")
        return None

def migrate_database():
    """Migrate from SQLite to PostgreSQL"""
    print_step(4, "Migrating Database")
    
    if not os.path.exists('smg_forcer.db'):
        print("⚠️  No SQLite database to migrate. Skipping...")
        return True
    
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL not set. Run Supabase setup first.")
        return False
    
    print("\n⚠️  This will copy all data from SQLite to PostgreSQL")
    print("   Your SQLite database will remain unchanged (backup)")
    
    confirm = input("\nProceed with migration? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Migration cancelled.")
        return False
    
    print("\n🔄 Starting migration...")
    
    try:
        # Import and run migration
        from migrate_to_postgres import migrate_sqlite_to_postgres
        success = migrate_sqlite_to_postgres('smg_forcer.db', db_url)
        return success
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def update_bot_code():
    """Update bot code to use hybrid database"""
    print_step(5, "Updating Bot Code")
    
    # Check if telegram_bot.py uses database.py
    try:
        with open('telegram_bot.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'from database import Database' in content:
            print("📝 Updating database import...")
            # Replace with hybrid version
            content = content.replace(
                'from database import Database',
                'from database_hybrid import Database  # Auto-detects SQLite or PostgreSQL'
            )
            
            with open('telegram_bot.py', 'w', encoding='utf-8') as f:
                f.write(content)
            print("✅ Bot code updated to use hybrid database")
        else:
            print("✅ Bot code already updated or using different import")
    except Exception as e:
        print(f"⚠️  Could not update bot code: {e}")
        print("   You may need to manually update the import in telegram_bot.py")

def create_production_config():
    """Create production configuration files"""
    print_step(6, "Creating Production Configuration")
    
    # Create .env.production template
    env_prod = """# Production Environment Variables
# Copy this to your production server

TELEGRAM_BOT_TOKEN=your_bot_token_here
DATABASE_URL=your_supabase_url_here

# Optional: Production mode
PRODUCTION_MODE=true
"""
    
    with open('.env.production.example', 'w') as f:
        f.write(env_prod)
    print("✅ Created .env.production.example")
    
    # Create deployment checklist
    checklist = """# Production Deployment Checklist

## Pre-Deployment
- [ ] All tests passing
- [ ] Database migrated to Supabase
- [ ] Environment variables configured
- [ ] Bot code updated

## Deployment
- [ ] VPS/server ready
- [ ] Dependencies installed
- [ ] Bot running with PM2/systemd
- [ ] Monitoring set up

## Post-Deployment
- [ ] Bot responds to /start
- [ ] Admin dashboard works
- [ ] Payments working
- [ ] Logs checked
- [ ] Backups configured
"""
    
    with open('DEPLOYMENT_CHECKLIST.md', 'w') as f:
        f.write(checklist)
    print("✅ Created DEPLOYMENT_CHECKLIST.md")

def main():
    print("\n" + "="*70)
    print("  SMG-Forcer Telegram Bot - Production Deployment")
    print("="*70)
    print("\nThis script will guide you through the complete deployment process.")
    print("Make sure you have:")
    print("  - Telegram Bot Token")
    print("  - Supabase account (or create one during setup)")
    print("  - VPS/server ready (or use Railway/Render)")
    
    input("\nPress Enter to continue...")
    
    # Step 1: Check requirements
    if not check_requirements():
        print("\n❌ Please install missing requirements and try again")
        return
    
    # Step 2: Check current setup
    if not check_current_setup():
        print("\n⚠️  Some setup issues found. Please fix them and try again.")
        return
    
    # Step 3: Setup Supabase
    db_url = setup_supabase()
    if not db_url:
        print("\n❌ Supabase setup failed. Please try again.")
        return
    
    # Step 4: Migrate database
    if not migrate_database():
        print("\n⚠️  Migration failed or cancelled. You can run it later with:")
        print("   python migrate_to_postgres.py")
    
    # Step 5: Update bot code
    update_bot_code()
    
    # Step 6: Create production config
    create_production_config()
    
    # Summary
    print("\n" + "="*70)
    print("  ✅ DEPLOYMENT SETUP COMPLETE!")
    print("="*70)
    print("\n📋 Next Steps:")
    print("1. Review DEPLOYMENT_STEPS.md for server setup")
    print("2. Deploy to VPS or Railway")
    print("3. Use PM2 or systemd to keep bot running")
    print("4. Monitor logs and test bot")
    print("\n📚 Documentation:")
    print("  - QUICK_DEPLOY.md - Fast deployment options")
    print("  - DEPLOYMENT_STEPS.md - Detailed steps")
    print("  - PRODUCTION_DEPLOYMENT.md - Full comparison")
    print("\n" + "="*70 + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Deployment cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

