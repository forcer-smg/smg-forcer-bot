# -*- coding: utf-8 -*-
"""
Approval Manager - Human-in-the-loop permission system
Manages action approvals with Telegram inline keyboards
"""

import os
import json
import uuid
import logging
import asyncio
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class ApprovalStatus(Enum):
    """Approval status"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    EXPIRED = "expired"


class ActionType(Enum):
    """Type of action requiring approval"""
    FILE_MODIFY = "file_modify"
    FILE_DELETE = "file_delete"
    COMMAND_EXECUTE = "command_execute"
    TOOL_INSTALL = "tool_install"
    SYSTEM_CHANGE = "system_change"
    NETWORK_OPERATION = "network_operation"
    BROWSER_ACTION = "browser_action"


class ApprovalRequest:
    """Represents an approval request"""
    
    def __init__(self, action_type: ActionType, description: str, details: Dict,
                 user_id: int, timeout: int = 300):
        """
        Initialize approval request
        action_type: Type of action
        description: Human-readable description
        details: Action details (command, file path, etc.)
        user_id: Telegram user ID
        timeout: Timeout in seconds (default 5 minutes)
        """
        self.request_id = str(uuid.uuid4())
        self.action_type = action_type
        self.description = description
        self.details = details
        self.user_id = user_id
        self.status = ApprovalStatus.PENDING
        self.created_at = datetime.now()
        self.expires_at = self.created_at + timedelta(seconds=timeout)
        self.approved_at = None
        self.rejected_at = None
        self.reason = None
    
    def is_expired(self) -> bool:
        """Check if request has expired"""
        return datetime.now() > self.expires_at
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'request_id': self.request_id,
            'action_type': self.action_type.value,
            'description': self.description,
            'details': self.details,
            'user_id': self.user_id,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'expires_at': self.expires_at.isoformat(),
            'approved_at': self.approved_at.isoformat() if self.approved_at else None,
            'rejected_at': self.rejected_at.isoformat() if self.rejected_at else None,
            'reason': self.reason
        }


class ApprovalManager:
    """Manages approval requests and user confirmations"""
    
    def __init__(self, workspace_root: Optional[str] = None):
        """
        Initialize approval manager
        workspace_root: Directory for storing approval history
        """
        self.workspace_root = Path(workspace_root) if workspace_root else Path(os.getcwd())
        self.approvals_dir = self.workspace_root / "approvals"
        self.approvals_dir.mkdir(exist_ok=True)
        
        # Active approval requests
        self.pending_requests: Dict[str, ApprovalRequest] = {}
        
        # Approval history
        self.history_file = self.approvals_dir / "approval_history.json"
        self.history: List[Dict] = []
        self._load_history()
        
        # Auto-approval whitelist/blacklist
        self.whitelist: List[str] = []  # Actions that don't need approval
        self.blacklist: List[str] = []  # Actions that always need approval
        
        # Approval callbacks (action_type -> callback)
        self.callbacks: Dict[ActionType, Callable] = {}
        
        # Default timeout (5 minutes)
        self.default_timeout = 300
    
    def _load_history(self):
        """Load approval history from file"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
            except Exception as e:
                logger.error(f"Error loading approval history: {e}")
                self.history = []
    
    def _save_history(self):
        """Save approval history to file"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving approval history: {e}")
    
    def requires_approval(self, action_type: ActionType, details: Dict) -> bool:
        """Check if action requires approval"""
        # Check blacklist first
        action_key = f"{action_type.value}:{details.get('command', details.get('path', ''))}"
        for blacklisted in self.blacklist:
            if blacklisted in action_key:
                return True
        
        # Check whitelist
        for whitelisted in self.whitelist:
            if whitelisted in action_key:
                return False
        
        # Default: require approval for dangerous actions
        dangerous_types = [
            ActionType.FILE_DELETE,
            ActionType.SYSTEM_CHANGE,
            ActionType.NETWORK_OPERATION
        ]
        
        return action_type in dangerous_types
    
    def create_approval_request(self, action_type: ActionType, description: str,
                               details: Dict, user_id: int, timeout: Optional[int] = None) -> ApprovalRequest:
        """Create a new approval request"""
        request = ApprovalRequest(
            action_type=action_type,
            description=description,
            details=details,
            user_id=user_id,
            timeout=timeout or self.default_timeout
        )
        
        self.pending_requests[request.request_id] = request
        logger.info(f"Created approval request: {request.request_id} for {action_type.value}")
        
        return request
    
    def get_approval_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get approval request by ID"""
        return self.pending_requests.get(request_id)
    
    def approve(self, request_id: str, reason: Optional[str] = None) -> bool:
        """Approve a request"""
        request = self.pending_requests.get(request_id)
        if not request:
            return False
        
        if request.is_expired():
            request.status = ApprovalStatus.EXPIRED
            self._finalize_request(request)
            return False
        
        request.status = ApprovalStatus.APPROVED
        request.approved_at = datetime.now()
        request.reason = reason
        
        # Execute callback if registered
        if request.action_type in self.callbacks:
            try:
                self.callbacks[request.action_type](request)
            except Exception as e:
                logger.error(f"Error executing approval callback: {e}")
        
        self._finalize_request(request)
        logger.info(f"Approval request {request_id} approved")
        return True
    
    def reject(self, request_id: str, reason: Optional[str] = None) -> bool:
        """Reject a request"""
        request = self.pending_requests.get(request_id)
        if not request:
            return False
        
        request.status = ApprovalStatus.REJECTED
        request.rejected_at = datetime.now()
        request.reason = reason
        
        self._finalize_request(request)
        logger.info(f"Approval request {request_id} rejected: {reason}")
        return True
    
    def _finalize_request(self, request: ApprovalRequest):
        """Finalize request and move to history"""
        self.history.append(request.to_dict())
        if request.request_id in self.pending_requests:
            del self.pending_requests[request.request_id]
        self._save_history()
    
    async def wait_for_approval(self, request_id: str, timeout: Optional[int] = None) -> ApprovalStatus:
        """Wait for approval decision (async)"""
        request = self.pending_requests.get(request_id)
        if not request:
            return ApprovalStatus.REJECTED
        
        timeout = timeout or self.default_timeout
        start_time = datetime.now()
        
        while datetime.now() - start_time < timedelta(seconds=timeout):
            request = self.pending_requests.get(request_id)
            if not request:
                return ApprovalStatus.REJECTED
            
            if request.status != ApprovalStatus.PENDING:
                return request.status
            
            if request.is_expired():
                request.status = ApprovalStatus.TIMEOUT
                self._finalize_request(request)
                return ApprovalStatus.TIMEOUT
            
            await asyncio.sleep(1)  # Check every second
        
        # Timeout
        request = self.pending_requests.get(request_id)
        if request:
            request.status = ApprovalStatus.TIMEOUT
            self._finalize_request(request)
        return ApprovalStatus.TIMEOUT
    
    def format_approval_message(self, request: ApprovalRequest) -> str:
        """Format approval request as Telegram message"""
        message = f"🔐 **Approval Required**\n\n"
        message += f"**Action:** {request.action_type.value.replace('_', ' ').title()}\n"
        message += f"**Description:** {request.description}\n\n"
        
        # Add details
        if request.details.get('command'):
            message += f"**Command:**\n```bash\n{request.details['command']}\n```\n"
        if request.details.get('path'):
            message += f"**Path:** `{request.details['path']}`\n"
        if request.details.get('tool'):
            message += f"**Tool:** `{request.details['tool']}`\n"
        
        # Add expiration info
        time_left = (request.expires_at - datetime.now()).total_seconds()
        if time_left > 0:
            minutes = int(time_left / 60)
            message += f"\n⏰ Expires in {minutes} minute(s)"
        
        return message
    
    def create_inline_keyboard(self, request_id: str) -> List[List[Dict]]:
        """Create Telegram inline keyboard for approval"""
        return [
            [
                {'text': '✅ Approve', 'callback_data': f'approve:{request_id}'},
                {'text': '❌ Reject', 'callback_data': f'reject:{request_id}'}
            ]
        ]
    
    def register_callback(self, action_type: ActionType, callback: Callable):
        """Register callback to execute when action is approved"""
        self.callbacks[action_type] = callback
    
    def get_user_approval_history(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Get approval history for user"""
        user_history = [
            entry for entry in self.history
            if entry.get('user_id') == user_id
        ]
        return sorted(user_history, key=lambda x: x.get('created_at', ''), reverse=True)[:limit]
    
    def add_to_whitelist(self, pattern: str):
        """Add pattern to auto-approval whitelist"""
        if pattern not in self.whitelist:
            self.whitelist.append(pattern)
            logger.info(f"Added to whitelist: {pattern}")
    
    def add_to_blacklist(self, pattern: str):
        """Add pattern to approval blacklist (always require approval)"""
        if pattern not in self.blacklist:
            self.blacklist.append(pattern)
            logger.info(f"Added to blacklist: {pattern}")
    
    def cleanup_expired(self):
        """Clean up expired pending requests"""
        expired_ids = []
        for request_id, request in self.pending_requests.items():
            if request.is_expired():
                expired_ids.append(request_id)
        
        for request_id in expired_ids:
            request = self.pending_requests[request_id]
            request.status = ApprovalStatus.EXPIRED
            self._finalize_request(request)
        
        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired approval requests")


# Global approval manager instance
_approval_instance = None

def get_approval_manager(workspace_root: Optional[str] = None) -> ApprovalManager:
    """Get or create global approval manager instance"""
    global _approval_instance
    if _approval_instance is None:
        _approval_instance = ApprovalManager(workspace_root)
    return _approval_instance
