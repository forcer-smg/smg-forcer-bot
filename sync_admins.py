# -*- coding: utf-8 -*-
"""
Sync admins from admins.txt file to database
Run this script after updating admins.txt to sync changes
"""

import os
from database import Database

ADMINS_FILE = "admins.txt"

def read_admins_from_file():
    """Read admin user IDs from admins.txt file"""
    admins = []
    
    if not os.path.exists(ADMINS_FILE):
        print(f"❌ {ADMINS_FILE} not found. Creating empty file...")
        with open(ADMINS_FILE, 'w') as f:
            f.write("# Admin User IDs\n")
            f.write("# Add one Telegram User ID per line\n")
            f.write("# Lines starting with # are ignored\n")
        return admins
    
    with open(ADMINS_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            try:
                user_id = int(line)
                admins.append(user_id)
            except ValueError:
                print(f"⚠️  Warning: Invalid user ID '{line}' in {ADMINS_FILE} (skipping)")
    
    return admins

def sync_admins():
    """Sync admins from file to database"""
    db = Database()
    
    # Read admins from file
    file_admins = read_admins_from_file()
    
    if not file_admins:
        print(f"⚠️  No admins found in {ADMINS_FILE}")
        print(f"   Add user IDs to {ADMINS_FILE} (one per line)")
        return
    
    print(f"📋 Found {len(file_admins)} admin(s) in {ADMINS_FILE}")
    
    # Get current admins from database
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM admins")
    db_admins = [row['user_id'] for row in cursor.fetchall()]
    conn.close()
    
    print(f"📊 Current admins in database: {len(db_admins)}")
    
    # Add admins from file
    added = 0
    already_exists = 0
    
    for user_id in file_admins:
        if user_id in db_admins:
            already_exists += 1
            print(f"   ✓ User {user_id} already admin")
        else:
            db.add_admin(user_id)
            added += 1
            print(f"   ✅ Added user {user_id} as admin")
    
    # Remove admins not in file (optional - comment out if you don't want this)
    removed = 0
    for db_admin in db_admins:
        if db_admin not in file_admins:
            # Optionally remove admins not in file
            # Uncomment the lines below if you want to remove admins not in file
            # conn = db.get_connection()
            # cursor = conn.cursor()
            # cursor.execute("DELETE FROM admins WHERE user_id = ?", (db_admin,))
            # conn.commit()
            # conn.close()
            # removed += 1
            # print(f"   ❌ Removed user {db_admin} from admins (not in file)")
            pass
    
    print("\n" + "=" * 50)
    print("📊 SYNC SUMMARY")
    print("=" * 50)
    print(f"✅ Added: {added}")
    print(f"✓ Already exists: {already_exists}")
    if removed > 0:
        print(f"❌ Removed: {removed}")
    print(f"📋 Total admins: {len(file_admins)}")
    print("=" * 50)

if __name__ == "__main__":
    print("=" * 50)
    print("🔄 SYNCING ADMINS FROM FILE")
    print("=" * 50)
    print()
    
    sync_admins()
    
    print("\n💡 Tip: Edit admins.txt and run this script again to update admins")

