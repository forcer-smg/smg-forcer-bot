# -*- coding: utf-8 -*-
"""
Context Retrieval Manager - Smart context retrieval combining recent and semantic search
Provides intelligent context assembly for AI conversations
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import vector memory manager
try:
    from vector_memory_manager import get_vector_memory_manager, VECTOR_MEMORY_AVAILABLE
except ImportError:
    VECTOR_MEMORY_AVAILABLE = False
    logger.warning("VectorMemoryManager not available")

# Try to import secure memory manager
try:
    from secure_memory_manager import get_secure_memory_manager, SECURE_MEMORY_AVAILABLE
except ImportError:
    SECURE_MEMORY_AVAILABLE = False
    logger.warning("SecureMemoryManager not available")


def get_context_retrieval_manager(workspace_root: Optional[str] = None) -> Optional['ContextRetrievalManager']:
    """Get or create ContextRetrievalManager instance"""
    try:
        return ContextRetrievalManager(workspace_root)
    except Exception as e:
        logger.error(f"Failed to initialize ContextRetrievalManager: {e}")
        return None


class ContextRetrievalManager:
    """Smart context retrieval combining recent history and semantic search"""
    
    def __init__(self, workspace_root: Optional[str] = None):
        """
        Initialize Context Retrieval Manager
        workspace_root: Base workspace directory
        """
        self.workspace_root = workspace_root
        
        # Initialize vector memory manager
        self.vector_memory = None
        if VECTOR_MEMORY_AVAILABLE:
            try:
                self.vector_memory = get_vector_memory_manager(workspace_root)
            except Exception as e:
                logger.warning(f"VectorMemoryManager not available: {e}")
        
        # Initialize secure memory manager
        self.secure_memory = None
        if SECURE_MEMORY_AVAILABLE:
            try:
                self.secure_memory = get_secure_memory_manager(workspace_root)
            except Exception as e:
                logger.warning(f"SecureMemoryManager not available: {e}")
        
        # Import configuration
        try:
            from memory_config import (
                MAX_CONTEXT_TOKENS, SEMANTIC_SEARCH_LIMIT, RECENT_HISTORY_LIMIT,
                SHORT_TERM_RETENTION_DAYS, LONG_TERM_RETENTION_DAYS
            )
            self.max_context_tokens = MAX_CONTEXT_TOKENS
            self.semantic_search_limit = SEMANTIC_SEARCH_LIMIT
            self.recent_history_limit = RECENT_HISTORY_LIMIT
            self.short_term_retention = SHORT_TERM_RETENTION_DAYS
            self.long_term_retention = LONG_TERM_RETENTION_DAYS
        except ImportError:
            # Defaults
            self.max_context_tokens = 2000
            self.semantic_search_limit = 5
            self.recent_history_limit = 10
            self.short_term_retention = 3
            self.long_term_retention = 90
        
        logger.info("ContextRetrievalManager initialized")
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars per token average)"""
        return len(text) // 4
    
    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within token limit"""
        estimated_tokens = self._estimate_tokens(text)
        if estimated_tokens <= max_tokens:
            return text
        
        # Truncate to approximately max_tokens
        max_chars = max_tokens * 4
        return text[:max_chars] + "..."
    
    def _format_conversation(self, item: Dict, include_metadata: bool = False) -> str:
        """Format a conversation item for context"""
        role = item.get('metadata', {}).get('role', 'user') if 'metadata' in item else item.get('role', 'user')
        document = item.get('document', item.get('content', ''))
        timestamp = item.get('metadata', {}).get('timestamp', '') if 'metadata' in item else item.get('timestamp', '')
        
        formatted = f"{role.upper()}: {document}"
        
        if include_metadata and timestamp:
            formatted += f" [Timestamp: {timestamp}]"
        
        return formatted
    
    def _score_relevance(self, item: Dict, query: str) -> float:
        """Score relevance of an item to the query"""
        score = 1.0
        
        # Boost recent items
        if 'metadata' in item and 'timestamp' in item['metadata']:
            try:
                timestamp = datetime.fromisoformat(item['metadata']['timestamp'])
                days_ago = (datetime.now() - timestamp).days
                # Recent items get higher score
                if days_ago < 1:
                    score *= 1.5
                elif days_ago < 7:
                    score *= 1.2
            except:
                pass
        
        # Boost items with lower distance (more similar)
        if 'distance' in item and item['distance'] is not None:
            # Lower distance = more similar = higher score
            distance = item['distance']
            if distance < 0.3:
                score *= 2.0
            elif distance < 0.5:
                score *= 1.5
        
        return score
    
    def retrieve_context(
        self,
        user_id: int,
        query: str,
        max_tokens: Optional[int] = None,
        include_recent: bool = True,
        include_similar: bool = True,
        context_data: Optional[Dict] = None
    ) -> str:
        """
        Retrieve smart context for user query
        user_id: User ID
        query: Current user message/query
        max_tokens: Maximum tokens for context (defaults to config)
        include_recent: Include recent conversation history
        include_similar: Include semantically similar conversations
        context_data: Additional context data (scan results, etc.)
        """
        if max_tokens is None:
            max_tokens = self.max_context_tokens
        
        context_parts = []
        used_tokens = 0
        
        # 1. Add recent action context if provided
        if context_data:
            action_context = []
            
            if 'last_scan_report' in context_data:
                scan_target = context_data.get('last_scan_target', 'unknown')
                scan_report = context_data.get('last_scan_report', '')
                action_context.append(f"[RECENT ACTION: Vulnerability Scan]")
                action_context.append(f"Target: {scan_target}")
                action_context.append(f"Results: {scan_report[:800]}...")
            
            if 'last_execution_results' in context_data:
                exec_results = context_data.get('last_execution_results', [])
                if exec_results:
                    action_context.append(f"[RECENT ACTION: Command Execution]")
                    action_context.append(f"Executed {len(exec_results)} command(s)")
            
            if 'generated_files' in context_data:
                files = context_data.get('generated_files', [])
                if files:
                    action_context.append(f"[RECENT ACTION: File Generation]")
                    action_context.append(f"Generated {len(files)} file(s)")
            
            if action_context:
                action_text = "\n".join(action_context)
                tokens = self._estimate_tokens(action_text)
                if used_tokens + tokens <= max_tokens:
                    context_parts.append(action_text)
                    context_parts.append("")
                    used_tokens += tokens
        
        # 2. Get recent conversations
        recent_conversations = []
        if include_recent:
            if self.vector_memory:
                try:
                    # Add timeout protection for vector search
                    import signal
                    import threading
                    
                    result = [None]
                    error = [None]
                    
                    def get_context():
                        try:
                            relevant = self.vector_memory.get_relevant_context(
                                user_id, query, recent_limit=self.recent_history_limit, similar_limit=0
                            )
                            result[0] = relevant.get('recent', [])
                        except Exception as e:
                            error[0] = e
                    
                    thread = threading.Thread(target=get_context)
                    thread.daemon = True
                    thread.start()
                    thread.join(timeout=2.0)  # 2 second timeout
                    
                    if thread.is_alive():
                        logger.warning(f"Vector memory search timed out, skipping")
                        recent_conversations = []
                    elif error[0]:
                        logger.warning(f"Error getting recent conversations: {error[0]}")
                    else:
                        recent_conversations = result[0]
                except Exception as e:
                    logger.warning(f"Error getting recent conversations: {e}")
            
            # Fallback to secure memory
            if not recent_conversations and self.secure_memory:
                try:
                    chat_history = self.secure_memory.get_chat_history(user_id) or []
                    recent_conversations = chat_history[-self.recent_history_limit:] if len(chat_history) > self.recent_history_limit else chat_history
                    # Convert format
                    recent_conversations = [
                        {'document': msg.get('content', ''), 'metadata': {'role': msg.get('role', 'user'), 'timestamp': msg.get('timestamp', '')}}
                        for msg in recent_conversations
                    ]
                except Exception as e:
                    logger.warning(f"Error getting recent from secure memory: {e}")
        
        # 3. Get semantically similar conversations
        similar_conversations = []
        if include_similar and self.vector_memory:
            try:
                # Add timeout protection for semantic search
                import threading
                
                result = [None]
                error = [None]
                
                def search_similar():
                    try:
                        result[0] = self.vector_memory.search_similar(
                            user_id, query, limit=self.semantic_search_limit
                        )
                    except Exception as e:
                        error[0] = e
                
                thread = threading.Thread(target=search_similar)
                thread.daemon = True
                thread.start()
                thread.join(timeout=2.0)  # 2 second timeout
                
                if thread.is_alive():
                    logger.warning(f"Semantic search timed out, skipping")
                    similar_conversations = []
                elif error[0]:
                    logger.warning(f"Error getting similar conversations: {error[0]}")
                else:
                    similar_conversations = result[0] if result[0] else []
            except Exception as e:
                logger.warning(f"Error getting similar conversations: {e}")
        
        # 4. Combine and deduplicate
        all_conversations = []
        seen_ids = set()
        
        # Add recent first (they're more important)
        for item in recent_conversations:
            item_id = item.get('id', '')
            if item_id and item_id not in seen_ids:
                all_conversations.append(item)
                seen_ids.add(item_id)
        
        # Add similar (avoid duplicates)
        for item in similar_conversations:
            item_id = item.get('id', '')
            if item_id and item_id not in seen_ids:
                all_conversations.append(item)
                seen_ids.add(item_id)
        
        # 5. Score and sort by relevance
        scored_conversations = []
        for item in all_conversations:
            score = self._score_relevance(item, query)
            scored_conversations.append((score, item))
        
        scored_conversations.sort(key=lambda x: x[0], reverse=True)
        
        # 6. Format and add to context (within token limit)
        if scored_conversations:
            context_parts.append("[CONVERSATION HISTORY]")
            
            remaining_tokens = max_tokens - used_tokens
            conversation_texts = []
            
            for score, item in scored_conversations:
                formatted = self._format_conversation(item)
                tokens = self._estimate_tokens(formatted)
                
                if used_tokens + tokens <= max_tokens:
                    conversation_texts.append(formatted)
                    used_tokens += tokens
                else:
                    break
            
            if conversation_texts:
                context_parts.extend(conversation_texts)
                context_parts.append("")
        
        # 7. Add current message
        context_parts.append(f"[CURRENT MESSAGE]\n{query}")
        
        # 8. Combine and truncate if needed
        final_context = "\n".join(context_parts)
        final_tokens = self._estimate_tokens(final_context)
        
        if final_tokens > max_tokens:
            final_context = self._truncate_to_tokens(final_context, max_tokens)
        
        return final_context
    
    def get_context_stats(self, user_id: int) -> Dict[str, Any]:
        """Get statistics about available context"""
        stats = {
            'vector_memory_available': self.vector_memory is not None,
            'secure_memory_available': self.secure_memory is not None,
            'recent_count': 0,
            'similar_count': 0
        }
        
        if self.vector_memory:
            try:
                vector_stats = self.vector_memory.get_stats(user_id)
                stats.update(vector_stats)
            except Exception as e:
                logger.warning(f"Error getting vector stats: {e}")
        
        return stats
