#!/usr/bin/env python3
"""
Prepare repository for GitHub upload
Creates necessary files and checks for sensitive data
"""

import os
import sys
from pathlib import Path

print("\n" + "="*60)
print("GITHUB PREPARATION CHECK")
print("="*60 + "\n")

warnings = []
errors = []

# Check for sensitive files
sensitive_files = [
    ".hacx",
    "smg_forcer.db",
    "*.log",
    "__pycache__",
]

print("🔍 Checking for sensitive files...")
for pattern in sensitive_files:
    files = list(Path(".").glob(pattern))
    if files:
        for file in files:
            if file.is_file():
                print(f"   ⚠️  Found: {file}")
                warnings.append(f"Sensitive file found: {file}")

# Check .gitignore
print("\n📋 Checking .gitignore...")
if Path(".gitignore").exists():
    print("   ✅ .gitignore exists")
    with open(".gitignore", 'r') as f:
        gitignore_content = f.read()
    
    required_patterns = [".hacx", "*.db", "__pycache__", "*.log"]
    missing = []
    for pattern in required_patterns:
        if pattern not in gitignore_content:
            missing.append(pattern)
    
    if missing:
        print(f"   ⚠️  Missing patterns: {', '.join(missing)}")
        warnings.append(f".gitignore missing patterns: {', '.join(missing)}")
    else:
        print("   ✅ All required patterns present")
else:
    print("   ❌ .gitignore not found!")
    errors.append(".gitignore file missing")

# Check required files
print("\n📄 Checking required files...")
required_files = [
    "README.md",
    "requirements.txt",
    ".env.example",
    "telegram_bot.py",
    "database.py",
    "HacxGPT.py",
]

for file in required_files:
    if Path(file).exists():
        print(f"   ✅ {file}")
    else:
        print(f"   ❌ {file} - MISSING")
        errors.append(f"Required file missing: {file}")

# Check for hardcoded secrets
print("\n🔐 Checking for hardcoded secrets...")
code_files = list(Path(".").glob("*.py"))
secrets_found = False

for code_file in code_files:
    if code_file.name == "prepare_github.py":
        continue
    
    try:
        with open(code_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
            # Check for common secret patterns
            suspicious = []
            if "sk-" in content and "api" in content.lower():
                suspicious.append("Possible API key")
            if "token" in content.lower() and "=" in content and len(content.split("token")[1].split("=")[1].strip()) > 20:
                suspicious.append("Possible hardcoded token")
            
            if suspicious:
                print(f"   ⚠️  {code_file.name}: {', '.join(suspicious)}")
                warnings.append(f"{code_file.name} may contain hardcoded secrets")
                secrets_found = True
    except Exception as e:
        print(f"   ⚠️  Could not check {code_file.name}: {e}")

if not secrets_found:
    print("   ✅ No obvious hardcoded secrets found")

# Summary
print("\n" + "="*60)
print("SUMMARY")
print("="*60)

if warnings:
    print(f"\n⚠️  WARNINGS: {len(warnings)}")
    for i, warning in enumerate(warnings, 1):
        print(f"   {i}. {warning}")

if errors:
    print(f"\n❌ ERRORS: {len(errors)}")
    for i, error in enumerate(errors, 1):
        print(f"   {i}. {error}")
    print("\n❌ NOT READY FOR GITHUB - Fix errors above")
    sys.exit(1)
else:
    print("\n✅ READY FOR GITHUB!")
    if warnings:
        print("⚠️  Review warnings above before uploading")
    print("\n📋 Next Steps:")
    print("   1. Review all warnings")
    print("   2. Make sure .hacx is in .gitignore")
    print("   3. Make sure database files are in .gitignore")
    print("   4. Initialize git: git init")
    print("   5. Add files: git add .")
    print("   6. Commit: git commit -m 'Initial commit'")
    print("   7. Create GitHub repo and push")
    print("="*60 + "\n")

