# -*- coding: utf-8 -*-
"""
Eden AI Integration Handler
Provides current information fetching capabilities for DeepSeek
Eden AI acts as a tool layer for fetching current/recent code, search results, and data
DeepSeek remains the reasoning/agent layer

API Documentation: https://docs.edenai.co/
- Currently using V2 API (supported until end of 2026)
- V3 API available at /v3/universal-ai with different structure
- No Python SDK required - uses direct HTTP API calls
"""

import os
import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime
import json

logger = logging.getLogger(__name__)

try:
    from edenai import EdenAI
    EDEN_AI_SDK_AVAILABLE = True
except ImportError:
    EDEN_AI_SDK_AVAILABLE = False
    logger.warning("Eden AI SDK not available. Install with: pip install edenai")


class EdenAIHandler:
    """
    Eden AI Handler - Provides current information fetching for DeepSeek
    DeepSeek uses this as a tool to get current/recent information beyond its knowledge cutoff
    """
    
    def __init__(self):
        """Initialize Eden AI handler with API key"""
        self.api_key = os.getenv('EDEN_AI_API_KEY')
        # Use V2 API (still supported until end of 2026)
        # V3 API uses different structure: /v3/universal-ai
        # See: https://docs.edenai.co/
        self.base_url = "https://api.edenai.run/v2"
        self.api_version = "v2"  # Can be upgraded to "v3" later
        
        if not self.api_key:
            logger.warning("Eden AI API key not found. Set EDEN_AI_API_KEY environment variable.")
            self.available = False
        else:
            self.available = True
            if EDEN_AI_SDK_AVAILABLE:
                try:
                    self.client = EdenAI(api_key=self.api_key)
                    logger.info("Eden AI SDK initialized successfully")
                except Exception as e:
                    logger.warning(f"Failed to initialize Eden AI SDK: {e}. Using direct API calls.")
                    self.client = None
            else:
                self.client = None
                logger.info("Eden AI will use direct API calls (SDK not installed)")
    
    def is_available(self) -> bool:
        """Check if Eden AI is available"""
        return self.available and self.api_key is not None
    
    async def search_web(self, query: str, num_results: int = 5, providers: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Search the web for current information
        
        Args:
            query: Search query
            num_results: Number of results to return
            providers: List of providers to use (default: ['google', 'bing'])
        
        Returns:
            List of search results with title, snippet, url, date
        """
        if not self.is_available():
            logger.warning("Eden AI not available - no API key configured")
            return []
        
        if providers is None:
            providers = ['google', 'bing']
        
        try:
            url = f"{self.base_url}/text/search"
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'text': query,
                'providers': ','.join(providers),
                'num_results': num_results,
                'language': 'en'
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            results = []
            # Parse results from different providers
            for provider in providers:
                if provider in data:
                    provider_data = data[provider]
                    if 'items' in provider_data:
                        for item in provider_data['items'][:num_results]:
                            results.append({
                                'title': item.get('title', ''),
                                'snippet': item.get('snippet', ''),
                                'url': item.get('link', ''),
                                'date': item.get('date', ''),
                                'provider': provider
                            })
            
            # Remove duplicates based on URL
            seen_urls = set()
            unique_results = []
            for result in results:
                if result['url'] not in seen_urls:
                    seen_urls.add(result['url'])
                    unique_results.append(result)
            
            return unique_results[:num_results]
            
        except Exception as e:
            logger.error(f"Error performing Eden AI web search: {e}")
            return []
    
    async def search_code(self, query: str, language: Optional[str] = None, num_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search for recent code examples and implementations
        
        Args:
            query: Code search query (e.g., "Python async HTTP client", "React hooks example")
            language: Programming language filter (optional)
            num_results: Number of results to return
        
        Returns:
            List of code search results with code snippets, source, url
        """
        if not self.is_available():
            logger.warning("Eden AI not available - no API key configured")
            return []
        
        try:
            # Use web search with code-specific query
            code_query = f"{query} code example"
            if language:
                code_query += f" {language}"
            
            # Search GitHub, Stack Overflow, and code repositories
            search_query = f"{code_query} site:github.com OR site:stackoverflow.com OR site:gist.github.com"
            
            results = await self.search_web(search_query, num_results=num_results * 2)
            
            # Filter and format code results
            code_results = []
            for result in results:
                if any(domain in result.get('url', '') for domain in ['github.com', 'stackoverflow.com', 'gist.github.com']):
                    code_results.append({
                        'title': result.get('title', ''),
                        'snippet': result.get('snippet', ''),
                        'url': result.get('url', ''),
                        'source': 'code_search',
                        'language': language
                    })
                    if len(code_results) >= num_results:
                        break
            
            return code_results
            
        except Exception as e:
            logger.error(f"Error performing Eden AI code search: {e}")
            return []
    
    async def semantic_search(self, query: str, documents: Optional[List[str]] = None, num_results: int = 5) -> List[Dict[str, Any]]:
        """
        Perform semantic search using embeddings
        
        Args:
            query: Search query
            documents: List of documents to search within (optional)
            num_results: Number of results to return
        
        Returns:
            List of semantically relevant results
        """
        if not self.is_available():
            logger.warning("Eden AI not available - no API key configured")
            return []
        
        try:
            url = f"{self.base_url}/text/embeddings"
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            # Get query embedding
            query_payload = {
                'texts': [query],
                'providers': 'openai',
                'language': 'en'
            }
            
            query_response = requests.post(url, json=query_payload, headers=headers, timeout=30)
            query_response.raise_for_status()
            query_data = query_response.json()
            
            if 'openai' not in query_data or 'items' not in query_data['openai']:
                logger.warning("Failed to get query embedding")
                return []
            
            query_embedding = query_data['openai']['items'][0]['embedding']
            
            # If documents provided, search within them
            if documents:
                doc_payload = {
                    'texts': documents,
                    'providers': 'openai',
                    'language': 'en'
                }
                
                doc_response = requests.post(url, json=doc_payload, headers=headers, timeout=30)
                doc_response.raise_for_status()
                doc_data = doc_response.json()
                
                if 'openai' not in doc_data or 'items' not in doc_data['openai']:
                    return []
                
                # Calculate cosine similarity
                try:
                    import numpy as np
                    NUMPY_AVAILABLE = True
                except ImportError:
                    NUMPY_AVAILABLE = False
                    logger.warning("numpy not available for semantic search. Install with: pip install numpy")
                    return await self.search_web(query, num_results=num_results)
                
                if not NUMPY_AVAILABLE:
                    return await self.search_web(query, num_results=num_results)
                
                similarities = []
                for i, doc_embedding in enumerate(doc_data['openai']['items']):
                    similarity = np.dot(query_embedding, doc_embedding['embedding']) / (
                        np.linalg.norm(query_embedding) * np.linalg.norm(doc_embedding['embedding'])
                    )
                    similarities.append((similarity, i))
                
                # Sort by similarity
                similarities.sort(reverse=True, key=lambda x: x[0])
                
                results = []
                for similarity, idx in similarities[:num_results]:
                    results.append({
                        'document': documents[idx],
                        'similarity': float(similarity),
                        'index': idx
                    })
                
                return results
            
            # If no documents, use web search with semantic understanding
            return await self.search_web(query, num_results=num_results)
            
        except Exception as e:
            logger.error(f"Error performing Eden AI semantic search: {e}")
            # Fallback to web search
            return await self.search_web(query, num_results=num_results)
    
    async def get_current_news(self, topic: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """
        Get current news and recent information about a topic
        
        Args:
            topic: Topic to search for
            num_results: Number of results to return
        
        Returns:
            List of news articles with title, snippet, url, date
        """
        if not self.is_available():
            logger.warning("Eden AI not available - no API key configured")
            return []
        
        try:
            # Search for recent news
            news_query = f"{topic} news 2025 2026"
            results = await self.search_web(news_query, num_results=num_results * 2)
            
            # Filter for news sources and recent dates
            news_results = []
            news_domains = ['bbc.com', 'reuters.com', 'cnn.com', 'theguardian.com', 
                          'techcrunch.com', 'arstechnica.com', 'wired.com', 'github.com']
            
            for result in results:
                url = result.get('url', '').lower()
                if any(domain in url for domain in news_domains):
                    news_results.append({
                        'title': result.get('title', ''),
                        'snippet': result.get('snippet', ''),
                        'url': result.get('url', ''),
                        'date': result.get('date', ''),
                        'topic': topic
                    })
                    if len(news_results) >= num_results:
                        break
            
            return news_results
            
        except Exception as e:
            logger.error(f"Error getting current news: {e}")
            return []
    
    async def fetch_recent_code(self, technology: str, framework: Optional[str] = None, num_results: int = 5) -> List[Dict[str, Any]]:
        """
        Fetch recent code examples and implementations for a technology/framework
        
        Args:
            technology: Technology name (e.g., "React", "Python", "FastAPI")
            framework: Specific framework/library (optional)
            num_results: Number of results to return
        
        Returns:
            List of code examples with code snippets, source, url
        """
        if not self.is_available():
            logger.warning("Eden AI not available - no API key configured")
            return []
        
        try:
            query = f"{technology}"
            if framework:
                query += f" {framework}"
            query += " latest code example 2025 2026"
            
            return await self.search_code(query, language=technology.lower(), num_results=num_results)
            
        except Exception as e:
            logger.error(f"Error fetching recent code: {e}")
            return []
    
    async def search_cve(self, cve_id: Optional[str] = None, query: Optional[str] = None, num_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search for CVE (Common Vulnerabilities and Exposures) information
        
        Args:
            cve_id: Specific CVE ID (e.g., "CVE-2024-1234") or None for general search
            query: General vulnerability search query (optional if cve_id provided)
            num_results: Number of results to return
        
        Returns:
            List of CVE information with ID, description, severity, affected versions, patches, CVSS scores
        """
        if not self.is_available():
            logger.warning("Eden AI not available - no API key configured")
            return []
        
        try:
            # Build search query
            if cve_id:
                search_query = f"{cve_id} site:cve.mitre.org OR site:nvd.nist.gov OR site:cvedetails.com"
            elif query:
                search_query = f"{query} CVE vulnerability site:cve.mitre.org OR site:nvd.nist.gov OR site:cvedetails.com"
            else:
                logger.warning("Either cve_id or query must be provided")
                return []
            
            # Search for CVE information
            results = await self.search_web(search_query, num_results=num_results * 2)
            
            # Filter and format CVE results
            cve_results = []
            cve_domains = ['cve.mitre.org', 'nvd.nist.gov', 'cvedetails.com', 'cve.org']
            
            for result in results:
                url = result.get('url', '').lower()
                if any(domain in url for domain in cve_domains):
                    # Extract CVE ID from title or URL
                    cve_id_found = None
                    title = result.get('title', '')
                    url_text = result.get('url', '')
                    
                    # Try to extract CVE ID
                    import re
                    cve_pattern = r'CVE-\d{4}-\d{4,}'
                    cve_match = re.search(cve_pattern, title + ' ' + url_text, re.IGNORECASE)
                    if cve_match:
                        cve_id_found = cve_match.group(0).upper()
                    
                    cve_results.append({
                        'title': result.get('title', ''),
                        'snippet': result.get('snippet', ''),
                        'url': result.get('url', ''),
                        'cve_id': cve_id_found or cve_id,
                        'date': result.get('date', ''),
                        'source': 'cve_search'
                    })
                    if len(cve_results) >= num_results:
                        break
            
            return cve_results
            
        except Exception as e:
            logger.error(f"Error performing Eden AI CVE search: {e}")
            return []
    
    async def search_poc(self, query: str, cve_id: Optional[str] = None, num_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search for current POCs (Proof of Concepts) for vulnerabilities
        
        Args:
            query: Search query (e.g., "SQL injection POC", "XSS exploit")
            cve_id: Optional CVE ID to search for specific POC
            num_results: Number of results to return
        
        Returns:
            List of POC results with code, GitHub repositories, exploit scripts
        """
        if not self.is_available():
            logger.warning("Eden AI not available - no API key configured")
            return []
        
        try:
            # Build POC search query
            if cve_id:
                poc_query = f"{cve_id} POC proof of concept exploit code 2024 2025 2026"
            else:
                poc_query = f"{query} POC proof of concept exploit code 2024 2025 2026"
            
            # Search GitHub, exploit-db, and security research sites
            search_query = f"{poc_query} site:github.com OR site:exploit-db.com OR site:packetstormsecurity.com OR site:seebug.org"
            
            results = await self.search_web(search_query, num_results=num_results * 3)
            
            # Filter and format POC results
            poc_results = []
            poc_domains = ['github.com', 'exploit-db.com', 'packetstormsecurity.com', 'seebug.org', 'gist.github.com']
            
            for result in results:
                url = result.get('url', '').lower()
                if any(domain in url for domain in poc_domains):
                    poc_results.append({
                        'title': result.get('title', ''),
                        'snippet': result.get('snippet', ''),
                        'url': result.get('url', ''),
                        'date': result.get('date', ''),
                        'source': 'poc_search',
                        'cve_id': cve_id
                    })
                    if len(poc_results) >= num_results:
                        break
            
            return poc_results
            
        except Exception as e:
            logger.error(f"Error performing Eden AI POC search: {e}")
            return []
    
    async def search_exploit(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search for exploit code, Metasploit modules, and exploit frameworks
        
        Args:
            query: Search query (e.g., "WordPress exploit", "Metasploit module")
            num_results: Number of results to return
        
        Returns:
            List of exploit information with code, usage instructions, affected systems
        """
        if not self.is_available():
            logger.warning("Eden AI not available - no API key configured")
            return []
        
        try:
            # Build exploit search query
            exploit_query = f"{query} exploit code Metasploit module 2024 2025 2026"
            
            # Search exploit databases and security repos
            search_query = f"{exploit_query} site:exploit-db.com OR site:github.com OR site:rapid7.com OR site:metasploit.com"
            
            results = await self.search_web(search_query, num_results=num_results * 3)
            
            # Filter and format exploit results
            exploit_results = []
            exploit_domains = ['exploit-db.com', 'github.com', 'rapid7.com', 'metasploit.com', 'gist.github.com']
            
            for result in results:
                url = result.get('url', '').lower()
                if any(domain in url for domain in exploit_domains):
                    exploit_results.append({
                        'title': result.get('title', ''),
                        'snippet': result.get('snippet', ''),
                        'url': result.get('url', ''),
                        'date': result.get('date', ''),
                        'source': 'exploit_search'
                    })
                    if len(exploit_results) >= num_results:
                        break
            
            return exploit_results
            
        except Exception as e:
            logger.error(f"Error performing Eden AI exploit search: {e}")
            return []
    
    async def search_hacking_techniques(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search for current hacking techniques, methodologies, and tools
        
        Args:
            query: Search query (e.g., "SQL injection bypass", "XSS techniques")
            num_results: Number of results to return
        
        Returns:
            List of hacking techniques with methods, tool documentation, attack vectors
        """
        if not self.is_available():
            logger.warning("Eden AI not available - no API key configured")
            return []
        
        try:
            # Build hacking techniques search query
            techniques_query = f"{query} hacking technique method bypass attack vector 2024 2025 2026"
            
            # Search security blogs, research papers, tool repositories
            search_query = f"{techniques_query} site:owasp.org OR site:portswigger.net OR site:github.com OR site:hackerone.com OR site:bugcrowd.com"
            
            results = await self.search_web(techniques_query, num_results=num_results * 2)
            
            # Filter and format hacking techniques results
            techniques_results = []
            techniques_domains = ['owasp.org', 'portswigger.net', 'github.com', 'hackerone.com', 
                                 'bugcrowd.com', 'hacktricks.xyz', 'book.hacktricks.xyz']
            
            for result in results:
                url = result.get('url', '').lower()
                if any(domain in url for domain in techniques_domains):
                    techniques_results.append({
                        'title': result.get('title', ''),
                        'snippet': result.get('snippet', ''),
                        'url': result.get('url', ''),
                        'date': result.get('date', ''),
                        'source': 'hacking_techniques_search'
                    })
                    if len(techniques_results) >= num_results:
                        break
            
            return techniques_results
            
        except Exception as e:
            logger.error(f"Error performing Eden AI hacking techniques search: {e}")
            return []
    
    async def search_security_research(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """
        Comprehensive security research search combining CVE, POC, exploit, and hacking techniques
        
        Args:
            query: Security research query
            num_results: Number of results to return
        
        Returns:
            List of aggregated security information from multiple sources
        """
        if not self.is_available():
            logger.warning("Eden AI not available - no API key configured")
            return []
        
        try:
            # Build comprehensive security research query
            research_query = f"{query} security vulnerability exploit CVE POC zero-day 2024 2025 2026"
            
            # Search multiple security sources
            results = await self.search_web(research_query, num_results=num_results * 2)
            
            # Filter for security-related sources
            security_results = []
            security_domains = ['cve.mitre.org', 'nvd.nist.gov', 'exploit-db.com', 'github.com',
                              'owasp.org', 'portswigger.net', 'hackerone.com', 'bugcrowd.com',
                              'securityfocus.com', 'krebsonsecurity.com', 'thehackernews.com']
            
            for result in results:
                url = result.get('url', '').lower()
                if any(domain in url for domain in security_domains):
                    security_results.append({
                        'title': result.get('title', ''),
                        'snippet': result.get('snippet', ''),
                        'url': result.get('url', ''),
                        'date': result.get('date', ''),
                        'source': 'security_research'
                    })
                    if len(security_results) >= num_results:
                        break
            
            return security_results
            
        except Exception as e:
            logger.error(f"Error performing Eden AI security research search: {e}")
            return []
    
    def format_search_results(self, results: List[Dict[str, Any]], result_type: str = "web") -> str:
        """
        Format search results for display to DeepSeek
        
        Args:
            results: List of search results
            result_type: Type of results ("web", "code", "news", "cve", "poc", "exploit", "hacking_techniques", "security_research")
        
        Returns:
            Formatted string for DeepSeek to use
        """
        if not results:
            return f"No {result_type} results found."
        
        # Map result types to display names
        type_display = {
            "cve": "CVE",
            "poc": "POC (Proof of Concept)",
            "exploit": "Exploit",
            "hacking_techniques": "Hacking Techniques",
            "security_research": "Security Research"
        }
        display_name = type_display.get(result_type, result_type.upper())
        
        formatted = f"**Eden AI {display_name} Search Results:**\n\n"
        
        for i, result in enumerate(results, 1):
            formatted += f"{i}. **{result.get('title', 'No title')}**\n"
            
            if result_type == "code":
                formatted += f"   Language: {result.get('language', 'N/A')}\n"
                formatted += f"   Source: {result.get('source', 'N/A')}\n"
            
            if result_type == "cve" and result.get('cve_id'):
                formatted += f"   CVE ID: {result.get('cve_id')}\n"
            
            if result_type == "poc" and result.get('cve_id'):
                formatted += f"   Related CVE: {result.get('cve_id')}\n"
            
            formatted += f"   {result.get('snippet', 'No description')}\n"
            formatted += f"   🔗 {result.get('url', '')}\n"
            
            if result.get('date'):
                formatted += f"   📅 {result.get('date')}\n"
            
            if result.get('similarity'):
                formatted += f"   Relevance: {result.get('similarity', 0):.2%}\n"
            
            formatted += "\n"
        
        formatted += f"\n*Fetched via Eden AI at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"
        
        return formatted
    
    def should_use_eden_ai(self, query: str) -> bool:
        """
        Determine if a query needs Eden AI (current/recent information)
        
        Args:
            query: User query to analyze
        
        Returns:
            True if Eden AI should be used
        """
        if not self.is_available():
            return False
        
        query_lower = query.lower()
        
        # CVE keywords
        cve_keywords = ['cve', 'cve-', 'vulnerability', 'vuln', 'security advisory', 'security patch']
        
        # POC keywords
        poc_keywords = ['poc', 'proof of concept', 'exploit code', 'exploit script', 'github poc']
        
        # Exploit keywords
        exploit_keywords = ['exploit', 'metasploit', 'exploit-db', 'exploit code', 'working exploit']
        
        # Hacking keywords
        hacking_keywords = ['hacking', 'hack', 'bypass', 'technique', 'method', 'attack', 'penetration', 'pentest']
        
        # Security research keywords
        security_research_keywords = ['security research', 'zero-day', '0-day', 'rce', 'sqli', 'xss', 
                                     'lfi', 'rfi', 'ssrf', 'csrf', 'xxe', 'deserialization', 'injection']
        
        # Current code keywords
        current_code_keywords = ['latest code', 'recent implementation', '2025', '2026', 'current', 
                                'latest', 'recent', 'today', 'now', 'new']
        
        # General current info keywords
        current_info_keywords = [
            'news', 'happening', 'update', 'breaking', 'just',
            'what is', 'who is', 'when did', 'where is', 'how is',
            'did', 'has', 'have', 'was', 'were', 'is', 'are',
            'code example', 'implementation', 'how to', 'tutorial',
            'search for', 'find', 'look up', 'get information'
        ]
        
        # Check for security-related keywords
        has_security_keyword = (
            any(keyword in query_lower for keyword in cve_keywords) or
            any(keyword in query_lower for keyword in poc_keywords) or
            any(keyword in query_lower for keyword in exploit_keywords) or
            any(keyword in query_lower for keyword in hacking_keywords) or
            any(keyword in query_lower for keyword in security_research_keywords)
        )
        
        # Check if query contains current info keywords
        has_current_keyword = (
            any(keyword in query_lower for keyword in current_code_keywords) or
            any(keyword in query_lower for keyword in current_info_keywords)
        )
        
        # Check if query asks about recent events or code
        is_question_about_current = any(phrase in query_lower for phrase in [
            'what happened', "what's happening", 'what is happening',
            'tell me about', 'what do you know about', 'search for',
            'find information about', 'look up', 'show me code',
            'example code', 'how to implement', 'recent changes'
        ])
        
        return has_security_keyword or has_current_keyword or is_question_about_current


# Singleton instance
_eden_ai_handler = None

def get_eden_ai_handler() -> Optional[EdenAIHandler]:
    """Get or create Eden AI handler singleton"""
    global _eden_ai_handler
    if _eden_ai_handler is None:
        _eden_ai_handler = EdenAIHandler()
    return _eden_ai_handler if _eden_ai_handler.is_available() else None
