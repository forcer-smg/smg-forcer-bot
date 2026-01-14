# -*- coding: utf-8 -*-
"""
News Handler - Real-time news access for current events
Supports multiple news APIs: NewsAPI, Currents API, NewsData.io
"""

import os
import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class NewsHandler:
    """Handles news API access for current events"""
    
    def __init__(self):
        """Initialize news handler with available APIs"""
        self.newsapi_key = os.getenv('NEWSAPI_KEY')
        self.currents_api_key = os.getenv('CURRENTS_API_KEY')
        self.newsdata_api_key = os.getenv('NEWSDATA_API_KEY')
        
        # Determine which API to use (priority order)
        self.active_api = None
        if self.newsapi_key:
            self.active_api = 'newsapi'
            logger.info("News: Using NewsAPI")
        elif self.currents_api_key:
            self.active_api = 'currents'
            logger.info("News: Using Currents API")
        elif self.newsdata_api_key:
            self.active_api = 'newsdata'
            logger.info("News: Using NewsData.io API")
        else:
            logger.warning("No news API keys configured. News access disabled.")
    
    def is_available(self) -> bool:
        """Check if news API is available"""
        return self.active_api is not None
    
    async def get_news(self, query: Optional[str] = None, category: Optional[str] = None,
                      country: Optional[str] = None, num_results: int = 10) -> List[Dict[str, Any]]:
        """
        Get current news articles
        
        Args:
            query: Search query (optional)
            category: News category (business, technology, sports, etc.)
            country: Country code (us, gb, etc.)
            num_results: Number of articles to return
        
        Returns:
            List of news articles with title, description, url, publishedAt
        """
        if not self.is_available():
            logger.warning("News API not available - no API keys configured")
            return []
        
        try:
            if self.active_api == 'newsapi':
                return await self._get_newsapi(query, category, country, num_results)
            elif self.active_api == 'currents':
                return await self._get_currents(query, category, num_results)
            elif self.active_api == 'newsdata':
                return await self._get_newsdata(query, category, num_results)
        except Exception as e:
            logger.error(f"Error fetching news: {e}")
            return []
    
    async def _get_newsapi(self, query: Optional[str], category: Optional[str],
                          country: Optional[str], num_results: int) -> List[Dict[str, Any]]:
        """Get news from NewsAPI"""
        if query:
            # Use everything endpoint for search
            url = "https://newsapi.org/v2/everything"
            params = {
                'apiKey': self.newsapi_key,
                'q': query,
                'sortBy': 'publishedAt',
                'pageSize': min(num_results, 100),
                'language': 'en'
            }
        else:
            # Use top headlines
            url = "https://newsapi.org/v2/top-headlines"
            params = {
                'apiKey': self.newsapi_key,
                'pageSize': min(num_results, 100),
                'language': 'en'
            }
            if category:
                params['category'] = category
            if country:
                params['country'] = country
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for article in data.get('articles', [])[:num_results]:
            results.append({
                'title': article.get('title', ''),
                'description': article.get('description', ''),
                'url': article.get('url', ''),
                'publishedAt': article.get('publishedAt', ''),
                'source': article.get('source', {}).get('name', ''),
                'author': article.get('author', '')
            })
        
        return results
    
    async def _get_currents(self, query: Optional[str], category: Optional[str],
                           num_results: int) -> List[Dict[str, Any]]:
        """Get news from Currents API"""
        if query:
            url = "https://api.currentsapi.services/v1/search"
            params = {
                'apiKey': self.currents_api_key,
                'keywords': query,
                'language': 'en',
                'limit': min(num_results, 100)
            }
        else:
            url = "https://api.currentsapi.services/v1/latest-news"
            params = {
                'apiKey': self.currents_api_key,
                'language': 'en',
                'limit': min(num_results, 100)
            }
            if category:
                params['category'] = category
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for article in data.get('news', [])[:num_results]:
            results.append({
                'title': article.get('title', ''),
                'description': article.get('description', ''),
                'url': article.get('url', ''),
                'publishedAt': article.get('published', ''),
                'source': article.get('author', ''),
                'author': article.get('author', '')
            })
        
        return results
    
    async def _get_newsdata(self, query: Optional[str], category: Optional[str],
                            num_results: int) -> List[Dict[str, Any]]:
        """Get news from NewsData.io API"""
        url = "https://newsdata.io/api/1/news"
        params = {
            'apikey': self.newsdata_api_key,
            'language': 'en',
            'size': min(num_results, 10)  # Free tier limit
        }
        
        if query:
            params['q'] = query
        if category:
            params['category'] = category
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for article in data.get('results', [])[:num_results]:
            results.append({
                'title': article.get('title', ''),
                'description': article.get('description', ''),
                'url': article.get('link', ''),
                'publishedAt': article.get('pubDate', ''),
                'source': article.get('source_id', ''),
                'author': article.get('creator', [None])[0] if article.get('creator') else None
            })
        
        return results
    
    def format_news_articles(self, articles: List[Dict[str, Any]]) -> str:
        """Format news articles for display"""
        if not articles:
            return "No news articles found."
        
        formatted = "**📰 Current News:**\n\n"
        for i, article in enumerate(articles, 1):
            formatted += f"{i}. **{article.get('title', 'No title')}**\n"
            if article.get('description'):
                formatted += f"   {article.get('description', '')[:200]}...\n"
            formatted += f"   🔗 {article.get('url', '')}\n"
            if article.get('source'):
                formatted += f"   📰 Source: {article.get('source')}\n"
            if article.get('publishedAt'):
                formatted += f"   📅 {article.get('publishedAt')}\n"
            formatted += "\n"
        
        return formatted
    
    def should_use_news(self, query: str) -> bool:
        """
        Determine if a query needs news access
        
        Args:
            query: User query to analyze
        
        Returns:
            True if news API should be used
        """
        query_lower = query.lower()
        
        # Keywords that indicate need for news
        news_keywords = [
            'news', 'breaking', 'headlines', 'latest news', 'current events',
            'what happened', 'what\'s happening', 'recent events',
            'today\'s news', 'this week', 'this month'
        ]
        
        return any(keyword in query_lower for keyword in news_keywords)
