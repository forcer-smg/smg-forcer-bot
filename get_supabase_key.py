#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Helper script to get Supabase anon key
Opens browser to Supabase dashboard API settings page
"""

import webbrowser
import sys

SUPABASE_PROJECT_REF = "yllsquazrwgbndgonxti"
SUPABASE_URL = f"https://supabase.com/dashboard/project/{SUPABASE_PROJECT_REF}/settings/api"

def main():
    print("=" * 60)
    print("Get Supabase Anon Key")
    print("=" * 60)
    print()
    print("Opening Supabase dashboard in your browser...")
    print()
    print(f"URL: {SUPABASE_URL}")
    print()
    print("Instructions:")
    print("1. The page will open in your browser")
    print("2. Look for 'Project API keys' section")
    print("3. Find the 'anon' or 'public' key")
    print("4. Copy that key (NOT the service_role key)")
    print("5. Use it as SUPABASE_KEY in Railway Variables")
    print()
    
    try:
        webbrowser.open(SUPABASE_URL)
        print("✅ Browser opened!")
        print()
        print("After copying the key, add it to Railway:")
        print("  Variable: SUPABASE_KEY")
        print("  Value: [paste the anon key here]")
        print()
    except Exception as e:
        print(f"❌ Could not open browser: {e}")
        print()
        print("Please manually visit:")
        print(SUPABASE_URL)
        print()
    
    input("Press Enter when you've copied the key...")

if __name__ == "__main__":
    main()

