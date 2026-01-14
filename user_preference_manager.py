# -*- coding: utf-8 -*-
"""
User Preference Manager - Manage user preferences and memory retention
"""

import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class UserPreferenceManager:
    """Manage user preferences and memory retention"""
    
    def __init__(self, secure_memory=None, vector_memory=None):
        """Initialize User Preference Manager
        
        Args:
            secure_memory: Secure memory instance for storing preferences
            vector_memory: Vector memory instance for semantic search
        """
        self.secure_memory = secure_memory
        self.vector_memory = vector_memory
        self.preferences_cache: Dict[int, Dict] = {}  # Cache for quick access
    
    async def store_user_preference(self, user_id: int, preference_type: str, 
                                   value: str, context: Dict) -> bool:
        """Store user preference in memory
        
        Args:
            user_id: Telegram user ID
            preference_type: Type of preference (method, resource, approach, etc.)
            value: Preference value (method description, resource path, etc.)
            context: Bot context for additional metadata
        
        Returns:
            True if stored successfully
        """
        try:
            preference_data = {
                'user_id': user_id,
                'preference_type': preference_type,
                'value': value,
                'timestamp': datetime.now().isoformat(),
                'metadata': {
                    'source': context.get('source', 'user_input'),
                    'task_type': context.get('task_type', 'general')
                }
            }
            
            # Store in cache
            if user_id not in self.preferences_cache:
                self.preferences_cache[user_id] = {}
            if preference_type not in self.preferences_cache[user_id]:
                self.preferences_cache[user_id][preference_type] = []
            
            self.preferences_cache[user_id][preference_type].append(preference_data)
            
            # Store in secure memory if available
            if self.secure_memory:
                try:
                    # Get existing preferences
                    existing = self.get_user_preferences(user_id, preference_type)
                    if not existing:
                        existing = []
                    
                    existing.append(preference_data)
                    
                    # Store back
                    if hasattr(self.secure_memory, 'store_user_data'):
                        self.secure_memory.store_user_data(
                            user_id,
                            f'preferences_{preference_type}',
                            existing
                        )
                    elif hasattr(self.secure_memory, 'store_chat_history'):
                        # Fallback: store in chat history with special marker
                        history = self.secure_memory.get_chat_history(user_id) or []
                        history.append({
                            'role': 'system',
                            'content': f'[PREFERENCE:{preference_type}]{value}',
                            'timestamp': datetime.now().isoformat()
                        })
                        self.secure_memory.store_chat_history(user_id, history)
                except Exception as e:
                    logger.warning(f"Error storing preference in secure memory: {e}")
            
            # Store in vector memory if available
            if self.vector_memory:
                try:
                    if hasattr(self.vector_memory, 'store_conversation_with_embedding'):
                        self.vector_memory.store_conversation_with_embedding(
                            user_id,
                            f"User preference: {preference_type}",
                            response=f"Preference value: {value}",
                            metadata={
                                'type': 'user_preference',
                                'preference_type': preference_type,
                                'source': 'user_input'
                            }
                        )
                except Exception as e:
                    logger.warning(f"Error storing preference in vector memory: {e}")
            
            logger.info(f"Stored preference for user {user_id}: {preference_type} = {value[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Error storing user preference: {e}")
            return False
    
    async def get_user_preferences(self, user_id: int, preference_type: str = None) -> Dict:
        """Retrieve user preferences from memory
        
        Args:
            user_id: Telegram user ID
            preference_type: Optional specific preference type, or None for all
        
        Returns:
            Dict of preferences, keyed by preference_type
        """
        preferences = {}
        
        # Check cache first
        if user_id in self.preferences_cache:
            if preference_type:
                preferences[preference_type] = self.preferences_cache[user_id].get(preference_type, [])
            else:
                preferences = self.preferences_cache[user_id].copy()
        
        # Load from secure memory if available
        if self.secure_memory:
            try:
                if preference_type:
                    if hasattr(self.secure_memory, 'get_user_data'):
                        stored = self.secure_memory.get_user_data(user_id, f'preferences_{preference_type}')
                        if stored:
                            preferences[preference_type] = stored
                    else:
                        # Fallback: search chat history
                        history = self.secure_memory.get_chat_history(user_id) or []
                        for entry in history:
                            if entry.get('role') == 'system' and f'[PREFERENCE:{preference_type}]' in entry.get('content', ''):
                                value = entry['content'].split(']', 1)[1]
                                if preference_type not in preferences:
                                    preferences[preference_type] = []
                                preferences[preference_type].append({
                                    'value': value,
                                    'timestamp': entry.get('timestamp', '')
                                })
                else:
                    # Get all preferences
                    if hasattr(self.secure_memory, 'get_user_data'):
                        # Try common preference types
                        for pref_type in ['method', 'resource', 'approach', 'tool']:
                            stored = self.secure_memory.get_user_data(user_id, f'preferences_{pref_type}')
                            if stored:
                                preferences[pref_type] = stored
            except Exception as e:
                logger.warning(f"Error retrieving preferences from secure memory: {e}")
        
        return preferences
    
    async def ask_for_personal_methods(self, user_id: int, update, context) -> Optional[str]:
        """Ask user for personal methods/resources when task completes without results
        
        Args:
            user_id: Telegram user ID
            update: Telegram update object
            context: Bot context
        
        Returns:
            User's response text or None
        """
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("📚 I have personal methods/resources", callback_data="pref_yes_personal"),
                InlineKeyboardButton("🔄 Retry with different approach", callback_data="pref_retry"),
                InlineKeyboardButton("✅ Accept current results", callback_data="pref_accept")
            ]])
            
            message = await update.message.reply_text(
                "🤔 **Task Completed Without Results**\n\n"
                "I've completed all steps but didn't find results.\n\n"
                "Do you have any personal method or place you want me to learn and apply? "
                "Send me and I will help!",
                parse_mode='Markdown',
                reply_markup=keyboard
            )
            
            # Store in context for callback handler
            if hasattr(context, 'user_data'):
                context.user_data[f'waiting_personal_methods_{user_id}'] = {
                    'message_id': message.message_id,
                    'timestamp': datetime.now().isoformat()
                }
            
            return None  # Will be set by callback handler
            
        except Exception as e:
            logger.error(f"Error asking for personal methods: {e}")
            return None
    
    def apply_stored_methods(self, user_id: int, task_type: str) -> List[str]:
        """Apply stored methods for a given task type
        
        Args:
            user_id: Telegram user ID
            task_type: Type of task (brute_force, scan, etc.)
        
        Returns:
            List of method descriptions to apply
        """
        methods = []
        
        # Get user preferences
        preferences = self.get_user_preferences(user_id, 'method')
        
        # Filter by task type relevance
        for pref_type, pref_list in preferences.items():
            if isinstance(pref_list, list):
                for pref in pref_list:
                    if isinstance(pref, dict):
                        value = pref.get('value', '')
                        metadata = pref.get('metadata', {})
                        pref_task_type = metadata.get('task_type', 'general')
                        
                        # Check if preference is relevant to current task
                        if (pref_task_type == task_type or 
                            pref_task_type == 'general' or
                            task_type in value.lower() or
                            value.lower() in task_type):
                            methods.append(value)
        
        logger.info(f"Found {len(methods)} stored methods for user {user_id}, task {task_type}")
        return methods
