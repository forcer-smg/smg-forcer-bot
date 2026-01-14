# -*- coding: utf-8 -*-
"""
Memory Configuration - Settings for Cursor-style chat history and memory system
"""

import os
from typing import Optional

# Vector memory enabled/disabled
VECTOR_MEMORY_ENABLED = os.getenv('VECTOR_MEMORY_ENABLED', 'true').lower() == 'true'

# Embedding model configuration
EMBEDDING_PROVIDER = os.getenv('EMBEDDING_PROVIDER', 'openai')  # 'openai' or 'local'
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')  # OpenAI model
LOCAL_EMBEDDING_MODEL = os.getenv('LOCAL_EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2')  # Local model

# Retention periods
SHORT_TERM_RETENTION_DAYS = int(os.getenv('SHORT_TERM_RETENTION_DAYS', '3'))
LONG_TERM_RETENTION_DAYS = int(os.getenv('LONG_TERM_RETENTION_DAYS', '90'))

# Context limits
MAX_CONTEXT_TOKENS = int(os.getenv('MAX_CONTEXT_TOKENS', '2000'))
SEMANTIC_SEARCH_LIMIT = int(os.getenv('SEMANTIC_SEARCH_LIMIT', '5'))
RECENT_HISTORY_LIMIT = int(os.getenv('RECENT_HISTORY_LIMIT', '10'))

# ChromaDB settings
CHROMA_PERSIST_DIR = os.getenv('CHROMA_PERSIST_DIR', 'vector_memory')
CHROMA_COLLECTION_PREFIX = os.getenv('CHROMA_COLLECTION_PREFIX', 'user_')

# Embedding cache settings
ENABLE_EMBEDDING_CACHE = os.getenv('ENABLE_EMBEDDING_CACHE', 'true').lower() == 'true'
EMBEDDING_CACHE_SIZE = int(os.getenv('EMBEDDING_CACHE_SIZE', '1000'))

# Performance settings
BATCH_EMBEDDING_SIZE = int(os.getenv('BATCH_EMBEDDING_SIZE', '10'))
EMBEDDING_TIMEOUT = int(os.getenv('EMBEDDING_TIMEOUT', '30'))  # seconds
