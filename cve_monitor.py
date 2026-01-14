# -*- coding: utf-8 -*-
"""
CVE Monitor - Real-time CVE monitoring
Monitors RSS feeds, API polling, and GitHub for new CVEs
"""

import os
import json
import logging
import time
import asyncio
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
from datetime import datetime, timedelta
import requests

logger = logging.getLogger(__name__)

# Try to import feedparser
try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False
    logger.warning("feedparser not available - RSS monitoring limited")


class CVEMonitor:
    """Real-time CVE monitoring from multiple sources"""
    
    def __init__(self, workspace_root: Optional[str] = None, cve_intelligence=None):
        """
        Initialize CVE Monitor
        workspace_root: Workspace directory for monitoring data
        cve_intelligence: CVEIntelligence instance
        """
        self.workspace_root = Path(workspace_root) if workspace_root else Path(os.getcwd())
        self.monitor_dir = self.workspace_root / "cve_monitoring"
        self.monitor_dir.mkdir(exist_ok=True)
        
        self.cve_intelligence = cve_intelligence
        
        # Monitoring state
        self.last_check = {}
        self.new_cves: List[Dict] = []
        self.alert_callbacks: List[Callable] = []
        
        # RSS feeds
        self.rss_feeds = [
            {
                'name': 'NVD',
                'url': 'https://nvd.nist.gov/feeds/xml/cve/misc/nvd-rss-analyzed.xml',
                'enabled': True
            },
            {
                'name': 'CVE Trends',
                'url': 'https://cvetrends.com/api/cves/24hrs',
                'enabled': True
            }
        ]
        
        # Monitoring settings
        self.check_interval = 3600  # Check every hour
        self.alert_on_severity = ['CRITICAL', 'HIGH']  # Alert on these severities
    
    def check_rss_feeds(self) -> List[Dict]:
        """Check RSS feeds for new CVEs"""
        new_cves = []
        
        if not FEEDPARSER_AVAILABLE:
            logger.warning("feedparser not available, skipping RSS feeds")
            return new_cves
        
        for feed_config in self.rss_feeds:
            if not feed_config.get('enabled'):
                continue
            
            try:
                feed_url = feed_config['url']
                feed_name = feed_config['name']
                
                # Parse feed
                feed = feedparser.parse(feed_url)
                
                if feed.bozo:
                    logger.warning(f"Error parsing {feed_name} feed: {feed.bozo_exception}")
                    continue
                
                # Process entries
                for entry in feed.entries[:20]:  # Limit to 20 entries
                    cve_id = self._extract_cve_id(entry.title or entry.summary or '')
                    if cve_id:
                        cve_data = {
                            'cve_id': cve_id,
                            'title': entry.title,
                            'summary': entry.summary,
                            'link': entry.link,
                            'published': entry.get('published', ''),
                            'source': feed_name,
                            'timestamp': datetime.now().isoformat()
                        }
                        
                        # Check if already seen
                        if not self._is_known_cve(cve_id):
                            new_cves.append(cve_data)
                            self._mark_cve_seen(cve_id)
            
            except Exception as e:
                logger.error(f"Error checking {feed_config['name']} feed: {e}")
        
        return new_cves
    
    def _extract_cve_id(self, text: str) -> Optional[str]:
        """Extract CVE ID from text"""
        cve_pattern = r'CVE-\d{4}-\d{4,}'
        match = re.search(cve_pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).upper()
        return None
    
    def _is_known_cve(self, cve_id: str) -> bool:
        """Check if CVE has been seen before"""
        seen_file = self.monitor_dir / "seen_cves.json"
        if not seen_file.exists():
            return False
        
        try:
            with open(seen_file, 'r') as f:
                seen_cves = json.load(f)
                return cve_id in seen_cves
        except Exception:
            return False
    
    def _mark_cve_seen(self, cve_id: str):
        """Mark CVE as seen"""
        seen_file = self.monitor_dir / "seen_cves.json"
        seen_cves = {}
        
        if seen_file.exists():
            try:
                with open(seen_file, 'r') as f:
                    seen_cves = json.load(f)
            except Exception:
                pass
        
        seen_cves[cve_id] = datetime.now().isoformat()
        
        try:
            with open(seen_file, 'w') as f:
                json.dump(seen_cves, f, indent=2)
        except Exception as e:
            logger.warning(f"Error marking CVE as seen: {e}")
    
    def check_trending_cves(self) -> List[Dict]:
        """Check for trending CVEs"""
        trending = []
        
        if self.cve_intelligence:
            try:
                trending = self.cve_intelligence.get_trending_cves(limit=10)
            except Exception as e:
                logger.error(f"Error getting trending CVEs: {e}")
        
        return trending
    
    def monitor_new_cves(self) -> List[Dict]:
        """Monitor for new CVEs from all sources"""
        all_new_cves = []
        
        # Check RSS feeds
        rss_cves = self.check_rss_feeds()
        all_new_cves.extend(rss_cves)
        
        # Check trending
        trending_cves = self.check_trending_cves()
        for cve in trending_cves:
            cve_id = cve.get('cve_id', '')
            if cve_id and not self._is_known_cve(cve_id):
                all_new_cves.append({
                    'cve_id': cve_id,
                    'description': cve.get('description', ''),
                    'severity': cve.get('severity', 'UNKNOWN'),
                    'exploit_available': cve.get('exploit_available', False),
                    'source': 'Trending',
                    'timestamp': datetime.now().isoformat()
                })
                self._mark_cve_seen(cve_id)
        
        # Remove duplicates
        seen_ids = set()
        unique_cves = []
        for cve in all_new_cves:
            cve_id = cve.get('cve_id', '')
            if cve_id and cve_id not in seen_ids:
                seen_ids.add(cve_id)
                unique_cves.append(cve)
        
        return unique_cves
    
    def get_new_cves_since_last_check(self) -> List[Dict]:
        """Get new CVEs since last check (for learning system)"""
        return self.monitor_new_cves()
    
    def check_high_severity_cves(self, cves: List[Dict]) -> List[Dict]:
        """Filter high-severity CVEs"""
        high_severity = []
        
        for cve in cves:
            severity = cve.get('severity', 'UNKNOWN')
            if severity in self.alert_on_severity:
                high_severity.append(cve)
        
        return high_severity
    
    def check_exploitable_cves(self, cves: List[Dict]) -> List[Dict]:
        """Filter CVEs with available exploits"""
        exploitable = []
        
        for cve in cves:
            if cve.get('exploit_available') or cve.get('exploit_count', 0) > 0:
                exploitable.append(cve)
        
        return exploitable
    
    def register_alert_callback(self, callback: Callable):
        """Register callback for CVE alerts"""
        self.alert_callbacks.append(callback)
    
    def trigger_alerts(self, cves: List[Dict]):
        """Trigger alerts for new CVEs"""
        for callback in self.alert_callbacks:
            try:
                callback(cves)
            except Exception as e:
                logger.error(f"Error in alert callback: {e}")
    
    def generate_alert_message(self, cves: List[Dict]) -> str:
        """Generate alert message for new CVEs"""
        if not cves:
            return ""
        
        lines = []
        lines.append("🚨 NEW CVE ALERT 🚨")
        lines.append("=" * 60)
        lines.append(f"Found {len(cves)} new CVE(s)")
        lines.append("")
        
        for cve in cves[:10]:  # Limit to 10
            cve_id = cve.get('cve_id', 'UNKNOWN')
            severity = cve.get('severity', 'UNKNOWN')
            exploit = "⚠️ EXPLOIT AVAILABLE" if cve.get('exploit_available') else ""
            
            lines.append(f"  • {cve_id} - {severity} {exploit}")
            if cve.get('description'):
                desc = cve['description'][:100]
                lines.append(f"    {desc}...")
        
        lines.append("")
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    async def start_monitoring(self, interval: int = 3600):
        """Start continuous monitoring (async)"""
        logger.info(f"Starting CVE monitoring (checking every {interval} seconds)")
        
        while True:
            try:
                # Check for new CVEs
                new_cves = self.monitor_new_cves()
                
                if new_cves:
                    logger.info(f"Found {len(new_cves)} new CVEs")
                    
                    # Filter high-severity
                    high_severity = self.check_high_severity_cves(new_cves)
                    if high_severity:
                        logger.warning(f"Found {len(high_severity)} high-severity CVEs")
                        self.trigger_alerts(high_severity)
                    
                    # Filter exploitable
                    exploitable = self.check_exploitable_cves(new_cves)
                    if exploitable:
                        logger.warning(f"Found {len(exploitable)} exploitable CVEs")
                        self.trigger_alerts(exploitable)
                
                # Wait for next check
                await asyncio.sleep(interval)
            
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retry


# Global CVE monitor instance
_monitor_instance = None

def get_cve_monitor(workspace_root: Optional[str] = None, cve_intelligence=None) -> CVEMonitor:
    """Get or create global CVE monitor instance"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = CVEMonitor(workspace_root, cve_intelligence)
    return _monitor_instance
