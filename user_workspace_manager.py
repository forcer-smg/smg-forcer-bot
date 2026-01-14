# -*- coding: utf-8 -*-
"""
User Workspace Manager - Ensures complete isolation between Telegram users
Prevents conflicts when multiple users use the bot simultaneously
"""

import os
import threading
from pathlib import Path
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class UserWorkspaceManager:
    """Manages isolated workspaces for each Telegram user"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self, base_workspace: Optional[str] = None):
        """Initialize workspace manager"""
        if base_workspace:
            self.base_workspace = Path(base_workspace)
        else:
            # Default to current directory or environment variable
            workspace_env = os.getenv('WORKSPACE_ROOT', os.getcwd())
            self.base_workspace = Path(workspace_env)
        
        # Ensure base workspace exists
        self.base_workspace.mkdir(parents=True, exist_ok=True)
        
        # Track active user workspaces (user_id -> workspace_path)
        self._user_workspaces: Dict[int, Path] = {}
        self._workspace_lock = threading.Lock()
        
        logger.info(f"UserWorkspaceManager initialized with base: {self.base_workspace}")
    
    @classmethod
    def get_instance(cls, base_workspace: Optional[str] = None):
        """Get singleton instance"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(base_workspace)
        return cls._instance
    
    def get_user_workspace(self, user_id: int) -> Path:
        """Get or create isolated workspace for a user"""
        with self._workspace_lock:
            if user_id not in self._user_workspaces:
                # Create user-specific workspace
                user_workspace = self.base_workspace / f"user_{user_id}"
                user_workspace.mkdir(parents=True, exist_ok=True)
                
                # Create subdirectories for organization
                (user_workspace / "plans").mkdir(exist_ok=True)
                (user_workspace / "generated_files").mkdir(exist_ok=True)
                
                self._user_workspaces[user_id] = user_workspace
                logger.info(f"Created isolated workspace for user {user_id}: {user_workspace}")
            
            return self._user_workspaces[user_id]
    
    def cleanup_user_workspace(self, user_id: int, keep_files: bool = True):
        """Clean up user workspace (optional - for cleanup tasks)"""
        with self._workspace_lock:
            if user_id in self._user_workspaces:
                workspace = self._user_workspaces[user_id]
                if not keep_files:
                    # Remove workspace (use with caution!)
                    import shutil
                    try:
                        shutil.rmtree(workspace)
                        logger.info(f"Removed workspace for user {user_id}")
                    except Exception as e:
                        logger.error(f"Error removing workspace for user {user_id}: {e}")
                del self._user_workspaces[user_id]
    
    def get_all_user_workspaces(self) -> Dict[int, Path]:
        """Get all active user workspaces (for admin/debugging)"""
        with self._workspace_lock:
            return self._user_workspaces.copy()
    
    def get_user_projects_dir(self, user_id: int) -> Path:
        """Get projects directory for user"""
        user_workspace = self.get_user_workspace(user_id)
        projects_dir = user_workspace / "projects"
        projects_dir.mkdir(exist_ok=True)
        return projects_dir
    
    def get_project_path(self, user_id: int, project_name: str) -> Path:
        """Get path to specific project"""
        projects_dir = self.get_user_projects_dir(user_id)
        return projects_dir / project_name
    
    def ensure_project_structure(self, user_id: int, project_name: str) -> Path:
        """Create project directory structure if it doesn't exist"""
        project_path = self.get_project_path(user_id, project_name)
        project_path.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        (project_path / "files").mkdir(exist_ok=True)
        (project_path / "tasks").mkdir(exist_ok=True)
        
        return project_path

