# -*- coding: utf-8 -*-
"""
Secure Memory Manager - Encrypted per-user memory storage with 3-day auto-deletion
Provides secure, isolated memory storage for each user with automatic cleanup
"""

import os
import json
import logging
import threading
import hashlib
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64

logger = logging.getLogger(__name__)


class SecureMemoryManager:
    """Secure memory storage with encryption and automatic cleanup"""
    
    def __init__(self, workspace_root: Optional[str] = None, retention_days: int = 3):
        """
        Initialize Secure Memory Manager
        workspace_root: Base workspace directory
        retention_days: Number of days to retain data (default: 3)
        """
        self.workspace_root = Path(workspace_root) if workspace_root else Path(os.getcwd())
        self.memory_store = self.workspace_root / "memory_store"
        self.memory_store.mkdir(parents=True, exist_ok=True)
        
        self.retention_days = retention_days
        self.retention_delta = timedelta(days=retention_days)
        
        # Thread safety
        self.locks: Dict[int, threading.Lock] = {}
        self.global_lock = threading.Lock()
        
        # Encryption key management
        self.master_key = self._get_or_create_master_key()
        
        # Track active users
        self.active_users: Dict[int, datetime] = {}
        self.active_users_lock = threading.Lock()
        
        # Vector memory integration (optional)
        self.vector_memory = None
        try:
            from vector_memory_manager import get_vector_memory_manager, VECTOR_MEMORY_AVAILABLE
            if VECTOR_MEMORY_AVAILABLE:
                self.vector_memory = get_vector_memory_manager(str(self.workspace_root))
        except ImportError:
            pass
    
    def _get_or_create_master_key(self) -> bytes:
        """Get or create master encryption key"""
        key_file = self.memory_store / ".master_key"
        
        if key_file.exists():
            try:
                with open(key_file, 'rb') as f:
                    return f.read()
            except Exception as e:
                logger.warning(f"Error reading master key: {e}")
        
        # Generate new key
        key = Fernet.generate_key()
        try:
            with open(key_file, 'wb') as f:
                f.write(key)
            # Set restrictive permissions (Unix only)
            if os.name != 'nt':
                os.chmod(key_file, 0o600)
        except Exception as e:
            logger.warning(f"Error saving master key: {e}")
        
        return key
    
    def _get_user_key(self, user_id: int) -> bytes:
        """Derive user-specific encryption key"""
        # Use PBKDF2 to derive key from master key + user_id
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=str(user_id).encode(),
            iterations=100000,
            backend=default_backend()
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.master_key))
        return key
    
    def _get_user_lock(self, user_id: int) -> threading.Lock:
        """Get or create lock for user"""
        with self.global_lock:
            if user_id not in self.locks:
                self.locks[user_id] = threading.Lock()
            return self.locks[user_id]
    
    def _get_user_dir(self, user_id: int) -> Path:
        """Get user-specific directory"""
        user_dir = self.memory_store / f"user_{user_id}"
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir
    
    def _encrypt_data(self, data: bytes, user_id: int) -> bytes:
        """Encrypt data for user"""
        key = self._get_user_key(user_id)
        fernet = Fernet(key)
        return fernet.encrypt(data)
    
    def _decrypt_data(self, encrypted_data: bytes, user_id: int) -> bytes:
        """Decrypt data for user"""
        key = self._get_user_key(user_id)
        fernet = Fernet(key)
        return fernet.decrypt(encrypted_data)
    
    def store_chat_history(self, user_id: int, messages: List[Dict]) -> bool:
        """Store encrypted chat history for user"""
        user_lock = self._get_user_lock(user_id)
        
        with user_lock:
            try:
                user_dir = self._get_user_dir(user_id)
                history_file = user_dir / "chat_history.json.encrypted"
                
                # Prepare data
                data = {
                    'messages': messages,
                    'last_updated': datetime.now().isoformat(),
                    'expires_at': (datetime.now() + self.retention_delta).isoformat()
                }
                
                # Encrypt and store
                json_data = json.dumps(data, ensure_ascii=False)
                encrypted = self._encrypt_data(json_data.encode('utf-8'), user_id)
                
                with open(history_file, 'wb') as f:
                    f.write(encrypted)
                
                # Update metadata
                self._update_metadata(user_id, 'chat_history', datetime.now())
                
                # Track active user
                with self.active_users_lock:
                    self.active_users[user_id] = datetime.now()
                
                logger.debug(f"Stored chat history for user {user_id}")
                return True
            
            except Exception as e:
                logger.error(f"Error storing chat history for user {user_id}: {e}")
                return False
    
    def store_conversation_with_embedding(
        self,
        user_id: int,
        message: str,
        response: Optional[str] = None,
        metadata: Optional[Dict] = None,
        conversation_id: Optional[str] = None
    ) -> bool:
        """
        Store conversation with embedding (hybrid storage)
        Stores in both secure memory and vector memory
        Also triggers migration on first use
        """
        # Migrate existing history on first use
        if self.vector_memory:
            try:
                self.migrate_to_vector_db(user_id)
            except Exception as e:
                logger.warning(f"Migration check failed: {e}")
        
        # Store in secure memory (encrypted)
        messages = [{'role': 'user', 'content': message, 'timestamp': datetime.now().isoformat()}]
        if response:
            messages.append({'role': 'assistant', 'content': response, 'timestamp': datetime.now().isoformat()})
        
        secure_success = self.store_chat_history(user_id, messages)
        
        # Store in vector memory (for semantic search)
        vector_success = True
        if self.vector_memory:
            try:
                vector_success = self.vector_memory.store_conversation(
                    user_id, message, response, metadata, conversation_id
                )
            except Exception as e:
                logger.warning(f"Failed to store in vector memory: {e}")
                vector_success = False
        
        return secure_success or vector_success
    
    def get_semantic_context(self, user_id: int, query: str, limit: int = 5) -> List[Dict]:
        """
        Retrieve semantic context using vector search
        Returns list of relevant past conversations
        """
        if not self.vector_memory:
            return []
        
        try:
            return self.vector_memory.search_similar(user_id, query, limit=limit)
        except Exception as e:
            logger.warning(f"Error getting semantic context: {e}")
            return []
    
    def migrate_to_vector_db(self, user_id: int) -> int:
        """
        Migrate existing chat history to vector DB on first use
        Returns number of conversations migrated
        """
        if not self.vector_memory:
            return 0
        
        try:
            # Check if already migrated
            user_dir = self._get_user_dir(user_id)
            migration_flag = user_dir / ".vector_migration_done"
            if migration_flag.exists():
                return 0  # Already migrated
            
            # Get existing chat history
            chat_history = self.get_chat_history(user_id) or []
            if not chat_history:
                return 0
            
            # Migrate to vector DB
            migrated_count = self.vector_memory.migrate_existing_history(user_id, chat_history)
            
            # Mark as migrated
            if migrated_count > 0:
                migration_flag.touch()
                logger.info(f"Migration completed for user {user_id}: {migrated_count} conversations")
            
            return migrated_count
            
        except Exception as e:
            logger.error(f"Error migrating to vector DB for user {user_id}: {e}", exc_info=True)
            return 0
    
    def get_chat_history(self, user_id: int) -> Optional[List[Dict]]:
        """Retrieve decrypted chat history for user"""
        user_lock = self._get_user_lock(user_id)
        
        with user_lock:
            try:
                user_dir = self._get_user_dir(user_id)
                history_file = user_dir / "chat_history.json.encrypted"
                
                if not history_file.exists():
                    return None
                
                # Check expiration
                if self._is_expired(user_id, 'chat_history'):
                    logger.debug(f"Chat history expired for user {user_id}")
                    return None
                
                # Read and decrypt
                with open(history_file, 'rb') as f:
                    encrypted = f.read()
                
                decrypted = self._decrypt_data(encrypted, user_id)
                data = json.loads(decrypted.decode('utf-8'))
                
                return data.get('messages', [])
            
            except Exception as e:
                logger.error(f"Error retrieving chat history for user {user_id}: {e}")
                return None
    
    def store_context(self, user_id: int, context: Dict) -> bool:
        """Store encrypted context for user"""
        user_lock = self._get_user_lock(user_id)
        
        with user_lock:
            try:
                user_dir = self._get_user_dir(user_id)
                context_file = user_dir / "context.json.encrypted"
                
                # Prepare data
                data = {
                    'context': context,
                    'last_updated': datetime.now().isoformat(),
                    'expires_at': (datetime.now() + self.retention_delta).isoformat()
                }
                
                # Encrypt and store
                json_data = json.dumps(data, ensure_ascii=False)
                encrypted = self._encrypt_data(json_data.encode('utf-8'), user_id)
                
                with open(context_file, 'wb') as f:
                    f.write(encrypted)
                
                # Update metadata
                self._update_metadata(user_id, 'context', datetime.now())
                
                logger.debug(f"Stored context for user {user_id}")
                return True
            
            except Exception as e:
                logger.error(f"Error storing context for user {user_id}: {e}")
                return False
    
    def get_context(self, user_id: int) -> Optional[Dict]:
        """Retrieve decrypted context for user"""
        user_lock = self._get_user_lock(user_id)
        
        with user_lock:
            try:
                user_dir = self._get_user_dir(user_id)
                context_file = user_dir / "context.json.encrypted"
                
                if not context_file.exists():
                    return None
                
                # Check expiration
                if self._is_expired(user_id, 'context'):
                    logger.debug(f"Context expired for user {user_id}")
                    return None
                
                # Read and decrypt
                with open(context_file, 'rb') as f:
                    encrypted = f.read()
                
                decrypted = self._decrypt_data(encrypted, user_id)
                data = json.loads(decrypted.decode('utf-8'))
                
                return data.get('context', {})
            
            except Exception as e:
                logger.error(f"Error retrieving context for user {user_id}: {e}")
                return None
    
    def _update_metadata(self, user_id: int, data_type: str, timestamp: datetime):
        """Update metadata file"""
        try:
            user_dir = self._get_user_dir(user_id)
            metadata_file = user_dir / "metadata.json"
            
            metadata = {}
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                except Exception:
                    pass
            
            metadata[data_type] = {
                'last_updated': timestamp.isoformat(),
                'expires_at': (timestamp + self.retention_delta).isoformat()
            }
            
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
        
        except Exception as e:
            logger.warning(f"Error updating metadata for user {user_id}: {e}")
    
    def _is_expired(self, user_id: int, data_type: str) -> bool:
        """Check if data is expired"""
        try:
            user_dir = self._get_user_dir(user_id)
            metadata_file = user_dir / "metadata.json"
            
            if not metadata_file.exists():
                return True
            
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            if data_type not in metadata:
                return True
            
            expires_at_str = metadata[data_type].get('expires_at')
            if not expires_at_str:
                return True
            
            expires_at = datetime.fromisoformat(expires_at_str)
            return datetime.now() > expires_at
        
        except Exception:
            return True
    
    def delete_user_data(self, user_id: int, secure: bool = True) -> bool:
        """Delete all data for user (with secure overwrite if requested)"""
        user_lock = self._get_user_lock(user_id)
        
        with user_lock:
            try:
                user_dir = self._get_user_dir(user_id)
                
                if not user_dir.exists():
                    return True
                
                # Secure deletion: overwrite before delete
                if secure:
                    for file_path in user_dir.rglob('*'):
                        if file_path.is_file():
                            # Overwrite with random data (3 passes)
                            file_size = file_path.stat().st_size
                            for _ in range(3):
                                with open(file_path, 'r+b') as f:
                                    f.write(os.urandom(file_size))
                                    f.flush()
                                    os.fsync(f.fileno())
                
                # Delete directory
                import shutil
                shutil.rmtree(user_dir, ignore_errors=True)
                
                # Remove from active users
                with self.active_users_lock:
                    self.active_users.pop(user_id, None)
                
                # Remove lock
                with self.global_lock:
                    self.locks.pop(user_id, None)
                
                logger.info(f"Deleted data for user {user_id} (secure={secure})")
                return True
            
            except Exception as e:
                logger.error(f"Error deleting data for user {user_id}: {e}")
                return False
    
    def cleanup_expired(self) -> int:
        """Clean up expired user data"""
        cleaned = 0
        
        try:
            if not self.memory_store.exists():
                return 0
            
            now = datetime.now()
            
            for user_dir in self.memory_store.iterdir():
                if not user_dir.is_dir() or not user_dir.name.startswith('user_'):
                    continue
                
                try:
                    user_id = int(user_dir.name.replace('user_', ''))
                except ValueError:
                    continue
                
                # Check if expired
                metadata_file = user_dir / "metadata.json"
                if not metadata_file.exists():
                    # No metadata, consider expired
                    if self.delete_user_data(user_id, secure=True):
                        cleaned += 1
                    continue
                
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                    
                    expired = True
                    for data_type, info in metadata.items():
                        expires_at_str = info.get('expires_at')
                        if expires_at_str:
                            expires_at = datetime.fromisoformat(expires_at_str)
                            if now <= expires_at:
                                expired = False
                                break
                    
                    if expired:
                        if self.delete_user_data(user_id, secure=True):
                            cleaned += 1
                
                except Exception as e:
                    logger.warning(f"Error checking expiration for user {user_id}: {e}")
                    # If we can't check, delete to be safe
                    if self.delete_user_data(user_id, secure=True):
                        cleaned += 1
        
        except Exception as e:
            logger.error(f"Error in cleanup_expired: {e}")
        
        return cleaned
    
    def get_active_users(self) -> List[int]:
        """Get list of active user IDs"""
        with self.active_users_lock:
            return list(self.active_users.keys())
    
    def get_user_stats(self, user_id: int) -> Optional[Dict]:
        """Get statistics for user"""
        user_dir = self._get_user_dir(user_id)
        
        if not user_dir.exists():
            return None
        
        try:
            metadata_file = user_dir / "metadata.json"
            metadata = {}
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
            
            # Calculate sizes
            total_size = 0
            file_count = 0
            for file_path in user_dir.rglob('*'):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
                    file_count += 1
            
            return {
                'user_id': user_id,
                'file_count': file_count,
                'total_size': total_size,
                'metadata': metadata,
                'is_active': user_id in self.active_users
            }
        
        except Exception as e:
            logger.error(f"Error getting stats for user {user_id}: {e}")
            return None


# Global secure memory manager instance
_memory_manager_instance = None
_memory_manager_lock = threading.Lock()

def get_secure_memory_manager(workspace_root: Optional[str] = None, retention_days: int = 3) -> SecureMemoryManager:
    """Get or create global secure memory manager instance"""
    global _memory_manager_instance
    with _memory_manager_lock:
        if _memory_manager_instance is None:
            _memory_manager_instance = SecureMemoryManager(workspace_root, retention_days)
        return _memory_manager_instance


# Module-level availability flag
SECURE_MEMORY_AVAILABLE = True
