#!/usr/bin/env python3
"""
Backup and Restore Script for SMG-Forcer Bot
Use this to backup your bot configuration and restore it later
"""

import os
import sys
import shutil
import json
from datetime import datetime
from pathlib import Path

BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(exist_ok=True)

def backup_config():
    """Backup configuration files"""
    print("\n" + "="*60)
    print("BACKUP CONFIGURATION")
    print("="*60 + "\n")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{timestamp}"
    backup_path = BACKUP_DIR / backup_name
    backup_path.mkdir(exist_ok=True)
    
    files_to_backup = {
        ".hacx": "Environment variables",
        "admins.txt": "Admin list",
        "smg_forcer.db": "Database (if exists)",
    }
    
    backed_up = []
    skipped = []
    
    for file_name, description in files_to_backup.items():
        source = Path(file_name)
        if source.exists():
            try:
                dest = backup_path / file_name
                if source.is_file():
                    shutil.copy2(source, dest)
                elif source.is_dir():
                    shutil.copytree(source, dest, dirs_exist_ok=True)
                backed_up.append(f"✅ {description}: {file_name}")
            except Exception as e:
                skipped.append(f"❌ {description}: {file_name} - {e}")
        else:
            skipped.append(f"⚠️  {description}: {file_name} - Not found")
    
    # Create backup info file
    info = {
        "timestamp": timestamp,
        "backup_name": backup_name,
        "files_backed_up": [f for f in files_to_backup.keys() if Path(f).exists()],
        "python_version": sys.version,
    }
    
    with open(backup_path / "backup_info.json", 'w') as f:
        json.dump(info, f, indent=2)
    
    print("📦 Backup Summary:")
    for item in backed_up:
        print(f"   {item}")
    if skipped:
        print("\n⚠️  Skipped:")
        for item in skipped:
            print(f"   {item}")
    
    print(f"\n✅ Backup created: {backup_path}")
    print(f"   Total size: {get_dir_size(backup_path) / 1024:.2f} KB")
    
    return backup_path

def restore_config(backup_name=None):
    """Restore configuration from backup"""
    print("\n" + "="*60)
    print("RESTORE CONFIGURATION")
    print("="*60 + "\n")
    
    if backup_name is None:
        # List available backups
        backups = [d for d in BACKUP_DIR.iterdir() if d.is_dir() and d.name.startswith("backup_")]
        if not backups:
            print("❌ No backups found!")
            return False
        
        backups.sort(reverse=True)  # Newest first
        
        print("Available backups:")
        for i, backup in enumerate(backups, 1):
            info_file = backup / "backup_info.json"
            if info_file.exists():
                with open(info_file, 'r') as f:
                    info = json.load(f)
                timestamp = info.get('timestamp', 'Unknown')
                print(f"   {i}. {backup.name} ({timestamp})")
            else:
                print(f"   {i}. {backup.name}")
        
        choice = input("\nSelect backup number to restore (or 'q' to quit): ").strip()
        if choice.lower() == 'q':
            return False
        
        try:
            backup_path = backups[int(choice) - 1]
        except (ValueError, IndexError):
            print("❌ Invalid selection")
            return False
    else:
        backup_path = BACKUP_DIR / backup_name
        if not backup_path.exists():
            print(f"❌ Backup not found: {backup_name}")
            return False
    
    print(f"\n📦 Restoring from: {backup_path.name}")
    
    # Confirm
    response = input("⚠️  This will overwrite existing files. Continue? (y/N): ").strip().lower()
    if response != 'y':
        print("❌ Restore cancelled")
        return False
    
    files_to_restore = [".hacx", "admins.txt", "smg_forcer.db"]
    
    restored = []
    failed = []
    
    for file_name in files_to_restore:
        source = backup_path / file_name
        if source.exists():
            try:
                dest = Path(file_name)
                if dest.exists():
                    # Backup existing file first
                    backup_dest = Path(f"{file_name}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                    shutil.copy2(dest, backup_dest)
                    print(f"   Backed up existing {file_name} to {backup_dest.name}")
                
                if source.is_file():
                    shutil.copy2(source, dest)
                elif source.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(source, dest)
                
                restored.append(f"✅ {file_name}")
            except Exception as e:
                failed.append(f"❌ {file_name} - {e}")
        else:
            print(f"   ⚠️  {file_name} not found in backup")
    
    print("\n📦 Restore Summary:")
    for item in restored:
        print(f"   {item}")
    if failed:
        print("\n❌ Failed:")
        for item in failed:
            print(f"   {item}")
    
    if restored:
        print("\n✅ Restore completed!")
        print("   Review restored files and restart the bot")
        return True
    else:
        print("\n❌ No files were restored")
        return False

def list_backups():
    """List all available backups"""
    backups = [d for d in BACKUP_DIR.iterdir() if d.is_dir() and d.name.startswith("backup_")]
    if not backups:
        print("\n📦 No backups found")
        return
    
    backups.sort(reverse=True)
    
    print("\n" + "="*60)
    print("AVAILABLE BACKUPS")
    print("="*60 + "\n")
    
    for backup in backups:
        info_file = backup / "backup_info.json"
        size = get_dir_size(backup) / 1024  # KB
        
        if info_file.exists():
            with open(info_file, 'r') as f:
                info = json.load(f)
            timestamp = info.get('timestamp', 'Unknown')
            files = len(info.get('files_backed_up', []))
            print(f"📦 {backup.name}")
            print(f"   Date: {timestamp}")
            print(f"   Files: {files}")
            print(f"   Size: {size:.2f} KB")
        else:
            print(f"📦 {backup.name}")
            print(f"   Size: {size:.2f} KB")
        print()

def get_dir_size(path):
    """Get total size of directory"""
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if os.path.exists(filepath):
                total += os.path.getsize(filepath)
    return total

def main():
    """Main function"""
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "backup":
            backup_config()
        elif command == "restore":
            if len(sys.argv) > 2:
                restore_config(sys.argv[2])
            else:
                restore_config()
        elif command == "list":
            list_backups()
        else:
            print(f"❌ Unknown command: {command}")
            print("\nUsage:")
            print("  python backup_restore.py backup    - Create backup")
            print("  python backup_restore.py restore   - Restore from backup")
            print("  python backup_restore.py list      - List backups")
    else:
        # Interactive mode
        print("\n" + "="*60)
        print("BACKUP & RESTORE UTILITY")
        print("="*60)
        print("\n1. Create Backup")
        print("2. Restore from Backup")
        print("3. List Backups")
        print("4. Exit")
        
        choice = input("\nSelect option (1-4): ").strip()
        
        if choice == "1":
            backup_config()
        elif choice == "2":
            restore_config()
        elif choice == "3":
            list_backups()
        elif choice == "4":
            print("Goodbye!")
        else:
            print("❌ Invalid option")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Operation cancelled")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

