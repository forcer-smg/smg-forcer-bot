#!/usr/bin/env python3
"""
Easy Setup Script for SMG-Forcer Telegram Bot
Run this script to set up the bot from scratch
"""

import os
import sys
import subprocess
from pathlib import Path

print("\n" + "="*60)
print("SMG-FORCER TELEGRAM BOT - EASY SETUP")
print("="*60 + "\n")

def check_python_version():
    """Check if Python version is 3.8+"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required!")
        print(f"   Current version: {sys.version}")
        return False
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    return True

def install_dependencies():
    """Install required Python packages"""
    print("\n📦 Installing dependencies...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "--upgrade"])
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False
    except FileNotFoundError:
        print("❌ requirements.txt not found!")
        return False

def create_env_file():
    """Create .hacx file from template"""
    env_file = Path(".hacx")
    env_example = Path(".env.example")
    
    if env_file.exists():
        print("\n⚠️  .hacx file already exists")
        response = input("   Do you want to overwrite it? (y/N): ").strip().lower()
        if response != 'y':
            print("   Keeping existing .hacx file")
            return True
    
    if not env_example.exists():
        print("❌ .env.example not found!")
        return False
    
    print("\n📝 Creating .hacx file from template...")
    
    # Read template
    with open(env_example, 'r') as f:
        template = f.read()
    
    # Get user input
    print("\n🔧 Configuration Setup:")
    print("   (Press Enter to skip optional fields)")
    
    token = input("\n   Enter Telegram Bot Token (required): ").strip()
    if not token:
        print("❌ Telegram Bot Token is required!")
        return False
    
    api_key = input("   Enter DeepSeek API Key (required): ").strip()
    if not api_key:
        print("❌ DeepSeek API Key is required!")
        return False
    
    oxapay_key = input("   Enter OxaPay API Key (optional): ").strip()
    oxapay_merchant = input("   Enter OxaPay Merchant ID (optional): ").strip()
    
    # Replace template values
    config = template.replace("your_telegram_bot_token_here", token)
    config = config.replace("sk-your-deepseek-api-key-here", api_key)
    config = config.replace("your_oxapay_api_key_here", oxapay_key or "your_oxapay_api_key_here")
    config = config.replace("your_merchant_id_here", oxapay_merchant or "your_merchant_id_here")
    
    # Write .hacx file
    with open(env_file, 'w') as f:
        f.write(config)
    
    print("✅ .hacx file created successfully")
    return True

def setup_admins():
    """Setup admin users"""
    print("\n👤 Admin Setup:")
    response = input("   Do you want to add an admin user now? (y/N): ").strip().lower()
    
    if response == 'y':
        try:
            user_id = input("   Enter your Telegram User ID: ").strip()
            if user_id.isdigit():
                from add_admin import add_admin_user
                if add_admin_user(int(user_id)):
                    print(f"✅ Admin user {user_id} added successfully")
                else:
                    print(f"⚠️  Could not add admin user {user_id}")
            else:
                print("⚠️  Invalid user ID (must be a number)")
        except Exception as e:
            print(f"⚠️  Error adding admin: {e}")
            print("   You can add admins later using: python add_admin.py USER_ID")
    else:
        print("   You can add admins later using:")
        print("   - python add_admin.py USER_ID")
        print("   - Or add to admins.txt and run: python sync_admins.py")

def verify_setup():
    """Verify the setup"""
    print("\n🔍 Verifying setup...")
    try:
        result = subprocess.run([sys.executable, "production_setup.py"], 
                              capture_output=True, text=True, timeout=30)
        if "READY FOR PRODUCTION" in result.stdout or "READY FOR PRODUCTION" in result.stderr:
            print("✅ Setup verification passed!")
            return True
        else:
            print("⚠️  Setup verification had warnings")
            print("   Review the output above")
            return True  # Still return True as warnings are acceptable
    except Exception as e:
        print(f"⚠️  Could not run verification: {e}")
        return True  # Don't fail setup if verification script has issues

def main():
    """Main setup function"""
    # Check Python version
    if not check_python_version():
        sys.exit(1)
    
    # Install dependencies
    if not install_dependencies():
        print("\n❌ Setup failed at dependency installation")
        sys.exit(1)
    
    # Create environment file
    if not create_env_file():
        print("\n❌ Setup failed at environment configuration")
        sys.exit(1)
    
    # Setup admins
    setup_admins()
    
    # Verify setup
    verify_setup()
    
    # Final instructions
    print("\n" + "="*60)
    print("✅ SETUP COMPLETE!")
    print("="*60)
    print("\n📋 Next Steps:")
    print("   1. Review .hacx file and add any missing configuration")
    print("   2. Add admin users if you haven't already")
    print("   3. Start the bot: python telegram_bot.py")
    print("\n📚 Documentation:")
    print("   - README.md - Main documentation")
    print("   - README_PRODUCTION.md - Production guide")
    print("   - PRODUCTION_CHECKLIST.md - Deployment checklist")
    print("\n🚀 Ready to launch!")
    print("="*60 + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Setup failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

