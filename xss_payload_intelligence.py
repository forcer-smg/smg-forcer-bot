# -*- coding: utf-8 -*-
"""
XSS Payload Intelligence - Advanced XSS payload management from trusted repositories
Fetches, caches, and manages advanced XSS payloads from multiple sources
"""

import os
import json
import re
import logging
import requests
import subprocess
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime, timedelta
import time

logger = logging.getLogger(__name__)

# XSS Payload Repository Sources
XSS_REPOSITORIES = {
    'payloads_all_the_things': {
        'type': 'github',
        'url': 'https://raw.githubusercontent.com/swisskyrepo/PayloadsAllTheThings/master/XSS%20Injection/XSS.md',
        'update_frequency': 'daily'
    },
    'portswigger': {
        'type': 'web',
        'url': 'https://portswigger.net/web-security/cross-site-scripting/cheat-sheet',
        'update_frequency': 'weekly'
    },
    'owasp': {
        'type': 'web',
        'url': 'https://owasp.org/www-community/xss-filter-evasion-cheatsheet',
        'update_frequency': 'regular'
    },
    'seclists': {
        'type': 'github',
        'url': 'https://raw.githubusercontent.com/danielmiessler/SecLists/master/Fuzzing/XSS/XSS-Jhaddix.txt',
        'update_frequency': 'regular'
    },
    'fuzzdb': {
        'type': 'github',
        'url': 'https://raw.githubusercontent.com/fuzzdb-project/fuzzdb/master/attack/xss/xss-payloads.txt',
        'update_frequency': 'regular'
    }
}

# Advanced payload patterns (not basic)
ADVANCED_PATTERNS = [
    r'<svg.*onload',
    r'<img.*onerror',
    r'javascript:.*',
    r'<iframe.*srcdoc',
    r'<body.*onload',
    r'<input.*onfocus',
    r'<details.*open.*ontoggle',
    r'<marquee.*onstart',
    r'<video.*onloadstart',
    r'<audio.*onloadstart',
    r'<select.*onfocus',
    r'<textarea.*onfocus',
    r'<keygen.*onfocus',
    r'<math.*href',
    r'<link.*href.*javascript',
    r'<base.*href.*javascript',
    r'<form.*action.*javascript',
    r'<isindex.*action.*javascript',
    r'<object.*data.*javascript',
    r'<embed.*src.*javascript',
    r'<source.*src.*javascript',
    r'<track.*src.*javascript',
    r'<style.*@import',
    r'<style.*expression',
    r'<xss.*style',
    r'<script.*src',
    r'<script.*nonce',
    r'<script.*integrity',
    r'<script.*crossorigin',
    r'<script.*async',
    r'<script.*defer',
    r'<script.*type.*module',
    r'<script.*type.*text/template',
    r'<script.*type.*text/x-template',
    r'<script.*type.*application/json',
    r'<script.*type.*application/ld+json',
    r'<script.*type.*application/javascript',
    r'<script.*type.*text/javascript',
    r'<script.*type.*text/ecmascript',
    r'<script.*type.*text/jscript',
    r'<script.*type.*text/vbscript',
    r'<script.*type.*text/xml',
    r'<script.*type.*text/html',
    r'<script.*type.*text/css',
    r'<script.*type.*text/plain',
    r'<script.*type.*text/x-handlebars-template',
    r'<script.*type.*text/x-mustache',
    r'<script.*type.*text/x-jsrender',
    r'<script.*type.*text/x-angular-template',
    r'<script.*type.*text/x-vue-template',
    r'<script.*type.*text/x-react-template',
    r'<script.*type.*text/x-ember-template',
    r'<script.*type.*text/x-backbone-template',
    r'<script.*type.*text/x-underscore-template',
    r'<script.*type.*text/x-lodash-template',
    r'<script.*type.*text/x-dust-template',
    r'<script.*type.*text/x-nunjucks-template',
    r'<script.*type.*text/x-ejs-template',
    r'<script.*type.*text/x-pug-template',
    r'<script.*type.*text/x-handlebars',
    r'<script.*type.*text/x-mustache-template',
    r'<script.*type.*text/x-jsrender-template',
    r'<script.*type.*text/x-angular',
    r'<script.*type.*text/x-vue',
    r'<script.*type.*text/x-react',
    r'<script.*type.*text/x-ember',
    r'<script.*type.*text/x-backbone',
    r'<script.*type.*text/x-underscore',
    r'<script.*type.*text/x-lodash',
    r'<script.*type.*text/x-dust',
    r'<script.*type.*text/x-nunjucks',
    r'<script.*type.*text/x-ejs',
    r'<script.*type.*text/x-pug',
    r'<script.*type.*text/x-handlebars-compiled',
    r'<script.*type.*text/x-mustache-compiled',
    r'<script.*type.*text/x-jsrender-compiled',
    r'<script.*type.*text/x-angular-compiled',
    r'<script.*type.*text/x-vue-compiled',
    r'<script.*type.*text/x-react-compiled',
    r'<script.*type.*text/x-ember-compiled',
    r'<script.*type.*text/x-backbone-compiled',
    r'<script.*type.*text/x-underscore-compiled',
    r'<script.*type.*text/x-lodash-compiled',
    r'<script.*type.*text/x-dust-compiled',
    r'<script.*type.*text/x-nunjucks-compiled',
    r'<script.*type.*text/x-ejs-compiled',
    r'<script.*type.*text/x-pug-compiled',
]


class XSSPayloadIntelligence:
    """Advanced XSS payload intelligence from trusted repositories"""
    
    def __init__(self, workspace_root: Optional[str] = None):
        """
        Initialize XSS Payload Intelligence
        workspace_root: Workspace directory for payload cache
        """
        self.workspace_root = Path(workspace_root) if workspace_root else Path(os.getcwd())
        self.payload_cache_dir = self.workspace_root / "xss_payloads"
        self.payload_cache_dir.mkdir(exist_ok=True)
        
        self.payload_cache = {}
        self.last_update = {}
        self.payload_database = {}  # Categorized payloads
        
        # Load cached payloads
        self._load_cached_payloads()
    
    def _load_cached_payloads(self):
        """Load payloads from cache"""
        cache_file = self.payload_cache_dir / "payloads.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.payload_cache = data.get('payloads', {})
                    self.last_update = data.get('last_update', {})
                    self.payload_database = data.get('database', {})
                logger.info(f"Loaded {sum(len(v) for v in self.payload_cache.values())} cached payloads")
            except Exception as e:
                logger.warning(f"Error loading payload cache: {e}")
    
    def _save_payloads(self):
        """Save payloads to cache"""
        cache_file = self.payload_cache_dir / "payloads.json"
        try:
            data = {
                'payloads': self.payload_cache,
                'last_update': self.last_update,
                'database': self.payload_database
            }
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving payload cache: {e}")
    
    def fetch_payloads_from_repository(self, source: str) -> List[str]:
        """Fetch payloads from a specific repository"""
        if source not in XSS_REPOSITORIES:
            logger.warning(f"Unknown repository: {source}")
            return []
        
        repo_info = XSS_REPOSITORIES[source]
        payloads = []
        
        try:
            if repo_info['type'] == 'github':
                # Fetch from GitHub raw content
                response = requests.get(repo_info['url'], timeout=30)
                response.raise_for_status()
                content = response.text
                
                # Extract payloads from markdown or text
                payloads = self._extract_payloads_from_text(content)
                
            elif repo_info['type'] == 'web':
                # For web pages, would need HTML parsing
                # For now, use cached or manual extraction
                logger.info(f"Web repository {source} requires manual extraction or scraping")
                payloads = []
            
            logger.info(f"Fetched {len(payloads)} payloads from {source}")
            return payloads
            
        except Exception as e:
            logger.error(f"Error fetching payloads from {source}: {e}")
            return []
    
    def _extract_payloads_from_text(self, text: str) -> List[str]:
        """Extract XSS payloads from text content"""
        payloads = []
        
        # Pattern 1: Code blocks with payloads
        code_block_pattern = r'```[^\n]*\n(.*?)```'
        code_blocks = re.findall(code_block_pattern, text, re.DOTALL | re.IGNORECASE)
        for block in code_blocks:
            # Extract potential payloads (lines with script tags, event handlers, etc.)
            lines = block.split('\n')
            for line in lines:
                line = line.strip()
                if self._is_xss_payload(line):
                    payloads.append(line)
        
        # Pattern 2: Inline code with backticks
        inline_code_pattern = r'`([^`]+)`'
        inline_codes = re.findall(inline_code_pattern, text)
        for code in inline_codes:
            if self._is_xss_payload(code):
                payloads.append(code)
        
        # Pattern 3: Lines starting with <script, <img, <svg, etc.
        xss_tag_pattern = r'^<(?:(?:script|img|svg|iframe|body|input|details|marquee|video|audio|select|textarea|keygen|math|link|base|form|isindex|object|embed|source|track|style|xss)[^>]*>.*)$'
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if re.match(xss_tag_pattern, line, re.IGNORECASE):
                payloads.append(line)
        
        # Remove duplicates and filter for advanced payloads
        payloads = list(set(payloads))
        payloads = [p for p in payloads if self._is_advanced_payload(p)]
        
        return payloads
    
    def _is_xss_payload(self, text: str) -> bool:
        """Check if text is an XSS payload"""
        xss_indicators = [
            r'<script',
            r'javascript:',
            r'on\w+\s*=',
            r'<img.*onerror',
            r'<svg.*onload',
            r'<iframe',
            r'<body.*onload',
            r'<input.*onfocus',
            r'alert\s*\(',
            r'confirm\s*\(',
            r'prompt\s*\(',
            r'eval\s*\(',
            r'Function\s*\(',
            r'<style.*expression',
        ]
        
        text_lower = text.lower()
        return any(re.search(pattern, text_lower, re.IGNORECASE) for pattern in xss_indicators)
    
    def _is_advanced_payload(self, payload: str) -> bool:
        """Check if payload is advanced (not basic)"""
        # Basic payloads to exclude
        basic_patterns = [
            r'^<script>alert\(1\)</script>$',
            r'^<script>alert\("XSS"\)</script>$',
            r'^javascript:alert\(1\)$',
            r'^<img src=x onerror=alert\(1\)>$',
        ]
        
        # Check if it's a basic payload
        for pattern in basic_patterns:
            if re.match(pattern, payload, re.IGNORECASE):
                return False
        
        # Check if it contains advanced patterns
        payload_lower = payload.lower()
        advanced_found = any(re.search(pattern, payload_lower, re.IGNORECASE) for pattern in ADVANCED_PATTERNS)
        
        # Also check for complexity (length, encoding, etc.)
        is_complex = (
            len(payload) > 20 or  # Longer than basic
            '%' in payload or  # URL encoding
            '\\x' in payload or  # Hex encoding
            '\\u' in payload or  # Unicode encoding
            '&#x' in payload or  # HTML entity hex
            '&#0' in payload or  # HTML entity decimal
            payload.count('<') > 1 or  # Multiple tags
            payload.count('>') > 1
        )
        
        return advanced_found or is_complex
    
    def get_advanced_payloads(self, context: str = 'html', limit: int = 100) -> List[str]:
        """Get advanced, working payloads for specific context"""
        # Check if we need to update
        self._update_payloads_if_needed()
        
        # Get payloads for context
        context_payloads = self.payload_database.get(context, [])
        
        # Filter for advanced payloads only
        advanced = [p for p in context_payloads if self._is_advanced_payload(p)]
        
        # Limit results
        return advanced[:limit]
    
    def _update_payloads_if_needed(self):
        """Update payloads if cache is stale"""
        should_update = False
        
        for source, repo_info in XSS_REPOSITORIES.items():
            last_update = self.last_update.get(source)
            if not last_update:
                should_update = True
                break
            
            # Check update frequency
            update_freq = repo_info.get('update_frequency', 'daily')
            days_since_update = (datetime.now() - datetime.fromisoformat(last_update)).days
            
            if update_freq == 'daily' and days_since_update >= 1:
                should_update = True
            elif update_freq == 'weekly' and days_since_update >= 7:
                should_update = True
            elif update_freq == 'regular' and days_since_update >= 3:
                should_update = True
        
        if should_update:
            logger.info("Updating XSS payloads from repositories...")
            self.update_payloads_daily()
    
    def update_payloads_daily(self):
        """Update payloads from all sources"""
        all_payloads = []
        
        for source in XSS_REPOSITORIES.keys():
            try:
                payloads = self.fetch_payloads_from_repository(source)
                all_payloads.extend(payloads)
                self.last_update[source] = datetime.now().isoformat()
                logger.info(f"Updated {source}: {len(payloads)} payloads")
            except Exception as e:
                logger.warning(f"Error updating {source}: {e}")
        
        # Categorize payloads
        self._categorize_payloads(all_payloads)
        
        # Save to cache
        self._save_payloads()
        
        logger.info(f"Total advanced payloads: {len(all_payloads)}")
    
    def _categorize_payloads(self, payloads: List[str]):
        """Categorize payloads by context"""
        categories = {
            'html': [],
            'javascript': [],
            'svg': [],
            'dom': [],
            'polyglot': [],
            'filter_evasion': [],
            'csp_bypass': [],
        }
        
        for payload in payloads:
            payload_lower = payload.lower()
            
            # Categorize
            if '<svg' in payload_lower:
                categories['svg'].append(payload)
            elif 'javascript:' in payload_lower or 'eval(' in payload_lower:
                categories['javascript'].append(payload)
            elif 'document.' in payload_lower or 'window.' in payload_lower:
                categories['dom'].append(payload)
            elif self._is_polyglot(payload):
                categories['polyglot'].append(payload)
            elif self._is_filter_evasion(payload):
                categories['filter_evasion'].append(payload)
            elif self._is_csp_bypass(payload):
                categories['csp_bypass'].append(payload)
            else:
                categories['html'].append(payload)
        
        # Store in database
        self.payload_database = categories
        self.payload_cache = {cat: payloads for cat, payloads in categories.items()}
    
    def _is_polyglot(self, payload: str) -> bool:
        """Check if payload is a polyglot (works in multiple contexts)"""
        # Polyglots typically work in HTML, JavaScript, and other contexts
        indicators = [
            r'jaVasCript:',
            r'<svg/onload',
            r'<img/src',
            r'<iframe/srcdoc',
            r'<body/onload',
            r'<input/onfocus',
            r'<details/open/ontoggle',
            r'<marquee/onstart',
        ]
        return any(re.search(pattern, payload, re.IGNORECASE) for pattern in indicators)
    
    def _is_filter_evasion(self, payload: str) -> bool:
        """Check if payload uses filter evasion techniques"""
        evasion_indicators = [
            r'%3C',  # URL encoded <
            r'%3E',  # URL encoded >
            r'\\x3c',  # Hex encoded <
            r'\\x3e',  # Hex encoded >
            r'&#x3c',  # HTML entity <
            r'&#x3e',  # HTML entity >
            r'&#60',  # HTML entity <
            r'&#62',  # HTML entity >
            r'&#x00',  # Null bytes
            r'\\u003c',  # Unicode <
            r'\\u003e',  # Unicode >
            r'String\.fromCharCode',
            r'String\.fromCodePoint',
            r'atob\s*\(',
            r'btoa\s*\(',
            r'unescape\s*\(',
            r'decodeURIComponent\s*\(',
        ]
        return any(re.search(pattern, payload, re.IGNORECASE) for pattern in evasion_indicators)
    
    def _is_csp_bypass(self, payload: str) -> bool:
        """Check if payload is a CSP bypass"""
        csp_bypass_indicators = [
            r'<link.*rel.*prefetch',
            r'<link.*rel.*dns-prefetch',
            r'<link.*rel.*preconnect',
            r'<link.*rel.*prerender',
            r'<base.*href',
            r'<form.*action',
            r'<meta.*http-equiv.*refresh',
            r'<iframe.*srcdoc',
            r'<object.*data',
            r'<embed.*src',
        ]
        return any(re.search(pattern, payload, re.IGNORECASE) for pattern in csp_bypass_indicators)
    
    def test_payload_effectiveness(self, payload: str) -> Dict:
        """Test if payload works against common filters"""
        effectiveness = {
            'payload': payload,
            'works_against_basic_filter': True,
            'works_against_waf': False,
            'works_against_csp': False,
            'contexts': [],
            'effectiveness_score': 0
        }
        
        # Test against basic filter (most payloads pass)
        if not self._would_be_blocked_by_basic_filter(payload):
            effectiveness['works_against_basic_filter'] = True
            effectiveness['effectiveness_score'] += 1
        
        # Test against WAF (advanced payloads more likely to pass)
        if self._is_filter_evasion(payload):
            effectiveness['works_against_waf'] = True
            effectiveness['effectiveness_score'] += 2
        
        # Test against CSP (CSP bypass payloads)
        if self._is_csp_bypass(payload):
            effectiveness['works_against_csp'] = True
            effectiveness['effectiveness_score'] += 3
        
        # Determine contexts
        payload_lower = payload.lower()
        if '<svg' in payload_lower:
            effectiveness['contexts'].append('svg')
        if 'javascript:' in payload_lower:
            effectiveness['contexts'].append('javascript')
        if 'document.' in payload_lower:
            effectiveness['contexts'].append('dom')
        if self._is_polyglot(payload):
            effectiveness['contexts'].append('polyglot')
        
        return effectiveness
    
    def _would_be_blocked_by_basic_filter(self, payload: str) -> bool:
        """Check if payload would be blocked by basic filter"""
        # Basic filters typically block simple patterns
        basic_blocked_patterns = [
            r'<script>alert\(1\)</script>',
            r'<script>alert\("XSS"\)</script>',
            r'javascript:alert\(1\)',
        ]
        return any(re.search(pattern, payload, re.IGNORECASE) for pattern in basic_blocked_patterns)
    
    def get_all_advanced_payloads(self, limit: int = 500) -> List[str]:
        """Get all advanced payloads from all categories"""
        self._update_payloads_if_needed()
        
        all_payloads = []
        for category_payloads in self.payload_database.values():
            advanced = [p for p in category_payloads if self._is_advanced_payload(p)]
            all_payloads.extend(advanced)
        
        # Remove duplicates
        all_payloads = list(set(all_payloads))
        
        return all_payloads[:limit]


def get_xss_payload_intelligence(workspace_root: Optional[str] = None) -> XSSPayloadIntelligence:
    """Get or create global XSS payload intelligence instance"""
    global _xss_instance
    if '_xss_instance' not in globals():
        _xss_instance = None
    
    if _xss_instance is None:
        _xss_instance = XSSPayloadIntelligence(workspace_root)
    
    return _xss_instance
