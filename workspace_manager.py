# -*- coding: utf-8 -*-
"""
Workspace Manager - Multi-root workspace support
Manages multiple project directories and context switching
"""

import os
import json
import logging
from typing import Dict, List, Optional, Set
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class Workspace:
    """Represents a workspace/project"""
    
    def __init__(self, name: str, root_path: str, workspace_id: Optional[str] = None):
        """
        Initialize workspace
        name: Workspace name
        root_path: Root directory path
        workspace_id: Unique workspace ID
        """
        self.workspace_id = workspace_id or f"ws_{int(datetime.now().timestamp())}"
        self.name = name
        self.root_path = Path(root_path)
        self.root_path.mkdir(parents=True, exist_ok=True)
        
        # Workspace metadata
        self.metadata = {
            'created_at': datetime.now().isoformat(),
            'last_accessed': datetime.now().isoformat(),
            'file_extensions': set(),
            'detected_frameworks': [],
            'tools_used': []
        }
        
        # Workspace-specific settings
        self.settings = {
            'default_tools': [],
            'environment': {},
            'python_path': None
        }
    
    def to_dict(self) -> Dict:
        """Convert workspace to dictionary"""
        metadata = self.metadata.copy()
        metadata['file_extensions'] = list(metadata['file_extensions'])
        return {
            'workspace_id': self.workspace_id,
            'name': self.name,
            'root_path': str(self.root_path),
            'metadata': metadata,
            'settings': self.settings
        }
    
    def update_metadata(self, **kwargs):
        """Update workspace metadata"""
        self.metadata.update(kwargs)
        self.metadata['last_accessed'] = datetime.now().isoformat()
    
    def detect_frameworks(self) -> List[str]:
        """Detect frameworks used in workspace"""
        frameworks = []
        
        # Check for common framework files
        framework_indicators = {
            'django': ['manage.py', 'settings.py', 'wsgi.py'],
            'flask': ['app.py', 'application.py', 'flask_app.py'],
            'react': ['package.json', 'src/App.js', 'src/App.tsx'],
            'vue': ['vue.config.js', 'src/main.js'],
            'angular': ['angular.json', 'src/main.ts'],
            'node': ['package.json', 'node_modules'],
            'python': ['requirements.txt', 'setup.py', 'pyproject.toml'],
            'go': ['go.mod', 'go.sum'],
            'rust': ['Cargo.toml', 'Cargo.lock']
        }
        
        for framework, indicators in framework_indicators.items():
            for indicator in indicators:
                if (self.root_path / indicator).exists():
                    if framework not in frameworks:
                        frameworks.append(framework)
                    break
        
        self.metadata['detected_frameworks'] = frameworks
        return frameworks
    
    def scan_file_extensions(self) -> Set[str]:
        """Scan workspace for file extensions"""
        extensions = set()
        
        try:
            for root, dirs, files in os.walk(self.root_path):
                # Skip hidden directories and common ignore patterns
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'venv', '.git']]
                
                for file in files:
                    if '.' in file:
                        ext = '.' + file.split('.')[-1]
                        extensions.add(ext)
        except Exception as e:
            logger.error(f"Error scanning workspace: {e}")
        
        self.metadata['file_extensions'] = extensions
        return extensions


class WorkspaceManager:
    """Manages multiple workspaces"""
    
    def __init__(self, base_workspace_root: Optional[str] = None):
        """
        Initialize workspace manager
        base_workspace_root: Base directory for all workspaces
        """
        self.base_workspace_root = Path(base_workspace_root) if base_workspace_root else Path(os.getcwd())
        self.workspaces_dir = self.base_workspace_root / "workspaces"
        self.workspaces_dir.mkdir(exist_ok=True)
        
        # Workspace registry
        self.workspaces: Dict[str, Workspace] = {}
        self.current_workspace_id: Optional[str] = None
        
        # Workspace configuration file
        self.config_file = self.workspaces_dir / "workspaces.json"
        
        # Load workspaces
        self._load_workspaces()
    
    def _load_workspaces(self):
        """Load workspaces from configuration"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                    for ws_data in config.get('workspaces', []):
                        workspace = Workspace(
                            name=ws_data['name'],
                            root_path=ws_data['root_path'],
                            workspace_id=ws_data['workspace_id']
                        )
                        workspace.metadata = ws_data.get('metadata', workspace.metadata)
                        workspace.settings = ws_data.get('settings', workspace.settings)
                        # Convert file_extensions back to set
                        if 'file_extensions' in workspace.metadata:
                            workspace.metadata['file_extensions'] = set(workspace.metadata['file_extensions'])
                        
                        self.workspaces[workspace.workspace_id] = workspace
                    
                    self.current_workspace_id = config.get('current_workspace_id')
            except Exception as e:
                logger.error(f"Error loading workspaces: {e}")
    
    def _save_workspaces(self):
        """Save workspaces to configuration"""
        try:
            config = {
                'workspaces': [ws.to_dict() for ws in self.workspaces.values()],
                'current_workspace_id': self.current_workspace_id
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving workspaces: {e}")
    
    def create_workspace(self, name: str, root_path: Optional[str] = None) -> Workspace:
        """Create a new workspace"""
        if root_path is None:
            # Create workspace in workspaces directory
            root_path = self.workspaces_dir / name
        else:
            root_path = Path(root_path)
        
        workspace = Workspace(name=name, root_path=str(root_path))
        self.workspaces[workspace.workspace_id] = workspace
        
        # Auto-detect frameworks and extensions
        workspace.detect_frameworks()
        workspace.scan_file_extensions()
        
        self._save_workspaces()
        logger.info(f"Created workspace: {name} ({workspace.workspace_id})")
        
        return workspace
    
    def get_workspace(self, workspace_id: Optional[str] = None) -> Optional[Workspace]:
        """Get workspace by ID, or current workspace if None"""
        if workspace_id is None:
            workspace_id = self.current_workspace_id
        
        if workspace_id:
            return self.workspaces.get(workspace_id)
        
        return None
    
    def set_current_workspace(self, workspace_id: str) -> bool:
        """Set current workspace"""
        if workspace_id in self.workspaces:
            self.current_workspace_id = workspace_id
            workspace = self.workspaces[workspace_id]
            workspace.update_metadata()
            self._save_workspaces()
            logger.info(f"Switched to workspace: {workspace.name}")
            return True
        return False
    
    def get_current_workspace(self) -> Optional[Workspace]:
        """Get current workspace"""
        return self.get_workspace()
    
    def list_workspaces(self) -> List[Workspace]:
        """List all workspaces"""
        return list(self.workspaces.values())
    
    def delete_workspace(self, workspace_id: str) -> bool:
        """Delete workspace (does not delete files, just removes from registry)"""
        if workspace_id in self.workspaces:
            del self.workspaces[workspace_id]
            if self.current_workspace_id == workspace_id:
                self.current_workspace_id = None
            self._save_workspaces()
            logger.info(f"Deleted workspace: {workspace_id}")
            return True
        return False
    
    def find_workspace_by_path(self, path: str) -> Optional[Workspace]:
        """Find workspace containing given path"""
        path = Path(path).resolve()
        
        for workspace in self.workspaces.values():
            try:
                workspace_path = Path(workspace.root_path).resolve()
                if str(path).startswith(str(workspace_path)):
                    return workspace
            except Exception:
                continue
        
        return None
    
    def get_workspace_context(self, workspace_id: Optional[str] = None) -> Dict:
        """Get context information for workspace"""
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            return {}
        
        return {
            'workspace_id': workspace.workspace_id,
            'name': workspace.name,
            'root_path': str(workspace.root_path),
            'frameworks': workspace.metadata.get('detected_frameworks', []),
            'file_extensions': list(workspace.metadata.get('file_extensions', [])),
            'tools_used': workspace.metadata.get('tools_used', []),
            'settings': workspace.settings
        }


# Global workspace manager instance
_workspace_instance = None

def get_workspace_manager(base_workspace_root: Optional[str] = None) -> WorkspaceManager:
    """Get or create global workspace manager instance"""
    global _workspace_instance
    if _workspace_instance is None:
        _workspace_instance = WorkspaceManager(base_workspace_root)
    return _workspace_instance
