# -*- coding: utf-8 -*-
"""
CVE Learning System - Daily CVE monitoring, learning, and knowledge base
Learns from daily CVE updates and answers questions about recent CVEs
"""

import os
import json
import logging
import asyncio
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CVELearningSystem:
    """CVE learning system that monitors, learns, and answers questions about CVEs"""
    
    def __init__(self, cve_intelligence=None, cve_monitor=None, workspace_root: Optional[str] = None):
        """
        Initialize CVE Learning System
        cve_intelligence: CVEIntelligence instance
        cve_monitor: CVEMonitor instance
        workspace_root: Workspace directory for knowledge base
        """
        self.cve_intelligence = cve_intelligence
        self.cve_monitor = cve_monitor
        self.workspace_root = Path(workspace_root) if workspace_root else Path(os.getcwd())
        self.knowledge_base_dir = self.workspace_root / "cve_knowledge_base"
        self.knowledge_base_dir.mkdir(exist_ok=True)
        
        self.knowledge_base = {}
        self.recent_cves_cache = []
        self.patterns_cache = {}
        self.last_learning_cycle = None
        
        # Load existing knowledge base
        self._load_knowledge_base()
    
    def _load_knowledge_base(self):
        """Load knowledge base from disk"""
        kb_file = self.knowledge_base_dir / "knowledge_base.json"
        if kb_file.exists():
            try:
                with open(kb_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.knowledge_base = data.get('knowledge', {})
                    self.recent_cves_cache = data.get('recent_cves', [])
                    self.patterns_cache = data.get('patterns', {})
                    self.last_learning_cycle = data.get('last_learning_cycle')
                logger.info(f"Loaded CVE knowledge base: {len(self.recent_cves_cache)} recent CVEs")
            except Exception as e:
                logger.warning(f"Error loading knowledge base: {e}")
    
    def _save_knowledge_base(self):
        """Save knowledge base to disk"""
        kb_file = self.knowledge_base_dir / "knowledge_base.json"
        try:
            data = {
                'knowledge': self.knowledge_base,
                'recent_cves': self.recent_cves_cache[-1000:],  # Keep last 1000
                'patterns': self.patterns_cache,
                'last_learning_cycle': self.last_learning_cycle
            }
            with open(kb_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            logger.error(f"Error saving knowledge base: {e}")
    
    async def daily_learning_cycle(self):
        """Daily cycle to learn from new CVEs"""
        try:
            logger.info("Starting daily CVE learning cycle...")
            
            # Fetch new CVEs since last check
            new_cves = await self._get_new_cves_since_last_check()
            
            if new_cves:
                logger.info(f"Found {len(new_cves)} new CVEs to learn from")
                
                # Analyze patterns
                patterns = self.analyze_cve_patterns(new_cves)
                
                # Update knowledge base
                self.update_knowledge_base(new_cves, patterns)
                
                # Update recent CVEs cache
                self.recent_cves_cache.extend(new_cves)
                # Keep only recent 1000
                self.recent_cves_cache = self.recent_cves_cache[-1000:]
                
                # Save knowledge base
                self._save_knowledge_base()
                
                self.last_learning_cycle = datetime.now().isoformat()
                logger.info(f"Learning cycle completed: {len(new_cves)} CVEs learned")
            else:
                logger.info("No new CVEs to learn from")
                
        except Exception as e:
            logger.error(f"Error in daily learning cycle: {e}", exc_info=True)
    
    async def _get_new_cves_since_last_check(self) -> List[Dict]:
        """Get new CVEs since last check"""
        new_cves = []
        
        try:
            # Get recent CVEs from CVE intelligence
            if self.cve_intelligence:
                # Get CVEs from last 7 days
                recent_cves = self.cve_intelligence.get_trending_cves(limit=100)
                new_cves.extend(recent_cves)
            
            # Get new CVEs from monitor
            if self.cve_monitor:
                monitor_cves = self.cve_monitor.get_new_cves_since_last_check()
                new_cves.extend(monitor_cves)
            
            # Remove duplicates by CVE ID
            seen = set()
            unique_cves = []
            for cve in new_cves:
                cve_id = cve.get('cve_id') or cve.get('id') or cve.get('cve')
                if cve_id and cve_id not in seen:
                    seen.add(cve_id)
                    unique_cves.append(cve)
            
            return unique_cves
            
        except Exception as e:
            logger.error(f"Error getting new CVEs: {e}")
            return []
    
    def analyze_cve_patterns(self, cves: List[Dict]) -> Dict:
        """Analyze patterns in CVEs"""
        patterns = {
            'product_trends': {},
            'severity_distribution': {},
            'vulnerability_types': {},
            'exploit_availability': {},
            'affected_versions': {},
            'common_weaknesses': {},
        }
        
        try:
            for cve in cves:
                cve_id = cve.get('cve_id') or cve.get('id') or cve.get('cve', '')
                
                # Product trends
                products = cve.get('affected_products', []) or cve.get('products', [])
                for product in products:
                    patterns['product_trends'][product] = patterns['product_trends'].get(product, 0) + 1
                
                # Severity distribution
                severity = cve.get('severity') or cve.get('cvss_score') or 'UNKNOWN'
                if isinstance(severity, (int, float)):
                    if severity >= 9.0:
                        severity = 'CRITICAL'
                    elif severity >= 7.0:
                        severity = 'HIGH'
                    elif severity >= 4.0:
                        severity = 'MEDIUM'
                    else:
                        severity = 'LOW'
                patterns['severity_distribution'][severity] = patterns['severity_distribution'].get(severity, 0) + 1
                
                # Vulnerability types
                vuln_type = cve.get('vulnerability_type') or cve.get('type') or 'UNKNOWN'
                patterns['vulnerability_types'][vuln_type] = patterns['vulnerability_types'].get(vuln_type, 0) + 1
                
                # Exploit availability
                has_exploit = cve.get('exploit_available', False) or cve.get('has_exploit', False)
                patterns['exploit_availability'][has_exploit] = patterns['exploit_availability'].get(has_exploit, 0) + 1
                
                # Common weaknesses (CWE)
                cwe = cve.get('cwe') or cve.get('weakness')
                if cwe:
                    patterns['common_weaknesses'][cwe] = patterns['common_weaknesses'].get(cwe, 0) + 1
            
            # Store patterns
            self.patterns_cache.update(patterns)
            
        except Exception as e:
            logger.error(f"Error analyzing CVE patterns: {e}")
        
        return patterns
    
    def update_knowledge_base(self, new_cves: List[Dict], patterns: Dict):
        """Update knowledge base with new CVEs and patterns"""
        try:
            # Update by product
            for cve in new_cves:
                products = cve.get('affected_products', []) or cve.get('products', [])
                for product in products:
                    if product not in self.knowledge_base:
                        self.knowledge_base[product] = {
                            'cves': [],
                            'last_updated': datetime.now().isoformat()
                        }
                    self.knowledge_base[product]['cves'].append(cve)
                    self.knowledge_base[product]['last_updated'] = datetime.now().isoformat()
            
            # Update patterns
            for pattern_type, pattern_data in patterns.items():
                if pattern_type not in self.knowledge_base:
                    self.knowledge_base[pattern_type] = {}
                self.knowledge_base[pattern_type].update(pattern_data)
            
        except Exception as e:
            logger.error(f"Error updating knowledge base: {e}")
    
    def get_recent_cves(self, days: int = 7, limit: int = 50) -> List[Dict]:
        """Get recent CVEs from last N days"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            recent = []
            for cve in self.recent_cves_cache:
                cve_date_str = cve.get('published') or cve.get('date') or cve.get('timestamp')
                if cve_date_str:
                    try:
                        if isinstance(cve_date_str, str):
                            cve_date = datetime.fromisoformat(cve_date_str.replace('Z', '+00:00'))
                        else:
                            cve_date = cve_date_str
                        
                        if cve_date >= cutoff_date:
                            recent.append(cve)
                    except:
                        # If date parsing fails, include it anyway
                        recent.append(cve)
                else:
                    # If no date, include it
                    recent.append(cve)
            
            return recent[:limit]
            
        except Exception as e:
            logger.error(f"Error getting recent CVEs: {e}")
            return []
    
    def search_cves_by_keyword(self, keyword: str, limit: int = 20) -> List[Dict]:
        """Search CVEs by keyword"""
        results = []
        keyword_lower = keyword.lower()
        
        try:
            for cve in self.recent_cves_cache:
                # Search in various fields
                cve_id = (cve.get('cve_id') or cve.get('id') or cve.get('cve', '')).lower()
                description = (cve.get('description') or cve.get('summary') or '').lower()
                products = [p.lower() for p in (cve.get('affected_products', []) or cve.get('products', []))]
                
                if (keyword_lower in cve_id or 
                    keyword_lower in description or 
                    any(keyword_lower in p for p in products)):
                    results.append(cve)
            
            return results[:limit]
            
        except Exception as e:
            logger.error(f"Error searching CVEs: {e}")
            return []
    
    def get_cve_trends(self) -> Dict:
        """Get trending CVEs and patterns"""
        trends = {
            'top_products': [],
            'top_severities': [],
            'top_vulnerability_types': [],
            'exploit_trends': {},
            'recent_high_severity': [],
        }
        
        try:
            # Top products
            if 'product_trends' in self.patterns_cache:
                product_trends = self.patterns_cache['product_trends']
                trends['top_products'] = sorted(
                    product_trends.items(), 
                    key=lambda x: x[1], 
                    reverse=True
                )[:10]
            
            # Top severities
            if 'severity_distribution' in self.patterns_cache:
                severity_dist = self.patterns_cache['severity_distribution']
                trends['top_severities'] = sorted(
                    severity_dist.items(),
                    key=lambda x: x[1],
                    reverse=True
                )
            
            # Recent high severity CVEs
            recent = self.get_recent_cves(days=7, limit=100)
            for cve in recent:
                severity = cve.get('severity') or cve.get('cvss_score', 0)
                if isinstance(severity, (int, float)) and severity >= 7.0:
                    trends['recent_high_severity'].append(cve)
                elif isinstance(severity, str) and severity.upper() in ['HIGH', 'CRITICAL']:
                    trends['recent_high_severity'].append(cve)
            
            trends['recent_high_severity'] = trends['recent_high_severity'][:20]
            
        except Exception as e:
            logger.error(f"Error getting CVE trends: {e}")
        
        return trends
    
    def answer_cve_question(self, question: str, brain=None) -> str:
        """Answer questions about CVEs using learned knowledge"""
        try:
            question_lower = question.lower()
            
            # Get relevant CVEs based on question
            recent_cves = self.get_recent_cves(days=30, limit=50)
            trends = self.get_cve_trends()
            
            # Build context for AI
            context = f"""
CVE KNOWLEDGE BASE CONTEXT:

Recent CVEs (last 30 days): {len(recent_cves)} CVEs
High Severity Recent CVEs: {len(trends.get('recent_high_severity', []))}

Top Affected Products:
{chr(10).join([f"- {prod}: {count} CVEs" for prod, count in trends.get('top_products', [])[:10]])}

Severity Distribution:
{chr(10).join([f"- {sev}: {count}" for sev, count in trends.get('top_severities', [])])}

Recent High Severity CVEs:
{chr(10).join([f"- {cve.get('cve_id', 'N/A')}: {cve.get('description', 'N/A')[:100]}" for cve in trends.get('recent_high_severity', [])[:10]])}

Question: {question}
"""
            
            # If brain available, use AI to answer
            if brain:
                answer_prompt = f"""
Based on the CVE knowledge base context above, answer this question about CVEs:
{question}

Provide a comprehensive answer using the recent CVE data and trends.
"""
                answer = ""
                for chunk in brain.chat(answer_prompt):
                    answer += chunk
                return answer
            else:
                # Fallback: return structured information
                if 'recent' in question_lower or 'latest' in question_lower or 'new' in question_lower:
                    recent = self.get_recent_cves(days=7, limit=10)
                    answer = f"Recent CVEs (last 7 days):\n\n"
                    for cve in recent:
                        cve_id = cve.get('cve_id') or cve.get('id', 'N/A')
                        severity = cve.get('severity') or cve.get('cvss_score', 'N/A')
                        desc = (cve.get('description') or cve.get('summary', 'N/A'))[:200]
                        answer += f"- {cve_id} (Severity: {severity})\n  {desc}\n\n"
                    return answer
                else:
                    return "CVE information available. Please ask a specific question about recent CVEs."
                    
        except Exception as e:
            logger.error(f"Error answering CVE question: {e}")
            return f"Error answering CVE question: {str(e)}"


def get_cve_learning_system(cve_intelligence=None, cve_monitor=None, workspace_root: Optional[str] = None) -> CVELearningSystem:
    """Get or create global CVE learning system instance"""
    global _cve_learning_instance
    if '_cve_learning_instance' not in globals():
        _cve_learning_instance = None
    
    if _cve_learning_instance is None:
        _cve_learning_instance = CVELearningSystem(cve_intelligence, cve_monitor, workspace_root)
    
    return _cve_learning_instance
