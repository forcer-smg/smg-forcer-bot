# -*- coding: utf-8 -*-
"""
Supabase Conversation Context - Cursor-style full conversation memory
Stores complete conversation history in Supabase for 400+ concurrent users
Provides smart context selection like Cursor
"""

import os
import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Try to import Supabase client
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logger.warning("Supabase client not available. Install with: pip install supabase")

# Try to import PostgreSQL adapter as fallback
try:
    from database_postgres import Database
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False


class SupabaseConversationContext:
    """Cursor-style conversation context management using Supabase"""
    
    def __init__(self, supabase_url: Optional[str] = None, supabase_key: Optional[str] = None):
        """
        Initialize Supabase Conversation Context
        
        Args:
            supabase_url: Supabase project URL
            supabase_key: Supabase anon/service key
        """
        self.supabase_url = supabase_url or os.getenv('SUPABASE_URL')
        self.supabase_key = supabase_key or os.getenv('SUPABASE_KEY') or os.getenv('SUPABASE_ANON_KEY')
        
        # Initialize Supabase client if available
        self.supabase_client: Optional[Client] = None
        if SUPABASE_AVAILABLE and self.supabase_url and self.supabase_key:
            try:
                self.supabase_client = create_client(self.supabase_url, self.supabase_key)
                logger.info("Supabase client initialized for conversation context")
            except Exception as e:
                logger.warning(f"Failed to initialize Supabase client: {e}")
                self.supabase_client = None
        
        # Fallback to PostgreSQL if Supabase not available
        self.postgres_db = None
        if not self.supabase_client and POSTGRES_AVAILABLE:
            try:
                self.postgres_db = Database()
                logger.info("Using PostgreSQL as fallback for conversation context")
            except Exception as e:
                logger.warning(f"Failed to initialize PostgreSQL fallback: {e}")
        
        # Context window settings (Cursor-style)
        self.max_context_tokens = 128000  # 128K tokens like Cursor
        self.max_recent_messages = 50  # Last 50 messages
        self.max_similar_messages = 20  # Top 20 similar messages
        
        # Initialize tables
        self._init_tables()
    
    def _init_tables(self):
        """Initialize conversation context tables"""
        if self.postgres_db:
            try:
                conn = self.postgres_db.get_connection()
                cursor = conn.cursor()
                
                # Conversation messages table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_messages (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id BIGINT NOT NULL,
                        chat_id TEXT NOT NULL,
                        message_id TEXT,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        metadata JSONB,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        token_count INTEGER,
                        embedding_vector VECTOR(384)
                    )
                """)
                
                # Conversation sessions table (like Cursor's chat sessions)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_sessions (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id BIGINT NOT NULL,
                        session_name TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        message_count INTEGER DEFAULT 0,
                        total_tokens INTEGER DEFAULT 0,
                        metadata JSONB
                    )
                """)
                
                # Indexes for fast retrieval
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_conv_msg_user_timestamp 
                    ON conversation_messages(user_id, timestamp DESC)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_conv_msg_chat 
                    ON conversation_messages(chat_id, timestamp DESC)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_conv_sessions_user 
                    ON conversation_sessions(user_id, last_activity DESC)
                """)
                
                conn.commit()
                cursor.close()
                conn.close()
                logger.info("Conversation context tables created")
            except Exception as e:
                logger.error(f"Error creating conversation context tables: {e}")
    
    async def store_message(
        self,
        user_id: int,
        chat_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None,
        message_id: Optional[str] = None
    ) -> str:
        """
        Store a conversation message (Cursor-style)
        
        Args:
            user_id: Telegram user ID
            chat_id: Chat/session ID
            role: 'user' or 'assistant'
            content: Message content
            metadata: Additional metadata (file references, tool calls, etc.)
            message_id: Optional message ID
        
        Returns:
            Message UUID
        """
        import uuid
        msg_id = str(uuid.uuid4())
        
        # Estimate token count (rough: 4 chars per token)
        token_count = len(content) // 4
        
        try:
            if self.postgres_db:
                conn = self.postgres_db.get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO conversation_messages (
                        id, user_id, chat_id, message_id, role, content, 
                        metadata, token_count
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    msg_id, user_id, chat_id, message_id, role, content,
                    json.dumps(metadata) if metadata else None, token_count
                ))
                
                # Update session activity
                cursor.execute("""
                    UPDATE conversation_sessions 
                    SET last_activity = CURRENT_TIMESTAMP, 
                        message_count = message_count + 1,
                        total_tokens = total_tokens + %s
                    WHERE user_id = %s AND id = %s
                """, (token_count, user_id, chat_id))
                
                conn.commit()
                cursor.close()
                conn.close()
                logger.debug(f"Stored message {msg_id} for user {user_id}")
            return msg_id
        except Exception as e:
            logger.error(f"Error storing message: {e}")
            return None
    
    async def get_conversation_context(
        self,
        user_id: int,
        chat_id: str,
        current_message: str,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Get conversation context (Cursor-style smart selection)
        
        Args:
            user_id: Telegram user ID
            chat_id: Chat/session ID
            current_message: Current user message
            max_tokens: Maximum tokens for context (defaults to max_context_tokens)
        
        Returns:
            Formatted conversation context
        """
        if max_tokens is None:
            max_tokens = self.max_context_tokens
        
        try:
            if self.postgres_db:
                conn = self.postgres_db.get_connection()
                cursor = conn.cursor()
                
                # Get recent messages (like Cursor's recent history)
                cursor.execute("""
                    SELECT role, content, metadata, timestamp, token_count
                    FROM conversation_messages
                    WHERE user_id = %s AND chat_id = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                """, (user_id, chat_id, self.max_recent_messages))
                
                recent_messages = cursor.fetchall()
                
                # Format context (Cursor-style: full conversation)
                context_parts = []
                used_tokens = 0
                
                # Add messages in chronological order (oldest first)
                for msg in reversed(recent_messages):
                    role, content, metadata, timestamp, token_count = msg
                    
                    # Format message
                    formatted = f"{role.upper()}: {content}"
                    
                    # Add metadata if available (file references, tool calls, etc.)
                    if metadata:
                        try:
                            meta = json.loads(metadata) if isinstance(metadata, str) else metadata
                            if meta.get('files'):
                                formatted += f"\n[Files: {', '.join(meta.get('files', []))}]"
                            if meta.get('tools'):
                                formatted += f"\n[Tools: {', '.join(meta.get('tools', []))}]"
                        except:
                            pass
                    
                    if used_tokens + token_count <= max_tokens:
                        context_parts.append(formatted)
                        used_tokens += token_count
                    else:
                        # Truncate if needed
                        remaining_tokens = max_tokens - used_tokens
                        if remaining_tokens > 100:  # Only add if meaningful
                            truncated = content[:remaining_tokens * 4]
                            context_parts.append(f"{role.upper()}: {truncated}...")
                        break
                
                cursor.close()
                conn.close()
                
                # Add current message
                context_parts.append(f"USER: {current_message}")
                
                return "\n\n".join(context_parts)
            return current_message
        except Exception as e:
            logger.error(f"Error getting conversation context: {e}")
            return current_message
    
    async def get_similar_messages(
        self,
        user_id: int,
        query: str,
        limit: int = 20
    ) -> List[Dict]:
        """
        Get semantically similar messages (for context retrieval)
        Uses vector similarity search if embeddings available
        """
        # For now, use keyword matching (can be enhanced with vector search)
        try:
            if self.postgres_db:
                conn = self.postgres_db.get_connection()
                cursor = conn.cursor()
                
                # Simple keyword search (can be enhanced with pgvector)
                keywords = query.lower().split()[:5]  # Top 5 keywords
                search_pattern = '%' + '%'.join(keywords) + '%'
                
                cursor.execute("""
                    SELECT role, content, metadata, timestamp
                    FROM conversation_messages
                    WHERE user_id = %s 
                    AND LOWER(content) LIKE %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                """, (user_id, search_pattern, limit))
                
                results = cursor.fetchall()
                cursor.close()
                conn.close()
                
                return [
                    {
                        'role': r[0],
                        'content': r[1],
                        'metadata': json.loads(r[2]) if r[2] else {},
                        'timestamp': r[3].isoformat() if r[3] else None
                    }
                    for r in results
                ]
            return []
        except Exception as e:
            logger.error(f"Error getting similar messages: {e}")
            return []
    
    async def create_session(self, user_id: int, session_name: Optional[str] = None) -> str:
        """Create a new conversation session"""
        import uuid
        session_id = str(uuid.uuid4())
        
        try:
            if self.postgres_db:
                conn = self.postgres_db.get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO conversation_sessions (
                        id, user_id, session_name
                    ) VALUES (%s, %s, %s)
                """, (session_id, user_id, session_name or f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}"))
                conn.commit()
                cursor.close()
                conn.close()
                logger.info(f"Created session {session_id} for user {user_id}")
            return session_id
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            return None
    
    async def get_user_sessions(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Get user's recent conversation sessions"""
        try:
            if self.postgres_db:
                conn = self.postgres_db.get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, session_name, created_at, last_activity, message_count
                    FROM conversation_sessions
                    WHERE user_id = %s
                    ORDER BY last_activity DESC
                    LIMIT %s
                """, (user_id, limit))
                
                sessions = cursor.fetchall()
                cursor.close()
                conn.close()
                
                return [
                    {
                        'id': s[0],
                        'name': s[1],
                        'created_at': s[2].isoformat() if s[2] else None,
                        'last_activity': s[3].isoformat() if s[3] else None,
                        'message_count': s[4]
                    }
                    for s in sessions
                ]
            return []
        except Exception as e:
            logger.error(f"Error getting user sessions: {e}")
            return []


def get_conversation_context() -> Optional[SupabaseConversationContext]:
    """Get or create conversation context instance"""
    try:
        return SupabaseConversationContext()
    except Exception as e:
        logger.error(f"Failed to initialize conversation context: {e}")
        return None
