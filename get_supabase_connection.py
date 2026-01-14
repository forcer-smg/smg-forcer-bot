#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Helper script to get Supabase connection string
Guides you through finding or building the connection string
"""

import os

def get_connection_info():
    """Interactive guide to get Supabase connection string"""
    print("\n" + "="*70)
    print("  Supabase Connection String Helper")
    print("="*70)
    
    print("\n📋 Let's get your Supabase connection string!")
    print("\nOption 1: You have the connection string")
    print("Option 2: Build it manually from project details")
    
    choice = input("\nWhich option? (1 or 2): ").strip()
    
    if choice == "1":
        print("\n📍 Where to find it in Supabase:")
        print("1. Go to your Supabase project dashboard")
        print("2. Click 'Settings' (⚙️ icon in left sidebar)")
        print("3. Click 'Database' in settings menu")
        print("4. Scroll to 'Connection string' section")
        print("5. Click 'URI' tab")
        print("6. Copy the connection string")
        print("\nIt should look like:")
        print("  postgresql://postgres:[PASSWORD]@db.xxxxx.supabase.co:5432/postgres")
        
        conn_string = input("\nPaste your connection string here: ").strip()
        
        if conn_string and conn_string.startswith('postgresql://'):
            return conn_string
        else:
            print("❌ Invalid format. Should start with 'postgresql://'")
            return None
    
    elif choice == "2":
        print("\n🔧 Let's build it manually:")
        print("\nYou'll need these from Supabase:")
        print("1. Reference ID (from Settings → General)")
        print("2. Database password (from Settings → Database)")
        
        print("\n📍 To find Reference ID:")
        print("   - Go to Settings → General")
        print("   - Look for 'Reference ID' (looks like: abcdefghijklmnop)")
        
        ref_id = input("\nEnter your Reference ID: ").strip()
        
        print("\n📍 To find/reset password:")
        print("   - Go to Settings → Database")
        print("   - Find 'Database password' section")
        print("   - Or click 'Reset database password' if you forgot it")
        
        password = input("\nEnter your database password: ").strip()
        
        if ref_id and password:
            # Build connection string
            conn_string = f"postgresql://postgres:{password}@db.{ref_id}.supabase.co:5432/postgres"
            print(f"\n✅ Built connection string:")
            print(f"   {conn_string}")
            
            confirm = input("\nUse this connection string? (y/n): ").strip().lower()
            if confirm == 'y':
                return conn_string
            else:
                return None
        else:
            print("❌ Missing information")
            return None
    
    else:
        print("❌ Invalid choice")
        return None

def save_connection_string(conn_string):
    """Save connection string to .hacx file"""
    env_file = '.hacx'
    if not os.path.exists(env_file):
        env_file = '.env'
    
    # Read existing content
    content = ""
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            content = f.read()
    
    # Check if DATABASE_URL already exists
    if 'DATABASE_URL=' in content:
        lines = content.split('\n')
        updated = False
        for i, line in enumerate(lines):
            if line.startswith('DATABASE_URL='):
                lines[i] = f'DATABASE_URL={conn_string}'
                updated = True
                break
        if updated:
            content = '\n'.join(lines)
        else:
            content += f'\nDATABASE_URL={conn_string}\n'
    else:
        content += f'\nDATABASE_URL={conn_string}\n'
    
    # Write back
    with open(env_file, 'w') as f:
        f.write(content)
    
    print(f"\n✅ Connection string saved to {env_file}")

def test_connection(conn_string):
    """Test the connection string"""
    print("\n🔍 Testing connection...")
    
    try:
        import psycopg2
        conn = psycopg2.connect(conn_string)
        conn.close()
        print("✅ Connection successful!")
        return True
    except ImportError:
        print("❌ psycopg2 not installed. Install with: pip install psycopg2-binary")
        return False
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("\nCommon issues:")
        print("  - Wrong password")
        print("  - Wrong reference ID")
        print("  - Network/firewall blocking connection")
        return False

def main():
    print("\n" + "="*70)
    print("  Get Supabase Connection String")
    print("="*70)
    
    conn_string = get_connection_info()
    
    if not conn_string:
        print("\n❌ Could not get connection string")
        return
    
    # Test connection
    if test_connection(conn_string):
        # Save to file
        save = input("\nSave to .hacx file? (y/n): ").strip().lower()
        if save == 'y':
            save_connection_string(conn_string)
            print("\n✅ Setup complete!")
            print("\nNext steps:")
            print("1. Run: python migrate_to_postgres.py")
            print("2. Test bot: python telegram_bot.py")
        else:
            print(f"\n📋 Your connection string:")
            print(f"   {conn_string}")
            print("\nAdd this to your .hacx file:")
            print(f"   DATABASE_URL={conn_string}")
    else:
        print("\n⚠️  Connection test failed. Please check your connection string.")
        print("   You can still save it and test later.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

