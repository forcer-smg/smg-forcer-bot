# -*- coding: utf-8 -*-
"""
Eden AI Integration Handler
Provides current information fetching capabilities for DeepSeek
Eden AI acts as a tool layer for fetching current/recent code, search results, and data
DeepSeek remains the reasoning/agent layer
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
        self.base_url = "https://api.edenai.run/v2"
        
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
    
    def format_search_results(self, results: List[Dict[str, Any]], result_type: str = "web") -> str:
        """
        Format search results for display to DeepSeek
        
        Args:
            results: List of search results
            result_type: Type of results ("web", "code", "news")
        
        Returns:
            Formatted string for DeepSeek to use
        """
        if not results:
            return f"No {result_type} results found."
        
        formatted = f"**Eden AI {result_type.upper()} Search Results:**\n\n"
        
        for i, result in enumerate(results, 1):
            formatted += f"{i}. **{result.get('title', 'No title')}**\n"
            
            if result_type == "code":
                formatted += f"   Language: {result.get('language', 'N/A')}\n"
                formatted += f"   Source: {result.get('source', 'N/A')}\n"
            
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
        
        # Keywords that indicate need for current information
        current_info_keywords = [
            'current', 'latest', 'recent', 'today', 'now', '2026', '2025',
            'news', 'happening', 'update', 'breaking', 'just', 'new',
            'what is', 'who is', 'when did', 'where is', 'how is',
            'did', 'has', 'have', 'was', 'were', 'is', 'are',
            'code example', 'implementation', 'how to', 'tutorial',
            'search for', 'find', 'look up', 'get information'
        ]
        
        # Check if query contains current info keywords
        has_current_keyword = any(keyword in query_lower for keyword in current_info_keywords)
        
        # Check if query asks about recent events or code
        is_question_about_current = any(phrase in query_lower for phrase in [
            'what happened', "what's happening", 'what is happening',
            'tell me about', 'what do you know about', 'search for',
            'find information about', 'look up', 'show me code',
            'example code', 'how to implement', 'recent changes'
        ])
        
        return has_current_keyword or is_question_about_current


# Singleton instance
_eden_ai_handler = None

def get_eden_ai_handler() -> Optional[EdenAIHandler]:
    """Get or create Eden AI handler singleton"""
    global _eden_ai_handler
    if _eden_ai_handler is None:
        _eden_ai_handler = EdenAIHandler()
    return _eden_ai_handler if _eden_ai_handler.is_available() else None
