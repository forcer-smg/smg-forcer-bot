#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Remote Tool Installer
Can be run via Railway shell to install tools and make them permanent
"""

import subprocess
import sys
import os
from pathlib import Path

def install_tool(tool_name, install_cmd, tool_type='system'):
    """Install a tool and optionally update Dockerfile/install_tools.sh"""
    print(f"\n🔧 Installing {tool_name}...")
    print(f"Command: {install_cmd}")
    
    # Run installation
    try:
        result = subprocess.run(
            install_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            print(f"✅ {tool_name} installed successfully!")
            
            # Verify installation
            verify_result = subprocess.run(
                f"which {tool_name}",
                shell=True,
                capture_output=True,
                text=True
            )
            if verify_result.returncode == 0:
                print(f"📍 Location: {verify_result.stdout.strip()}")
            
            # Ask if user wants to make it permanent
            print(f"\n⚠️  This installation is temporary!")
            print(f"   To make it permanent, add to:")
            print(f"   - Dockerfile (for build-time)")
            print(f"   - install_tools.sh (for runtime)")
            print(f"\n   Add this line:")
            print(f"   {install_cmd}")
            
            return True
        else:
            print(f"❌ Installation failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    """Interactive tool installer"""
    print("=" * 70)
    print("REMOTE TOOL INSTALLER")
    print("=" * 70)
    print()
    print("This script helps you install tools on Railway and make them permanent.")
    print()
    
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python remote_tool_installer.py <tool-name> <install-command> [type]")
        print()
        print("Examples:")
        print("  python remote_tool_installer.py httpx 'go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest' go")
        print("  python remote_tool_installer.py dirsearch 'pip install dirsearch' python")
        print("  python remote_tool_installer.py htop 'apt-get update && apt-get install -y htop' system")
        print()
        
        # Interactive mode
        tool_name = input("Tool name: ").strip()
        if not tool_name:
            return
        
        install_cmd = input("Install command: ").strip()
        if not install_cmd:
            return
        
        tool_type = input("Tool type (system/go/python) [system]: ").strip() or "system"
    else:
        tool_name = sys.argv[1]
        install_cmd = sys.argv[2]
        tool_type = sys.argv[3] if len(sys.argv) > 3 else "system"
    
    install_tool(tool_name, install_cmd, tool_type)

if __name__ == '__main__':
    main()
