# -*- coding: utf-8 -*-
"""
Threat Intelligence - Real-time threat intelligence feeds
Integrates AlienVault OTX, GreyNoise, CISA KEV, and other threat intelligence sources
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
import requests
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ThreatIntelligence:
    """Comprehensive threat intelligence from multiple sources"""
    
    def __init__(self, workspace_root: Optional[str] = None):
        """
        Initialize Threat Intelligence
        workspace_root: Workspace directory for caching
        """
        self.workspace_root = Path(workspace_root) if workspace_root else Path(os.getcwd())
        self.cache_dir = self.workspace_root / "threat_cache"
        self.cache_dir.mkdir(exist_ok=True)
        
        # API keys
        self.otx_api_key = os.getenv('ALIENVAULT_OTX_API_KEY')  # Optional
        self.greynoise_api_key = os.getenv('GREYNOISE_API_KEY')  # Optional but recommended
        
        # Cache settings
        self.cache_duration = timedelta(hours=6)  # Cache threat intel for 6 hours
    
    def check_cisa_kev(self, cve_id: str) -> Dict:
        """Check if CVE is in CISA KEV (Known Exploited Vulnerabilities) Catalog"""
        cache_file = self.cache_dir / f"cisa_kev_{cve_id}.json"
        
        # Check cache
        if cache_file.exists():
            cache_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if cache_age < self.cache_duration:
                try:
                    with open(cache_file, 'r') as f:
                        return json.load(f)
                except Exception as e:
                    logger.warning(f"Error reading CISA KEV cache: {e}")
        
        try:
            # Download CISA KEV catalog
            url = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            result = {
                'cve_id': cve_id,
                'in_kev': False,
                'date_added': None,
                'vulnerability_name': None,
                'required_action': None,
                'due_date': None,
                'source': 'CISA KEV'
            }
            
            # Search for CVE in catalog
            for vuln in data.get('vulnerabilities', []):
                if vuln.get('cveID', '').upper() == cve_id.upper():
                    result.update({
                        'in_kev': True,
                        'date_added': vuln.get('dateAdded', ''),
                        'vulnerability_name': vuln.get('vulnerabilityName', ''),
                        'required_action': vuln.get('requiredAction', ''),
                        'due_date': vuln.get('dueDate', ''),
                        'notes': vuln.get('notes', '')
                    })
                    break
            
            # Cache result
            try:
                with open(cache_file, 'w') as f:
                    json.dump(result, f, indent=2)
            except Exception as e:
                logger.warning(f"Error caching CISA KEV: {e}")
            
            return result
        
        except Exception as e:
            logger.error(f"Error checking CISA KEV: {e}")
            return {'cve_id': cve_id, 'in_kev': False, 'error': str(e), 'source': 'CISA KEV'}
    
    def check_greynoise(self, ip: Optional[str] = None, cve_id: Optional[str] = None) -> Dict:
        """Check GreyNoise for active exploitation"""
        if not self.greynoise_api_key:
            return {'error': 'GreyNoise API key not configured'}
        
        try:
            if ip:
                # Check IP in GreyNoise
                url = f"https://api.greynoise.io/v2/noise/context/{ip}"
                headers = {
                    'key': self.greynoise_api_key,
                    'Accept': 'application/json'
                }
                
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                return {
                    'ip': ip,
                    'classification': data.get('classification', 'unknown'),
                    'actor': data.get('actor', ''),
                    'tags': data.get('tags', []),
                    'cve': data.get('cve', []),
                    'source': 'GreyNoise'
                }
            
            elif cve_id:
                # Search for CVE in GreyNoise
                url = "https://api.greynoise.io/v2/experimental/gnql"
                headers = {
                    'key': self.greynoise_api_key,
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                }
                params = {
                    'query': f'cve:{cve_id}',
                    'size': 10
                }
                
                response = requests.get(url, headers=headers, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                return {
                    'cve_id': cve_id,
                    'active_exploitation': data.get('count', 0) > 0,
                    'exploitation_count': data.get('count', 0),
                    'data': data.get('data', []),
                    'source': 'GreyNoise'
                }
        
        except Exception as e:
            logger.error(f"Error checking GreyNoise: {e}")
            return {'error': str(e), 'source': 'GreyNoise'}
    
    def check_otx(self, cve_id: str) -> Dict:
        """Check AlienVault OTX for threat intelligence"""
        try:
            url = f"https://otx.alienvault.com/api/v1/pulses/subscribed"
            headers = {
                'X-OTX-API-KEY': self.otx_api_key or ''
            }
            
            # Search for CVE in pulses
            search_url = f"https://otx.alienvault.com/api/v1/search"
            params = {
                'q': cve_id,
                'limit': 10
            }
            
            response = requests.get(search_url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            result = {
                'cve_id': cve_id,
                'pulses_found': len(data.get('results', [])),
                'pulses': [],
                'source': 'AlienVault OTX'
            }
            
            for pulse in data.get('results', [])[:5]:
                result['pulses'].append({
                    'id': pulse.get('id', ''),
                    'name': pulse.get('name', ''),
                    'description': pulse.get('description', ''),
                    'created': pulse.get('created', ''),
                    'modified': pulse.get('modified', ''),
                    'author': pulse.get('author_name', ''),
                    'indicators_count': pulse.get('indicator_count', 0)
                })
            
            return result
        
        except Exception as e:
            logger.error(f"Error checking OTX: {e}")
            return {'cve_id': cve_id, 'error': str(e), 'source': 'AlienVault OTX'}
    
    def get_active_exploitation_status(self, cve_id: str) -> Dict:
        """Get comprehensive active exploitation status for a CVE"""
        result = {
            'cve_id': cve_id,
            'actively_exploited': False,
            'sources': {},
            'confidence': 'low'
        }
        
        # Check CISA KEV (highest confidence)
        cisa_result = self.check_cisa_kev(cve_id)
        result['sources']['cisa'] = cisa_result
        if cisa_result.get('in_kev'):
            result['actively_exploited'] = True
            result['confidence'] = 'high'
        
        # Check GreyNoise
        greynoise_result = self.check_greynoise(cve_id=cve_id)
        result['sources']['greynoise'] = greynoise_result
        if greynoise_result.get('active_exploitation'):
            result['actively_exploited'] = True
            if result['confidence'] == 'low':
                result['confidence'] = 'medium'
        
        # Check OTX
        otx_result = self.check_otx(cve_id)
        result['sources']['otx'] = otx_result
        if otx_result.get('pulses_found', 0) > 0:
            if not result['actively_exploited']:
                result['confidence'] = 'medium'
        
        return result
    
    def get_threat_actors(self, cve_id: str) -> List[str]:
        """Get threat actors associated with a CVE"""
        actors = []
        
        # Check OTX pulses
        otx_result = self.check_otx(cve_id)
        for pulse in otx_result.get('pulses', []):
            author = pulse.get('author', '')
            if author:
                actors.append(author)
        
        # Check GreyNoise
        greynoise_result = self.check_greynoise(cve_id=cve_id)
        if greynoise_result.get('data'):
            for item in greynoise_result['data']:
                actor = item.get('actor', '')
                if actor and actor not in actors:
                    actors.append(actor)
        
        return list(set(actors))  # Remove duplicates
    
    def get_exploitation_indicators(self, cve_id: str) -> Dict:
        """Get indicators of compromise and exploitation for a CVE"""
        result = {
            'cve_id': cve_id,
            'indicators': [],
            'ips': [],
            'domains': [],
            'hashes': []
        }
        
        # Get OTX pulses
        otx_result = self.check_otx(cve_id)
        for pulse in otx_result.get('pulses', []):
            pulse_id = pulse.get('id', '')
            if pulse_id:
                try:
                    # Get pulse details
                    url = f"https://otx.alienvault.com/api/v1/pulses/{pulse_id}"
                    headers = {
                        'X-OTX-API-KEY': self.otx_api_key or ''
                    }
                    response = requests.get(url, headers=headers, timeout=10)
                    if response.status_code == 200:
                        pulse_data = response.json()
                        for indicator in pulse_data.get('indicators', []):
                            indicator_type = indicator.get('type', '')
                            indicator_value = indicator.get('indicator', '')
                            
                            if indicator_type == 'IPv4':
                                result['ips'].append(indicator_value)
                            elif indicator_type in ['domain', 'hostname']:
                                result['domains'].append(indicator_value)
                            elif indicator_type in ['FileHash-MD5', 'FileHash-SHA1', 'FileHash-SHA256']:
                                result['hashes'].append(indicator_value)
                            
                            result['indicators'].append({
                                'type': indicator_type,
                                'value': indicator_value,
                                'title': indicator.get('title', '')
                            })
                except Exception as e:
                    logger.debug(f"Error getting pulse details: {e}")
        
        return result


# Global threat intelligence instance
_threat_instance = None

def get_threat_intelligence(workspace_root: Optional[str] = None) -> ThreatIntelligence:
    """Get or create global threat intelligence instance"""
    global _threat_instance
    if _threat_instance is None:
        _threat_instance = ThreatIntelligence(workspace_root)
    return _threat_instance
