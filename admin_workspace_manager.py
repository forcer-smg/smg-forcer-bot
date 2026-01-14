# -*- coding: utf-8 -*-
"""
Admin Workspace Manager - Admin tools for managing all user workspaces and services
"""

import os
import logging
import psutil
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class AdminWorkspaceManager:
    """Admin workspace and service management"""
    
    def __init__(self, database=None, workspace_root: str = None):
        """
        Initialize admin workspace manager
        
        Args:
            database: Database instance
            workspace_root: Root directory for workspaces
        """
        if not database:
            from database_hybrid import Database
            database = Database()
        
        self.database = database
        self.workspace_root = Path(workspace_root) if workspace_root else Path.cwd()
        self.logger = logger
    
    def list_all_workspaces(self) -> List[Dict]:
        """
        List all user workspaces with metadata
        
        Returns:
            List of workspace information dicts
        """
        try:
            workspaces = self.database.get_all_user_workspaces()
            
            # Enhance with filesystem information
            for workspace in workspaces:
                user_id = workspace['user_id']
                user_workspace = self.workspace_root / f"user_{user_id}"
                
                if user_workspace.exists():
                    workspace['workspace_path'] = str(user_workspace)
                    workspace['workspace_size'] = self._calculate_directory_size(user_workspace)
                    workspace['workspace_exists'] = True
                else:
                    workspace['workspace_path'] = None
                    workspace['workspace_size'] = 0
                    workspace['workspace_exists'] = False
            
            return workspaces
        except Exception as e:
            self.logger.error(f"Error listing workspaces: {e}")
            return []
    
    def get_workspace_details(self, user_id: int) -> Dict:
        """
        Get detailed workspace info for a user
        
        Args:
            user_id: User ID
        
        Returns:
            Dict with detailed workspace information
        """
        details = {
            'user_id': user_id,
            'workspace_path': None,
            'exists': False,
            'size': 0,
            'file_count': 0,
            'project_types': {},
            'projects': [],
            'active_services': [],
            'hosting_detected': False,
            'hosting_info': {}
        }
        
        try:
            # Get user info
            user = self.database.get_user(user_id)
            if user:
                details['username'] = user.get('username')
                details['first_name'] = user.get('first_name')
            
            # Check workspace
            user_workspace = self.workspace_root / f"user_{user_id}"
            if user_workspace.exists():
                details['workspace_path'] = str(user_workspace)
                details['exists'] = True
                details['size'] = self._calculate_directory_size(user_workspace)
                details['file_count'] = self._count_files(user_workspace)
                
                # Analyze projects
                from workspace_intelligence import get_workspace_intelligence
                intel = get_workspace_intelligence(str(user_workspace))
                scan_result = intel.scan_workspace(str(user_workspace))
                details['projects'] = scan_result.get('projects', [])
                details['project_types'] = scan_result.get('project_types', {})
            
            # Get active services
            services = self.database.list_user_services(user_id)
            details['active_services'] = [s for s in services if s.get('status') == 'running']
            
            # Check for hosting
            hosting_info = self.scan_workspace_for_hosting(user_id)
            details['hosting_detected'] = hosting_info.get('hosting_detected', False)
            details['hosting_info'] = hosting_info
            
        except Exception as e:
            self.logger.error(f"Error getting workspace details: {e}")
            details['error'] = str(e)
        
        return details
    
    def scan_workspace_for_hosting(self, user_id: int) -> Dict:
        """
        Detect if user is hosting services
        
        Args:
            user_id: User ID
        
        Returns:
            Dict with hosting detection information
        """
        hosting_info = {
            'hosting_detected': False,
            'running_processes': [],
            'open_ports': [],
            'web_servers': [],
            'background_services': []
        }
        
        try:
            # Check database for services
            services = self.database.list_user_services(user_id)
            running_services = [s for s in services if s.get('status') == 'running']
            
            if running_services:
                hosting_info['hosting_detected'] = True
                hosting_info['background_services'] = running_services
            
            # Check for running processes in workspace
            user_workspace = self.workspace_root / f"user_{user_id}"
            if user_workspace.exists():
                workspace_str = str(user_workspace)
                
                for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'connections']):
                    try:
                        cmdline = ' '.join(proc.info['cmdline'] or [])
                        if workspace_str in cmdline:
                            hosting_info['hosting_detected'] = True
                            process_info = {
                                'pid': proc.info['pid'],
                                'name': proc.info['name'],
                                'command': cmdline
                            }
                            
                            # Check for open ports
                            connections = proc.info.get('connections')
                            if connections:
                                for conn in connections:
                                    if conn.status == 'LISTEN':
                                        process_info['port'] = conn.laddr.port
                                        hosting_info['open_ports'].append(conn.laddr.port)
                            
                            # Detect web servers
                            if any(server in cmdline.lower() for server in ['nginx', 'apache', 'httpd', 'python -m http.server', 'node', 'php']):
                                hosting_info['web_servers'].append(process_info)
                            
                            hosting_info['running_processes'].append(process_info)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
        
        except Exception as e:
            self.logger.error(f"Error scanning for hosting: {e}")
            hosting_info['error'] = str(e)
        
        return hosting_info
    
    def get_workspace_statistics(self) -> Dict:
        """
        Get overall workspace statistics
        
        Returns:
            Dict with statistics
        """
        stats = {
            'total_workspaces': 0,
            'total_size': 0,
            'active_services_count': 0,
            'total_projects': 0,
            'projects_by_type': {},
            'users_with_hosting': 0
        }
        
        try:
            # Get all workspaces
            workspaces = self.list_all_workspaces()
            stats['total_workspaces'] = len(workspaces)
            
            # Calculate totals
            for workspace in workspaces:
                if workspace.get('workspace_exists'):
                    stats['total_size'] += workspace.get('workspace_size', 0)
                
                stats['total_projects'] += workspace.get('project_count', 0)
                stats['active_services_count'] += workspace.get('service_count', 0)
                
                # Check for hosting
                user_id = workspace['user_id']
                hosting_info = self.scan_workspace_for_hosting(user_id)
                if hosting_info.get('hosting_detected'):
                    stats['users_with_hosting'] += 1
            
            # Get all services
            all_services = self.database.get_all_services()
            stats['active_services_count'] = len([s for s in all_services if s.get('status') == 'running'])
            
            # Get all projects
            all_projects = self.database.get_all_projects()
            stats['total_projects'] = len(all_projects)
            
            # Count projects by type
            for project in all_projects:
                metadata = project.get('metadata', {})
                if isinstance(metadata, str):
                    import json
                    try:
                        metadata = json.loads(metadata)
                    except:
                        metadata = {}
                project_type = metadata.get('project_type', 'unknown')
                stats['projects_by_type'][project_type] = stats['projects_by_type'].get(project_type, 0) + 1
        
        except Exception as e:
            self.logger.error(f"Error getting statistics: {e}")
            stats['error'] = str(e)
        
        return stats
    
    def delete_user_project(self, user_id: int, project_name: str) -> bool:
        """Delete user's project (admin only)"""
        try:
            return self.database.delete_project(user_id, project_name)
        except Exception as e:
            self.logger.error(f"Error deleting project: {e}")
            return False
    
    def stop_user_service(self, user_id: int, service_name: str) -> bool:
        """Stop user's service (admin only)"""
        try:
            from service_manager import get_service_manager
            service_mgr = get_service_manager(str(self.workspace_root))
            
            # Get service info
            service = self.database.get_service(user_id, service_name)
            if service:
                pid = service.get('pid')
                if pid:
                    success = service_mgr.stop_service(service_name, user_id, pid)
                    if success:
                        self.database.update_service_status(user_id, service_name, 'stopped')
                    return success
            
            return False
        except Exception as e:
            self.logger.error(f"Error stopping service: {e}")
            return False
    
    def delete_user_service(self, user_id: int, service_name: str) -> bool:
        """Delete user's service (admin only)"""
        try:
            # Stop service first
            self.stop_user_service(user_id, service_name)
            
            # Delete from database
            return self.database.delete_service(user_id, service_name)
        except Exception as e:
            self.logger.error(f"Error deleting service: {e}")
            return False
    
    def _calculate_directory_size(self, directory: Path) -> int:
        """Calculate total size of directory"""
        total_size = 0
        try:
            for item in directory.rglob('*'):
                if item.is_file():
                    try:
                        total_size += item.stat().st_size
                    except:
                        pass
        except Exception as e:
            self.logger.debug(f"Error calculating directory size: {e}")
        return total_size
    
    def _count_files(self, directory: Path) -> int:
        """Count files in directory"""
        count = 0
        try:
            for item in directory.rglob('*'):
                if item.is_file():
                    count += 1
        except Exception as e:
            self.logger.debug(f"Error counting files: {e}")
        return count


# Global instance
_admin_workspace_manager_instance = None

def get_admin_workspace_manager(database=None, workspace_root: str = None) -> AdminWorkspaceManager:
    """Get or create global admin workspace manager instance"""
    global _admin_workspace_manager_instance
    if _admin_workspace_manager_instance is None:
        _admin_workspace_manager_instance = AdminWorkspaceManager(database, workspace_root)
    return _admin_workspace_manager_instance
