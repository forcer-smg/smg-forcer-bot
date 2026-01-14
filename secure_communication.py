# -*- coding: utf-8 -*-
"""
Secure Communication - End-to-end encryption and secure API communication
Provides encryption for sensitive data in transit and secure API key storage
"""

import os
import json
import logging
import hashlib
import hmac
import time
from typing import Dict, Optional, Any
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64

logger = logging.getLogger(__name__)


class SecureCommunication:
    """Secure communication layer with encryption and authentication"""
    
    def __init__(self, workspace_root: Optional[str] = None):
        """
        Initialize Secure Communication
        workspace_root: Workspace directory for key storage
        """
        self.workspace_root = Path(workspace_root) if workspace_root else Path(os.getcwd())
        self.keys_dir = self.workspace_root / ".secure_keys"
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate or load communication key
        self.communication_key = self._get_or_create_communication_key()
        
        # API key encryption
        self.api_key_fernet = Fernet(self.communication_key)
    
    def _get_or_create_communication_key(self) -> bytes:
        """Get or create communication encryption key"""
        key_file = self.keys_dir / "communication.key"
        
        if key_file.exists():
            try:
                with open(key_file, 'rb') as f:
                    return f.read()
            except Exception as e:
                logger.warning(f"Error reading communication key: {e}")
        
        # Generate new key
        key = Fernet.generate_key()
        try:
            with open(key_file, 'wb') as f:
                f.write(key)
            # Set restrictive permissions (Unix only)
            if os.name != 'nt':
                os.chmod(key_file, 0o600)
        except Exception as e:
            logger.warning(f"Error saving communication key: {e}")
        
        return key
    
    def encrypt_sensitive_data(self, data: str) -> str:
        """Encrypt sensitive data"""
        try:
            encrypted = self.api_key_fernet.encrypt(data.encode('utf-8'))
            return base64.urlsafe_b64encode(encrypted).decode('utf-8')
        except Exception as e:
            logger.error(f"Error encrypting data: {e}")
            raise
    
    def decrypt_sensitive_data(self, encrypted_data: str) -> str:
        """Decrypt sensitive data"""
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode('utf-8'))
            decrypted = self.api_key_fernet.decrypt(encrypted_bytes)
            return decrypted.decode('utf-8')
        except Exception as e:
            logger.error(f"Error decrypting data: {e}")
            raise
    
    def store_api_key(self, key_name: str, api_key: str) -> bool:
        """Store encrypted API key"""
        try:
            key_file = self.keys_dir / f"{key_name}.encrypted"
            encrypted = self.encrypt_sensitive_data(api_key)
            
            with open(key_file, 'w') as f:
                json.dump({'encrypted_key': encrypted}, f)
            
            # Set restrictive permissions (Unix only)
            if os.name != 'nt':
                os.chmod(key_file, 0o600)
            
            logger.debug(f"Stored encrypted API key: {key_name}")
            return True
        except Exception as e:
            logger.error(f"Error storing API key {key_name}: {e}")
            return False
    
    def get_api_key(self, key_name: str) -> Optional[str]:
        """Retrieve decrypted API key"""
        try:
            key_file = self.keys_dir / f"{key_name}.encrypted"
            
            if not key_file.exists():
                return None
            
            with open(key_file, 'r') as f:
                data = json.load(f)
            
            encrypted = data.get('encrypted_key')
            if not encrypted:
                return None
            
            return self.decrypt_sensitive_data(encrypted)
        except Exception as e:
            logger.error(f"Error retrieving API key {key_name}: {e}")
            return None
    
    def sign_request(self, data: Dict, secret: Optional[str] = None) -> str:
        """Sign request data for integrity verification"""
        if secret is None:
            secret = self.communication_key.decode('utf-8')
        
        # Create canonical string from sorted data
        canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
        
        # Create HMAC signature
        signature = hmac.new(
            secret.encode('utf-8'),
            canonical.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def verify_request(self, data: Dict, signature: str, secret: Optional[str] = None) -> bool:
        """Verify request signature"""
        try:
            expected_signature = self.sign_request(data, secret)
            return hmac.compare_digest(expected_signature, signature)
        except Exception as e:
            logger.error(f"Error verifying request signature: {e}")
            return False
    
    def secure_log(self, message: str, sensitive_keys: Optional[list] = None):
        """Log message without sensitive data"""
        if sensitive_keys is None:
            sensitive_keys = ['password', 'api_key', 'token', 'secret', 'key']
        
        # Remove sensitive data from log message
        safe_message = message
        for key in sensitive_keys:
            # Simple pattern matching to remove sensitive values
            import re
            pattern = rf'\b{key}\s*[:=]\s*["\']?([^"\'\s]+)["\']?'
            safe_message = re.sub(pattern, f'{key}=***REDACTED***', safe_message, flags=re.IGNORECASE)
        
        logger.info(safe_message)
    
    def create_secure_token(self, user_id: int, expiration_seconds: int = 3600) -> str:
        """Create secure token for user session"""
        payload = {
            'user_id': user_id,
            'timestamp': time.time(),
            'expires_at': time.time() + expiration_seconds
        }
        
        # Create token with signature
        token_data = json.dumps(payload, sort_keys=True)
        signature = self.sign_request(payload)
        
        # Combine payload and signature
        token = base64.urlsafe_b64encode(
            f"{token_data}:{signature}".encode('utf-8')
        ).decode('utf-8')
        
        return token
    
    def verify_secure_token(self, token: str) -> Optional[Dict]:
        """Verify and decode secure token"""
        try:
            decoded = base64.urlsafe_b64decode(token.encode('utf-8')).decode('utf-8')
            token_data, signature = decoded.split(':', 1)
            
            payload = json.loads(token_data)
            
            # Verify signature
            if not self.verify_request(payload, signature):
                logger.warning("Token signature verification failed")
                return None
            
            # Check expiration
            if time.time() > payload.get('expires_at', 0):
                logger.warning("Token expired")
                return None
            
            return payload
        except Exception as e:
            logger.error(f"Error verifying token: {e}")
            return None


# Global secure communication instance
_secure_comm_instance = None

def get_secure_communication(workspace_root: Optional[str] = None) -> SecureCommunication:
    """Get or create global secure communication instance"""
    global _secure_comm_instance
    if _secure_comm_instance is None:
        _secure_comm_instance = SecureCommunication(workspace_root)
    return _secure_comm_instance
