# -*- coding: utf-8 -*-
"""
Vector Memory Manager - ChromaDB-based semantic memory for Cursor-style chat history
Provides vector embeddings and semantic search for conversation history
"""

import os
import logging
import threading
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime, timedelta
import hashlib
import json

logger = logging.getLogger(__name__)

# Try to import ChromaDB
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.warning("ChromaDB not available. Install with: pip install chromadb")

# Try to import OpenAI for embeddings
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI not available for embeddings")

# Try to import sentence-transformers for local embeddings
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("Sentence-transformers not available. Install with: pip install sentence-transformers")


def get_vector_memory_manager(workspace_root: Optional[str] = None) -> Optional['VectorMemoryManager']:
    """Get or create VectorMemoryManager instance"""
    if not CHROMADB_AVAILABLE:
        return None
    
    try:
        return VectorMemoryManager(workspace_root)
    except Exception as e:
        logger.error(f"Failed to initialize VectorMemoryManager: {e}")
        return None


class VectorMemoryManager:
    """Vector-based memory manager using ChromaDB for semantic search"""
    
    def __init__(self, workspace_root: Optional[str] = None):
        """
        Initialize Vector Memory Manager
        workspace_root: Base workspace directory for ChromaDB persistence
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError("ChromaDB is not installed")
        
        self.workspace_root = Path(workspace_root) if workspace_root else Path(os.getcwd())
        self.vector_memory_dir = self.workspace_root / "vector_memory"
        self.vector_memory_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=str(self.vector_memory_dir),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Thread safety
        self.locks: Dict[int, threading.Lock] = {}
        self.global_lock = threading.Lock()
        
        # Embedding configuration
        from memory_config import (
            EMBEDDING_PROVIDER, EMBEDDING_MODEL, LOCAL_EMBEDDING_MODEL,
            ENABLE_EMBEDDING_CACHE, EMBEDDING_CACHE_SIZE
        )
        
        self.embedding_provider = EMBEDDING_PROVIDER
        self.embedding_model = EMBEDDING_MODEL
        self.local_embedding_model = LOCAL_EMBEDDING_MODEL
        self.enable_cache = ENABLE_EMBEDDING_CACHE
        
        # Initialize embedding models
        self.openai_client = None
        self.local_embedder = None
        
        if self.embedding_provider == 'openai' and OPENAI_AVAILABLE:
            api_key = os.getenv('OPENAI_API_KEY') or os.getenv('DEEPSEEK_API_KEY')
            if api_key:
                self.openai_client = openai.OpenAI(api_key=api_key)
                logger.info(f"Using OpenAI embeddings: {self.embedding_model}")
            else:
                logger.warning("OpenAI API key not found, falling back to local embeddings")
                self.embedding_provider = 'local'
        
        if self.embedding_provider == 'local' and SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self.local_embedder = SentenceTransformer(self.local_embedding_model)
                logger.info(f"Using local embeddings: {self.local_embedding_model}")
            except Exception as e:
                logger.error(f"Failed to load local embedding model: {e}")
        
        # Embedding cache
        self.embedding_cache: Dict[str, List[float]] = {}
        self.cache_max_size = EMBEDDING_CACHE_SIZE
        
        logger.info("VectorMemoryManager initialized")
    
    def _get_user_lock(self, user_id: int) -> threading.Lock:
        """Get or create lock for user"""
        with self.global_lock:
            if user_id not in self.locks:
                self.locks[user_id] = threading.Lock()
            return self.locks[user_id]
    
    def _get_collection_name(self, user_id: int) -> str:
        """Get collection name for user"""
        from memory_config import CHROMA_COLLECTION_PREFIX
        return f"{CHROMA_COLLECTION_PREFIX}{user_id}_conversations"
    
    def _get_collection(self, user_id: int):
        """Get or create collection for user"""
        collection_name = self._get_collection_name(user_id)
        
        try:
            # Try to get existing collection
            return self.client.get_collection(name=collection_name)
        except:
            # Create new collection if it doesn't exist
            return self.client.create_collection(
                name=collection_name,
                metadata={"user_id": str(user_id), "created_at": datetime.now().isoformat()}
            )
    
    def _get_embedding_cache_key(self, text: str) -> str:
        """Generate cache key for text"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text"""
        if not text or not text.strip():
            return None
        
        # Check cache
        if self.enable_cache:
            cache_key = self._get_embedding_cache_key(text)
            if cache_key in self.embedding_cache:
                return self.embedding_cache[cache_key]
        
        embedding = None
        
        # Try OpenAI first
        if self.embedding_provider == 'openai' and self.openai_client:
            try:
                response = self.openai_client.embeddings.create(
                    model=self.embedding_model,
                    input=text
                )
                embedding = response.data[0].embedding
            except Exception as e:
                logger.warning(f"OpenAI embedding failed: {e}, falling back to local")
                self.embedding_provider = 'local'
        
        # Fallback to local embeddings
        if not embedding and self.local_embedder:
            try:
                embedding = self.local_embedder.encode(text, convert_to_numpy=False).tolist()
            except Exception as e:
                logger.error(f"Local embedding failed: {e}")
                return None
        
        # Cache embedding
        if embedding and self.enable_cache:
            cache_key = self._get_embedding_cache_key(text)
            # Simple LRU: remove oldest if cache is full
            if len(self.embedding_cache) >= self.cache_max_size:
                # Remove first item (oldest)
                self.embedding_cache.pop(next(iter(self.embedding_cache)))
            self.embedding_cache[cache_key] = embedding
        
        return embedding
    
    def store_conversation(
        self,
        user_id: int,
        message: str,
        response: Optional[str] = None,
        metadata: Optional[Dict] = None,
        conversation_id: Optional[str] = None
    ) -> bool:
        """
        Store conversation with embedding
        user_id: User ID
        message: User message
        response: Bot response (optional)
        metadata: Additional metadata
        conversation_id: Group related messages
        """
        user_lock = self._get_user_lock(user_id)
        
        with user_lock:
            try:
                collection = self._get_collection(user_id)
                
                # Generate embedding for user message
                message_embedding = self._generate_embedding(message)
                if not message_embedding:
                    logger.warning(f"Failed to generate embedding for user message")
                    return False
                
                # Store user message
                message_id = f"{user_id}_{datetime.now().timestamp()}_{hashlib.md5(message.encode()).hexdigest()[:8]}"
                message_metadata = {
                    'user_id': str(user_id),
                    'role': 'user',
                    'timestamp': datetime.now().isoformat(),
                    'message': message[:500],  # Store first 500 chars in metadata
                }
                
                if conversation_id:
                    message_metadata['conversation_id'] = conversation_id
                if metadata:
                    message_metadata.update(metadata)
                
                collection.add(
                    ids=[message_id],
                    embeddings=[message_embedding],
                    documents=[message],
                    metadatas=[message_metadata]
                )
                
                # Store bot response if provided
                if response:
                    response_embedding = self._generate_embedding(response)
                    if response_embedding:
                        response_id = f"{user_id}_{datetime.now().timestamp()}_response_{hashlib.md5(response.encode()).hexdigest()[:8]}"
                        response_metadata = {
                            'user_id': str(user_id),
                            'role': 'assistant',
                            'timestamp': datetime.now().isoformat(),
                            'message': response[:500],
                        }
                        
                        if conversation_id:
                            response_metadata['conversation_id'] = conversation_id
                        if metadata:
                            response_metadata.update(metadata)
                        
                        collection.add(
                            ids=[response_id],
                            embeddings=[response_embedding],
                            documents=[response],
                            metadatas=[response_metadata]
                        )
                
                logger.debug(f"Stored conversation for user {user_id}")
                return True
                
            except Exception as e:
                logger.error(f"Error storing conversation for user {user_id}: {e}", exc_info=True)
                return False
    
    def search_similar(
        self,
        user_id: int,
        query: str,
        limit: int = 5,
        filter_metadata: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Search for similar past conversations
        user_id: User ID
        query: Search query
        limit: Maximum number of results
        filter_metadata: Optional metadata filters
        """
        user_lock = self._get_user_lock(user_id)
        
        with user_lock:
            try:
                collection = self._get_collection(user_id)
                
                # Generate embedding for query
                query_embedding = self._generate_embedding(query)
                if not query_embedding:
                    logger.warning(f"Failed to generate embedding for query")
                    return []
                
                # Search
                results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=limit,
                    where=filter_metadata if filter_metadata else None
                )
                
                # Format results
                similar_conversations = []
                if results['ids'] and len(results['ids'][0]) > 0:
                    for i in range(len(results['ids'][0])):
                        similar_conversations.append({
                            'id': results['ids'][0][i],
                            'document': results['documents'][0][i],
                            'metadata': results['metadatas'][0][i],
                            'distance': results['distances'][0][i] if 'distances' in results else None
                        })
                
                return similar_conversations
                
            except Exception as e:
                logger.error(f"Error searching similar conversations for user {user_id}: {e}", exc_info=True)
                return []
    
    def get_relevant_context(
        self,
        user_id: int,
        query: str,
        recent_limit: int = 10,
        similar_limit: int = 5
    ) -> Dict[str, List[Dict]]:
        """
        Get relevant context combining recent and similar conversations
        Returns dict with 'recent' and 'similar' keys
        """
        from memory_config import RECENT_HISTORY_LIMIT
        
        user_lock = self._get_user_lock(user_id)
        
        with user_lock:
            try:
                collection = self._get_collection(user_id)
                
                # Get all conversations (ChromaDB get() doesn't support order_by)
                # We'll get all and sort manually
                all_results = collection.get()
                
                recent_conversations = []
                if all_results['ids']:
                    # Combine all data into list of dicts
                    all_conversations = []
                    for i in range(len(all_results['ids'])):
                        metadata = all_results['metadatas'][i] if all_results['metadatas'] else {}
                        all_conversations.append({
                            'id': all_results['ids'][i],
                            'document': all_results['documents'][i] if all_results['documents'] else '',
                            'metadata': metadata,
                            'timestamp': metadata.get('timestamp', '0') if metadata else '0'
                        })
                    
                    # Sort by timestamp (descending - most recent first)
                    all_conversations.sort(key=lambda x: x['timestamp'], reverse=True)
                    
                    # Take only the requested limit
                    limit = recent_limit or RECENT_HISTORY_LIMIT
                    recent_conversations = all_conversations[:limit]
                
                # Get similar conversations
                similar_conversations = self.search_similar(user_id, query, limit=similar_limit)
                
                return {
                    'recent': recent_conversations,
                    'similar': similar_conversations
                }
                
            except Exception as e:
                logger.error(f"Error getting relevant context for user {user_id}: {e}", exc_info=True)
                return {'recent': [], 'similar': []}
    
    def cleanup_old_memories(self, user_id: int, days_to_keep: int = 90) -> int:
        """
        Clean up old memories beyond retention period
        Returns number of items deleted
        """
        user_lock = self._get_user_lock(user_id)
        
        with user_lock:
            try:
                collection = self._get_collection(user_id)
                cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).isoformat()
                
                # Get all items
                all_items = collection.get()
                
                deleted_count = 0
                ids_to_delete = []
                
                if all_items['ids']:
                    for i, metadata in enumerate(all_items['metadatas']):
                        timestamp = metadata.get('timestamp', '')
                        if timestamp and timestamp < cutoff_date:
                            ids_to_delete.append(all_items['ids'][i])
                
                if ids_to_delete:
                    collection.delete(ids=ids_to_delete)
                    deleted_count = len(ids_to_delete)
                    logger.info(f"Cleaned up {deleted_count} old memories for user {user_id}")
                
                return deleted_count
                
            except Exception as e:
                logger.error(f"Error cleaning up memories for user {user_id}: {e}", exc_info=True)
                return 0
    
    def get_stats(self, user_id: int) -> Dict[str, Any]:
        """Get statistics for user's memory"""
        user_lock = self._get_user_lock(user_id)
        
        with user_lock:
            try:
                collection = self._get_collection(user_id)
                count = collection.count()
                
                return {
                    'total_conversations': count,
                    'collection_name': self._get_collection_name(user_id),
                    'embedding_provider': self.embedding_provider,
                    'cache_size': len(self.embedding_cache)
                }
            except Exception as e:
                logger.error(f"Error getting stats for user {user_id}: {e}")
                return {'total_conversations': 0}
    
    def migrate_existing_history(self, user_id: int, chat_history: List[Dict]) -> int:
        """
        Migrate existing chat history to vector DB
        Returns number of conversations migrated
        """
        if not chat_history:
            return 0
        
        user_lock = self._get_user_lock(user_id)
        migrated_count = 0
        
        with user_lock:
            try:
                # Group messages into conversations (user message + assistant response)
                i = 0
                while i < len(chat_history):
                    user_msg = None
                    assistant_msg = None
                    
                    # Find user message
                    while i < len(chat_history):
                        msg = chat_history[i]
                        if msg.get('role') == 'user':
                            user_msg = msg.get('content', '')
                            i += 1
                            break
                        i += 1
                    
                    # Find corresponding assistant message
                    if user_msg and i < len(chat_history):
                        msg = chat_history[i]
                        if msg.get('role') == 'assistant':
                            assistant_msg = msg.get('content', '')
                            i += 1
                    
                    # Store conversation if we have at least user message
                    if user_msg:
                        conversation_id = f"migrated_{user_id}_{migrated_count}"
                        success = self.store_conversation(
                            user_id, user_msg, assistant_msg,
                            conversation_id=conversation_id,
                            metadata={'migrated': True, 'source': 'existing_history'}
                        )
                        if success:
                            migrated_count += 1
                
                logger.info(f"Migrated {migrated_count} conversations for user {user_id}")
                return migrated_count
                
            except Exception as e:
                logger.error(f"Error migrating history for user {user_id}: {e}", exc_info=True)
                return migrated_count


# Module-level availability flag
VECTOR_MEMORY_AVAILABLE = CHROMADB_AVAILABLE
