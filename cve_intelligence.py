# -*- coding: utf-8 -*-
"""
CVE Intelligence - Comprehensive CVE database integrations
Integrates NVD, Vulners, OSV, GitHub Advisories, and other CVE sources
"""

import os
import json
import logging
import time
from typing import Dict, List, Optional, Any
from pathlib import Path
import requests
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CVEIntelligence:
    """Comprehensive CVE intelligence from multiple sources"""
    
    def __init__(self, workspace_root: Optional[str] = None):
        """
        Initialize CVE Intelligence
        workspace_root: Workspace directory for caching
        """
        self.workspace_root = Path(workspace_root) if workspace_root else Path(os.getcwd())
        self.cache_dir = self.workspace_root / "cve_cache"
        self.cache_dir.mkdir(exist_ok=True)
        
        # API keys (optional, some APIs work without keys)
        self.nvd_api_key = os.getenv('NVD_API_KEY')  # Optional, increases rate limit
        self.vulners_api_key = os.getenv('VULNERS_API_KEY')  # Optional
        
        # Rate limiting
        self.last_nvd_request = 0
        self.nvd_rate_limit = 0.6  # NVD allows 5 requests per 30 seconds (6 seconds between requests)
        
        # Cache settings
        self.cache_duration = timedelta(hours=24)  # Cache CVE data for 24 hours
    
    def get_cve_nvd(self, cve_id: str) -> Dict:
        """Get CVE information from NVD (National Vulnerability Database)"""
        cache_file = self.cache_dir / f"nvd_{cve_id}.json"
        
        # Check cache
        if cache_file.exists():
            cache_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if cache_age < self.cache_duration:
                try:
                    with open(cache_file, 'r') as f:
                        return json.load(f)
                except Exception as e:
                    logger.warning(f"Error reading CVE cache: {e}")
        
        # Rate limiting
        time_since_last = time.time() - self.last_nvd_request
        if time_since_last < self.nvd_rate_limit:
            time.sleep(self.nvd_rate_limit - time_since_last)
        
        try:
            url = f"https://services.nvd.nist.gov/rest/json/cves/2.0"
            params = {
                'cveId': cve_id
            }
            headers = {}
            if self.nvd_api_key:
                headers['apiKey'] = self.nvd_api_key
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            self.last_nvd_request = time.time()
            
            # Extract CVE information
            cve_data = {}
            if 'vulnerabilities' in data and data['vulnerabilities']:
                vuln = data['vulnerabilities'][0].get('cve', {})
                cve_data = {
                    'cve_id': cve_id,
                    'description': vuln.get('descriptions', [{}])[0].get('value', ''),
                    'cvss_v3': None,
                    'cvss_v2': None,
                    'severity': 'UNKNOWN',
                    'published_date': vuln.get('published', ''),
                    'modified_date': vuln.get('lastModified', ''),
                    'references': [ref.get('url', '') for ref in vuln.get('references', [])],
                    'source': 'NVD'
                }
                
                # Extract CVSS scores
                metrics = vuln.get('metrics', {})
                if 'cvssMetricV31' in metrics:
                    cvss_v3 = metrics['cvssMetricV31'][0].get('cvssData', {})
                    cve_data['cvss_v3'] = {
                        'base_score': cvss_v3.get('baseScore'),
                        'severity': cvss_v3.get('baseSeverity'),
                        'vector': cvss_v3.get('vectorString')
                    }
                    cve_data['severity'] = cvss_v3.get('baseSeverity', 'UNKNOWN')
                elif 'cvssMetricV30' in metrics:
                    cvss_v3 = metrics['cvssMetricV30'][0].get('cvssData', {})
                    cve_data['cvss_v3'] = {
                        'base_score': cvss_v3.get('baseScore'),
                        'severity': cvss_v3.get('baseSeverity'),
                        'vector': cvss_v3.get('vectorString')
                    }
                    cve_data['severity'] = cvss_v3.get('baseSeverity', 'UNKNOWN')
                elif 'cvssMetricV2' in metrics:
                    cvss_v2 = metrics['cvssMetricV2'][0].get('cvssData', {})
                    cve_data['cvss_v2'] = {
                        'base_score': cvss_v2.get('baseScore'),
                        'severity': cvss_v2.get('baseSeverity'),
                        'vector': cvss_v2.get('vectorString')
                    }
                    cve_data['severity'] = cvss_v2.get('baseSeverity', 'UNKNOWN')
            
            # Cache result
            try:
                with open(cache_file, 'w') as f:
                    json.dump(cve_data, f, indent=2)
            except Exception as e:
                logger.warning(f"Error caching CVE: {e}")
            
            return cve_data
        
        except Exception as e:
            logger.error(f"Error fetching CVE from NVD: {e}")
            return {'cve_id': cve_id, 'error': str(e), 'source': 'NVD'}
    
    def search_cve_by_product(self, product: str, version: Optional[str] = None) -> List[Dict]:
        """Search CVEs by product name and optionally version"""
        try:
            url = f"https://services.nvd.nist.gov/rest/json/cves/2.0"
            params = {
                'keywordSearch': product
            }
            if version:
                params['keywordSearch'] = f"{product} {version}"
            
            headers = {}
            if self.nvd_api_key:
                headers['apiKey'] = self.nvd_api_key
            
            # Rate limiting
            time_since_last = time.time() - self.last_nvd_request
            if time_since_last < self.nvd_rate_limit:
                time.sleep(self.nvd_rate_limit - time_since_last)
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            self.last_nvd_request = time.time()
            
            cves = []
            for vuln in data.get('vulnerabilities', [])[:20]:  # Limit to 20 results
                cve = vuln.get('cve', {})
                cve_data = {
                    'cve_id': cve.get('id', ''),
                    'description': cve.get('descriptions', [{}])[0].get('value', ''),
                    'published_date': cve.get('published', ''),
                    'source': 'NVD'
                }
                cves.append(cve_data)
            
            return cves
        
        except Exception as e:
            logger.error(f"Error searching CVEs: {e}")
            return []
    
    def get_cve_vulners(self, cve_id: str) -> Dict:
        """Get CVE information from Vulners"""
        cache_file = self.cache_dir / f"vulners_{cve_id}.json"
        
        # Check cache
        if cache_file.exists():
            cache_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if cache_age < self.cache_duration:
                try:
                    with open(cache_file, 'r') as f:
                        return json.load(f)
                except Exception as e:
                    logger.warning(f"Error reading Vulners cache: {e}")
        
        try:
            url = "https://vulners.com/api/v3/search/lucene/"
            params = {
                'query': f'cveId:{cve_id}',
                'size': 1
            }
            headers = {
                'User-Agent': 'Mozilla/5.0'
            }
            if self.vulners_api_key:
                headers['X-Vulners-Api-Key'] = self.vulners_api_key
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            cve_data = {
                'cve_id': cve_id,
                'source': 'Vulners',
                'exploit_available': False,
                'exploit_count': 0
            }
            
            if 'data' in data and 'search' in data['data']:
                results = data['data']['search']
                if results:
                    result = results[0]
                    cve_data.update({
                        'description': result.get('description', ''),
                        'published_date': result.get('published', ''),
                        'modified_date': result.get('modified', ''),
                        'cvss_score': result.get('cvss', {}).get('score'),
                        'severity': result.get('cvss', {}).get('severity'),
                        'exploit_available': result.get('exploit', False),
                        'exploit_count': result.get('exploitCount', 0),
                        'references': result.get('references', [])
                    })
            
            # Cache result
            try:
                with open(cache_file, 'w') as f:
                    json.dump(cve_data, f, indent=2)
            except Exception as e:
                logger.warning(f"Error caching Vulners CVE: {e}")
            
            return cve_data
        
        except Exception as e:
            logger.error(f"Error fetching CVE from Vulners: {e}")
            return {'cve_id': cve_id, 'error': str(e), 'source': 'Vulners'}
    
    def get_cve_osv(self, cve_id: str) -> Dict:
        """Get CVE information from OSV (Open Source Vulnerabilities)"""
        try:
            url = f"https://osv.dev/api/v1/vulns/{cve_id}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            cve_data = {
                'cve_id': cve_id,
                'source': 'OSV',
                'summary': data.get('summary', ''),
                'details': data.get('details', ''),
                'published': data.get('published', ''),
                'modified': data.get('modified', ''),
                'severity': [],
                'references': data.get('references', []),
                'affected_packages': []
            }
            
            # Extract severity
            if 'severity' in data:
                for sev in data['severity']:
                    if 'score' in sev:
                        cve_data['severity'].append({
                            'type': sev.get('type', ''),
                            'score': sev.get('score', '')
                        })
            
            # Extract affected packages
            if 'affected' in data:
                for affected in data['affected']:
                    package = affected.get('package', {})
                    cve_data['affected_packages'].append({
                        'name': package.get('name', ''),
                        'ecosystem': package.get('ecosystem', ''),
                        'versions': affected.get('versions', [])
                    })
            
            return cve_data
        
        except Exception as e:
            logger.error(f"Error fetching CVE from OSV: {e}")
            return {'cve_id': cve_id, 'error': str(e), 'source': 'OSV'}
    
    def get_cve_github(self, cve_id: str) -> Dict:
        """Get CVE information from GitHub Advisory Database"""
        try:
            # GitHub uses GHSA format, need to search
            url = "https://api.github.com/advisories"
            params = {
                'cve_id': cve_id,
                'per_page': 1
            }
            headers = {
                'Accept': 'application/vnd.github+json'
            }
            github_token = os.getenv('GITHUB_TOKEN')
            if github_token:
                headers['Authorization'] = f'token {github_token}'
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            cve_data = {
                'cve_id': cve_id,
                'source': 'GitHub',
                'advisories': []
            }
            
            for advisory in data:
                cve_data['advisories'].append({
                    'ghsa_id': advisory.get('ghsa_id', ''),
                    'summary': advisory.get('summary', ''),
                    'description': advisory.get('description', ''),
                    'severity': advisory.get('severity', ''),
                    'published_at': advisory.get('published_at', ''),
                    'updated_at': advisory.get('updated_at', ''),
                    'vulnerabilities': advisory.get('vulnerabilities', [])
                })
            
            return cve_data
        
        except Exception as e:
            logger.error(f"Error fetching CVE from GitHub: {e}")
            return {'cve_id': cve_id, 'error': str(e), 'source': 'GitHub'}
    
    def get_cve_comprehensive(self, cve_id: str) -> Dict:
        """Get comprehensive CVE information from all sources"""
        result = {
            'cve_id': cve_id,
            'sources': {},
            'combined': {
                'severity': 'UNKNOWN',
                'exploit_available': False,
                'exploit_count': 0,
                'description': '',
                'references': []
            }
        }
        
        # Get from NVD (primary source)
        nvd_data = self.get_cve_nvd(cve_id)
        result['sources']['nvd'] = nvd_data
        if nvd_data.get('severity'):
            result['combined']['severity'] = nvd_data['severity']
        if nvd_data.get('description'):
            result['combined']['description'] = nvd_data['description']
        if nvd_data.get('references'):
            result['combined']['references'].extend(nvd_data['references'])
        
        # Get from Vulners (exploit intelligence)
        vulners_data = self.get_cve_vulners(cve_id)
        result['sources']['vulners'] = vulners_data
        if vulners_data.get('exploit_available'):
            result['combined']['exploit_available'] = True
        if vulners_data.get('exploit_count', 0) > 0:
            result['combined']['exploit_count'] = vulners_data['exploit_count']
        
        # Get from OSV (open source focus)
        osv_data = self.get_cve_osv(cve_id)
        result['sources']['osv'] = osv_data
        if osv_data.get('affected_packages'):
            result['combined']['affected_packages'] = osv_data['affected_packages']
        
        # Get from GitHub (developer focus)
        github_data = self.get_cve_github(cve_id)
        result['sources']['github'] = github_data
        
        return result
    
    def check_exploit_availability(self, cve_id: str) -> Dict:
        """Check if exploits are available for a CVE"""
        result = {
            'cve_id': cve_id,
            'exploit_available': False,
            'exploit_sources': [],
            'exploit_count': 0
        }
        
        # Check Vulners
        vulners_data = self.get_cve_vulners(cve_id)
        if vulners_data.get('exploit_available'):
            result['exploit_available'] = True
            result['exploit_count'] += vulners_data.get('exploit_count', 0)
            result['exploit_sources'].append('Vulners')
        
        return result
    
    def get_trending_cves(self, limit: int = 10) -> List[Dict]:
        """Get trending CVEs (from Vulners or CVE Trends)"""
        try:
            # Use Vulners trending API
            url = "https://vulners.com/api/v3/search/lucene/"
            params = {
                'query': 'type:cve',
                'sort': 'published desc',
                'size': limit
            }
            headers = {
                'User-Agent': 'Mozilla/5.0'
            }
            if self.vulners_api_key:
                headers['X-Vulners-Api-Key'] = self.vulners_api_key
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            trending = []
            if 'data' in data and 'search' in data['data']:
                for result in data['data']['search']:
                    trending.append({
                        'cve_id': result.get('id', ''),
                        'description': result.get('description', ''),
                        'published_date': result.get('published', ''),
                        'cvss_score': result.get('cvss', {}).get('score'),
                        'severity': result.get('cvss', {}).get('severity'),
                        'exploit_available': result.get('exploit', False)
                    })
            
            return trending
        
        except Exception as e:
            logger.error(f"Error getting trending CVEs: {e}")
            return []
    
    def get_recent_cves(self, days: int = 7, limit: int = 50) -> List[Dict]:
        """Get recent CVEs from last N days"""
        try:
            # Use Vulners to get recent CVEs
            url = "https://vulners.com/api/v3/search/lucene/"
            params = {
                'query': 'type:cve',
                'sort': 'published desc',
                'size': limit
            }
            headers = {
                'User-Agent': 'Mozilla/5.0'
            }
            if self.vulners_api_key:
                headers['X-Vulners-Api-Key'] = self.vulners_api_key
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            recent_cves = []
            if 'data' in data and 'search' in data['data']:
                cutoff_date = datetime.now() - timedelta(days=days)
                
                for result in data['data']['search']:
                    published = result.get('published', '')
                    if published:
                        try:
                            pub_date = datetime.fromisoformat(published.replace('Z', '+00:00'))
                            if pub_date >= cutoff_date:
                                recent_cves.append({
                                    'cve_id': result.get('id', ''),
                                    'description': result.get('description', ''),
                                    'published': published,
                                    'cvss_score': result.get('cvss', {}).get('score'),
                                    'severity': result.get('cvss', {}).get('severity'),
                                    'exploit_available': result.get('exploit', False),
                                    'affected_products': result.get('affected', []),
                                    'references': result.get('references', [])
                                })
                        except:
                            # Include if date parsing fails
                            recent_cves.append({
                                'cve_id': result.get('id', ''),
                                'description': result.get('description', ''),
                                'published': published,
                                'cvss_score': result.get('cvss', {}).get('score'),
                                'severity': result.get('cvss', {}).get('severity'),
                                'exploit_available': result.get('exploit', False)
                            })
            
            return recent_cves[:limit]
            
        except Exception as e:
            logger.error(f"Error getting recent CVEs: {e}")
            return []
    
    def search_cves_by_keyword(self, keyword: str, limit: int = 20) -> List[Dict]:
        """Search CVEs by keyword (product, vendor, type)"""
        try:
            # Search NVD
            url = f"https://services.nvd.nist.gov/rest/json/cves/2.0"
            params = {
                'keywordSearch': keyword
            }
            headers = {}
            if self.nvd_api_key:
                headers['apiKey'] = self.nvd_api_key
            
            # Rate limiting
            time_since_last = time.time() - self.last_nvd_request
            if time_since_last < self.nvd_rate_limit:
                time.sleep(self.nvd_rate_limit - time_since_last)
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            self.last_nvd_request = time.time()
            
            results = []
            for vuln in data.get('vulnerabilities', [])[:limit]:
                cve = vuln.get('cve', {})
                cve_data = {
                    'cve_id': cve.get('id', ''),
                    'description': cve.get('descriptions', [{}])[0].get('value', ''),
                    'published': cve.get('published', ''),
                    'cvss_score': None,
                    'severity': 'UNKNOWN'
                }
                
                # Get CVSS score
                metrics = cve.get('metrics', {})
                if 'cvssMetricV31' in metrics:
                    cvss = metrics['cvssMetricV31'][0].get('cvssData', {})
                    cve_data['cvss_score'] = cvss.get('baseScore')
                    cve_data['severity'] = self._score_to_severity(cve_data['cvss_score'])
                elif 'cvssMetricV2' in metrics:
                    cvss = metrics['cvssMetricV2'][0].get('cvssData', {})
                    cve_data['cvss_score'] = cvss.get('baseScore')
                    cve_data['severity'] = self._score_to_severity(cve_data['cvss_score'])
                
                results.append(cve_data)
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching CVEs by keyword: {e}")
            return []
    
    def _score_to_severity(self, score: Optional[float]) -> str:
        """Convert CVSS score to severity string"""
        if score is None:
            return 'UNKNOWN'
        if score >= 9.0:
            return 'CRITICAL'
        elif score >= 7.0:
            return 'HIGH'
        elif score >= 4.0:
            return 'MEDIUM'
        elif score >= 0.1:
            return 'LOW'
        else:
            return 'NONE'


# Global CVE intelligence instance
_cve_instance = None

def get_cve_intelligence(workspace_root: Optional[str] = None) -> CVEIntelligence:
    """Get or create global CVE intelligence instance"""
    global _cve_instance
    if _cve_instance is None:
        _cve_instance = CVEIntelligence(workspace_root)
    return _cve_instance
