# -*- coding: utf-8 -*-
"""
Web Search Handler - Real-time web search capabilities for current information
Supports multiple search APIs: Google Custom Search, Serper, Bing Search
"""

import os
import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class WebSearchHandler:
    """Handles web search for real-time information access"""
    
    def __init__(self):
        """Initialize web search handler with available APIs"""
        self.serper_api_key = os.getenv('SERPER_API_KEY')
        self.google_api_key = os.getenv('GOOGLE_SEARCH_API_KEY')
        self.google_cx = os.getenv('GOOGLE_SEARCH_ENGINE_ID')
        self.bing_api_key = os.getenv('BING_SEARCH_API_KEY')
        
        # Determine which API to use (priority order)
        self.active_api = None
        if self.serper_api_key:
            self.active_api = 'serper'
            logger.info("Web search: Using Serper API")
        elif self.google_api_key and self.google_cx:
            self.active_api = 'google'
            logger.info("Web search: Using Google Custom Search API")
        elif self.bing_api_key:
            self.active_api = 'bing'
            logger.info("Web search: Using Bing Search API")
        else:
            logger.warning("No web search API keys configured. Web search disabled.")
    
    def is_available(self) -> bool:
        """Check if web search is available"""
        return self.active_api is not None
    
    async def search(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search the web for current information
        
        Args:
            query: Search query
            num_results: Number of results to return (default: 5)
        
        Returns:
            List of search results with title, snippet, url
        """
        if not self.is_available():
            logger.warning("Web search not available - no API keys configured")
            return []
        
        try:
            if self.active_api == 'serper':
                return await self._search_serper(query, num_results)
            elif self.active_api == 'google':
                return await self._search_google(query, num_results)
            elif self.active_api == 'bing':
                return await self._search_bing(query, num_results)
        except Exception as e:
            logger.error(f"Error performing web search: {e}")
            return []
    
    async def _search_serper(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        """Search using Serper API"""
        url = "https://google.serper.dev/search"
        headers = {
            'X-API-KEY': self.serper_api_key,
            'Content-Type': 'application/json'
        }
        payload = {
            'q': query,
            'num': num_results
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get('organic', [])[:num_results]:
            results.append({
                'title': item.get('title', ''),
                'snippet': item.get('snippet', ''),
                'url': item.get('link', ''),
                'date': item.get('date', '')
            })
        
        return results
    
    async def _search_google(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        """Search using Google Custom Search API"""
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'key': self.google_api_key,
            'cx': self.google_cx,
            'q': query,
            'num': min(num_results, 10)  # Google limits to 10 per request
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get('items', [])[:num_results]:
            results.append({
                'title': item.get('title', ''),
                'snippet': item.get('snippet', ''),
                'url': item.get('link', ''),
                'date': item.get('pagemap', {}).get('metatags', [{}])[0].get('date', '')
            })
        
        return results
    
    async def _search_bing(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        """Search using Bing Search API"""
        url = "https://api.bing.microsoft.com/v7.0/search"
        headers = {
            'Ocp-Apim-Subscription-Key': self.bing_api_key
        }
        params = {
            'q': query,
            'count': num_results,
            'textDecorations': True,
            'textFormat': 'HTML'
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get('webPages', {}).get('value', [])[:num_results]:
            results.append({
                'title': item.get('name', ''),
                'snippet': item.get('snippet', ''),
                'url': item.get('url', ''),
                'date': item.get('dateLastCrawled', '')
            })
        
        return results
    
    def format_search_results(self, results: List[Dict[str, Any]]) -> str:
        """Format search results for display"""
        if not results:
            return "No search results found."
        
        formatted = "**Web Search Results:**\n\n"
        for i, result in enumerate(results, 1):
            formatted += f"{i}. **{result.get('title', 'No title')}**\n"
            formatted += f"   {result.get('snippet', 'No description')}\n"
            formatted += f"   🔗 {result.get('url', '')}\n"
            if result.get('date'):
                formatted += f"   📅 {result.get('date')}\n"
            formatted += "\n"
        
        return formatted
    
    def should_use_search(self, query: str) -> bool:
        """
        Determine if a query needs web search (current information)
        
        Args:
            query: User query to analyze
        
        Returns:
            True if web search should be used
        """
        query_lower = query.lower()
        
        # Keywords that indicate need for current information
        current_info_keywords = [
            'current', 'latest', 'recent', 'today', 'now', '2026', '2025',
            'news', 'happening', 'update', 'breaking', 'just', 'new',
            'what is', 'who is', 'when did', 'where is', 'how is',
            'did', 'has', 'have', 'was', 'were', 'is', 'are'
        ]
        
        # Check if query contains current info keywords
        has_current_keyword = any(keyword in query_lower for keyword in current_info_keywords)
        
        # Check if query asks about recent events
        is_question_about_events = any(phrase in query_lower for phrase in [
            'what happened', 'what\'s happening', 'what is happening',
            'tell me about', 'what do you know about', 'search for',
            'find information about', 'look up'
        ])
        
        return has_current_keyword or is_question_about_events
