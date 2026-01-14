#!/usr/bin/env python3
"""Check if all requirements are installed"""

required_packages = {
    'openai': 'openai',
    'colorama': 'colorama',
    'pwinput': 'pwinput',
    'dotenv': 'python-dotenv',
    'rich': 'rich',
    'telegram': 'python-telegram-bot',
    'requests': 'requests',
    'flask': 'flask'
}

print("Checking required packages...\n")

missing = []
installed = []

for import_name, package_name in required_packages.items():
    try:
        if import_name == 'dotenv':
            from dotenv import load_dotenv
        elif import_name == 'telegram':
            from telegram import Update
        else:
            __import__(import_name)
        installed.append(package_name)
        print(f"✅ {package_name}")
    except ImportError:
        missing.append(package_name)
        print(f"❌ {package_name} - MISSING")

print(f"\n{'='*50}")
print(f"Installed: {len(installed)}/{len(required_packages)}")
if missing:
    print(f"Missing: {', '.join(missing)}")
    print(f"\nTo install missing packages, run:")
    print(f"pip install {' '.join(missing)}")
else:
    print("\n🎉 All packages are installed!")

