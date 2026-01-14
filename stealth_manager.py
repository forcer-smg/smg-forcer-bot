# -*- coding: utf-8 -*-
"""
Stealth Manager - Anti-detection system for bot operations
Manages human-like timing, headers, fingerprints, and behavior patterns
"""

import os
import random
import time
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import hashlib

logger = logging.getLogger(__name__)

# Real browser User-Agents (rotated)
REAL_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
]

# Real browser Accept headers
ACCEPT_HEADERS = [
    'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
]

# Real browser Accept-Language headers
ACCEPT_LANGUAGES = [
    'en-US,en;q=0.9',
    'en-US,en;q=0.9,fr;q=0.8',
    'en-GB,en;q=0.9',
    'en-US,en;q=0.9,es;q=0.8',
]


class StealthManager:
    """Manages stealth operations to avoid detection"""
    
    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = workspace_root
        self.request_history = []  # Track request patterns
        self.fingerprint_cache = {}
        self.last_request_time = None
        self.request_count = 0
        
    def get_human_like_headers(self, url: Optional[str] = None) -> Dict:
        """Generate realistic, rotating headers"""
        # Rotate User-Agent
        user_agent = random.choice(REAL_USER_AGENTS)
        
        # Determine browser type from User-Agent
        if 'Chrome' in user_agent:
            browser = 'chrome'
        elif 'Firefox' in user_agent:
            browser = 'firefox'
        elif 'Safari' in user_agent:
            browser = 'safari'
        elif 'Edg' in user_agent:
            browser = 'edge'
        else:
            browser = 'chrome'
        
        headers = {
            'User-Agent': user_agent,
            'Accept': random.choice(ACCEPT_HEADERS),
            'Accept-Language': random.choice(ACCEPT_LANGUAGES),
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
        
        # Add browser-specific headers
        if browser == 'chrome':
            headers['sec-ch-ua'] = '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"'
            headers['sec-ch-ua-mobile'] = '?0'
            headers['sec-ch-ua-platform'] = '"Windows"'
        elif browser == 'firefox':
            headers['DNT'] = '1'
        
        # Add Referer if URL provided
        if url:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                headers['Referer'] = f"{parsed.scheme}://{parsed.netloc}/"
            except:
                pass
        
        return headers
    
    def human_like_delay(self, base_delay: float = 1.0, variance: float = 0.5):
        """Add human-like random delays"""
        # Human-like delay pattern (not uniform)
        # Use normal distribution around base_delay
        delay = base_delay + random.uniform(-variance, variance)
        delay = max(0.5, delay)  # Minimum 0.5 seconds
        
        # Add occasional longer pauses (like humans do)
        if random.random() < 0.1:  # 10% chance
            delay += random.uniform(2.0, 5.0)
        
        time.sleep(delay)
        return delay
    
    def randomize_fingerprint(self) -> Dict:
        """Randomize browser fingerprint"""
        fingerprint = {
            'screen_resolution': random.choice([
                '1920x1080', '1366x768', '1536x864', '1440x900', '1280x720',
                '2560x1440', '1920x1200', '1600x900'
            ]),
            'timezone': random.choice([
                'America/New_York', 'America/Los_Angeles', 'Europe/London',
                'Europe/Paris', 'Asia/Tokyo', 'Asia/Shanghai', 'Australia/Sydney'
            ]),
            'language': random.choice(['en-US', 'en-GB', 'en-CA', 'en-AU']),
            'platform': random.choice(['Win32', 'MacIntel', 'Linux x86_64']),
            'hardware_concurrency': random.choice([4, 8, 12, 16]),
            'device_memory': random.choice([4, 8, 16]),
        }
        
        # Cache fingerprint
        fingerprint_id = hashlib.md5(str(fingerprint).encode()).hexdigest()
        self.fingerprint_cache[fingerprint_id] = fingerprint
        
        return fingerprint
    
    def avoid_rate_limiting(self, requests_count: int, max_requests_per_minute: int = 30):
        """Implement rate limiting avoidance"""
        current_time = time.time()
        
        # Clean old requests (older than 1 minute)
        self.request_history = [
            req_time for req_time in self.request_history
            if current_time - req_time < 60
        ]
        
        # Check if we're approaching rate limit
        if len(self.request_history) >= max_requests_per_minute * 0.8:
            # Slow down - add longer delay
            wait_time = 60 - (current_time - self.request_history[0]) if self.request_history else 0
            if wait_time > 0:
                logger.info(f"Rate limit approaching, waiting {wait_time:.2f} seconds")
                time.sleep(wait_time)
                # Clean history again
                self.request_history = []
        
        # Add request to history
        self.request_history.append(current_time)
        
        # Add human-like delay between requests
        if self.last_request_time:
            time_since_last = current_time - self.last_request_time
            if time_since_last < 1.0:  # If less than 1 second since last request
                self.human_like_delay(base_delay=1.0 - time_since_last)
        
        self.last_request_time = time.time()
        self.request_count += 1
    
    def get_session_config(self) -> Dict:
        """Get session configuration for stealth"""
        return {
            'headers': self.get_human_like_headers(),
            'fingerprint': self.randomize_fingerprint(),
            'timeout': random.uniform(10, 30),  # Vary timeouts
            'verify': True,  # SSL verification
            'allow_redirects': True,
            'max_redirects': random.randint(3, 5),
        }
    
    def should_rotate_proxy(self, request_count: int) -> bool:
        """Determine if proxy should be rotated"""
        # Rotate every 50 requests or if errors detected
        return request_count % 50 == 0
    
    def get_stealth_delay(self, action_type: str = 'request') -> float:
        """Get appropriate delay for action type"""
        delays = {
            'request': random.uniform(1.0, 3.0),
            'navigation': random.uniform(2.0, 5.0),
            'click': random.uniform(0.5, 2.0),
            'typing': random.uniform(0.1, 0.3),  # per character
            'scroll': random.uniform(0.5, 1.5),
        }
        return delays.get(action_type, random.uniform(1.0, 2.0))


def get_stealth_manager(workspace_root: Optional[str] = None) -> StealthManager:
    """Get or create global stealth manager instance"""
    global _stealth_instance
    if '_stealth_instance' not in globals():
        _stealth_instance = None
    
    if _stealth_instance is None:
        _stealth_instance = StealthManager(workspace_root)
    
    return _stealth_instance
