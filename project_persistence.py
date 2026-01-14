# -*- coding: utf-8 -*-
"""
Project Persistence - Save and restore user projects across redeployments
"""

import os
import tarfile
import logging
import tempfile
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime
import io

logger = logging.getLogger(__name__)


class ProjectPersistence:
    """Manage project save/restore functionality"""
    
    def __init__(self, database=None):
        """
        Initialize project persistence
        
        Args:
            database: Database instance (optional, will import if not provided)
        """
        self.database = database
        self.logger = logger
    
    def save_project(self, user_id: int, project_name: str, workspace_path: str, metadata: Dict = None) -> bool:
        """
        Save project to database as compressed archive
        
        Args:
            user_id: User ID
            project_name: Name of project
            workspace_path: Path to workspace directory
            metadata: Additional metadata (project type, file count, etc.)
        
        Returns:
            True if saved successfully
        """
        if not self.database:
            from database_hybrid import Database
            self.database = Database()
        
        workspace = Path(workspace_path)
        if not workspace.exists() or not workspace.is_dir():
            self.logger.error(f"Workspace does not exist: {workspace_path}")
            return False
        
        try:
            # Create compressed archive
            archive_data = self._create_archive(workspace)
            
            # Prepare metadata
            project_metadata = {
                'project_type': self._detect_project_type(workspace),
                'file_count': self._count_files(workspace),
                'total_size': self._calculate_size(workspace),
                'saved_at': datetime.now().isoformat(),
                **(metadata or {})
            }
            
            # Save to database
            success = self.database.save_project(
                user_id=user_id,
                project_name=project_name,
                workspace_path=str(workspace),
                project_data=archive_data,
                metadata=project_metadata
            )
            
            if success:
                self.logger.info(f"Project {project_name} saved for user {user_id}")
            else:
                self.logger.error(f"Failed to save project {project_name} for user {user_id}")
            
            return success
        
        except Exception as e:
            self.logger.error(f"Error saving project: {e}", exc_info=True)
            return False
    
    def restore_project(self, user_id: int, project_name: str, target_path: str = None) -> bool:
        """
        Restore project from database
        
        Args:
            user_id: User ID
            project_name: Name of project to restore
            target_path: Target directory (default: original workspace_path from metadata)
        
        Returns:
            True if restored successfully
        """
        if not self.database:
            from database_hybrid import Database
            self.database = Database()
        
        try:
            # Get project from database
            project = self.database.get_project(user_id, project_name)
            if not project:
                self.logger.error(f"Project {project_name} not found for user {user_id}")
                return False
            
            # Determine target path
            if not target_path:
                target_path = project.get('workspace_path')
                if not target_path:
                    self.logger.error("No target path specified and project has no workspace_path")
                    return False
            
            target = Path(target_path)
            target.mkdir(parents=True, exist_ok=True)
            
            # Extract archive
            archive_data = project.get('project_data')
            if not archive_data:
                self.logger.error(f"Project {project_name} has no archive data")
                return False
            
            success = self._extract_archive(archive_data, target)
            
            if success:
                self.logger.info(f"Project {project_name} restored to {target_path} for user {user_id}")
            else:
                self.logger.error(f"Failed to restore project {project_name} for user {user_id}")
            
            return success
        
        except Exception as e:
            self.logger.error(f"Error restoring project: {e}", exc_info=True)
            return False
    
    def list_projects(self, user_id: int) -> List[Dict]:
        """List all saved projects for a user"""
        if not self.database:
            from database_hybrid import Database
            self.database = Database()
        
        try:
            return self.database.list_user_projects(user_id)
        except Exception as e:
            self.logger.error(f"Error listing projects: {e}")
            return []
    
    def delete_project(self, user_id: int, project_name: str) -> bool:
        """Delete saved project"""
        if not self.database:
            from database_hybrid import Database
            self.database = Database()
        
        try:
            return self.database.delete_project(user_id, project_name)
        except Exception as e:
            self.logger.error(f"Error deleting project: {e}")
            return False
    
    def _create_archive(self, workspace: Path) -> bytes:
        """Create compressed tar.gz archive of workspace"""
        archive_buffer = io.BytesIO()
        
        with tarfile.open(fileobj=archive_buffer, mode='w:gz') as tar:
            # Add all files in workspace
            for item in workspace.rglob('*'):
                if item.is_file():
                    try:
                        # Get relative path from workspace root
                        arcname = item.relative_to(workspace)
                        tar.add(item, arcname=arcname, recursive=False)
                    except Exception as e:
                        self.logger.warning(f"Could not add {item} to archive: {e}")
        
        archive_buffer.seek(0)
        return archive_buffer.read()
    
    def _extract_archive(self, archive_data: bytes, target: Path) -> bool:
        """Extract compressed tar.gz archive to target directory"""
        try:
            archive_buffer = io.BytesIO(archive_data)
            
            with tarfile.open(fileobj=archive_buffer, mode='r:gz') as tar:
                tar.extractall(path=target)
            
            return True
        except Exception as e:
            self.logger.error(f"Error extracting archive: {e}")
            return False
    
    def _detect_project_type(self, workspace: Path) -> str:
        """Detect project type"""
        from workspace_intelligence import get_workspace_intelligence
        intel = get_workspace_intelligence(str(workspace))
        return intel.analyze_project_type(str(workspace))
    
    def _count_files(self, workspace: Path) -> int:
        """Count files in workspace"""
        count = 0
        try:
            for item in workspace.rglob('*'):
                if item.is_file():
                    count += 1
        except Exception as e:
            self.logger.warning(f"Error counting files: {e}")
        return count
    
    def _calculate_size(self, workspace: Path) -> int:
        """Calculate total size of workspace"""
        total_size = 0
        try:
            for item in workspace.rglob('*'):
                if item.is_file():
                    try:
                        total_size += item.stat().st_size
                    except:
                        pass
        except Exception as e:
            self.logger.warning(f"Error calculating size: {e}")
        return total_size


# Global instance
_project_persistence_instance = None

def get_project_persistence(database=None) -> ProjectPersistence:
    """Get or create global project persistence instance"""
    global _project_persistence_instance
    if _project_persistence_instance is None:
        _project_persistence_instance = ProjectPersistence(database)
    return _project_persistence_instance
