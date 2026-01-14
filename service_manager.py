# -*- coding: utf-8 -*-
"""
Service Manager - Manage long-running services (evilginx, web servers, etc.)
Handles starting, stopping, monitoring, and tracking background services
"""

import os
import subprocess
import psutil
import logging
import signal
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class ServiceManager:
    """Manage long-running services for users"""
    
    def __init__(self, workspace_root: str = None):
        """
        Initialize service manager
        
        Args:
            workspace_root: Root directory for service workspaces
        """
        self.workspace_root = Path(workspace_root) if workspace_root else Path.cwd()
        self.logs_dir = self.workspace_root / "service_logs"
        self.logs_dir.mkdir(exist_ok=True, parents=True)
        self.logger = logger
    
    def start_service(self, service_name: str, command: str, workspace: str, user_id: int, metadata: Dict = None) -> Dict:
        """
        Start service in background, return PID and status
        
        Args:
            service_name: Unique name for the service
            command: Command to run (can include arguments)
            workspace: Workspace directory where service runs
            user_id: User ID who owns the service
            metadata: Additional metadata (port, URL, etc.)
        
        Returns:
            Dict with service info including PID, status, logs_path
        """
        workspace_path = Path(workspace)
        workspace_path.mkdir(exist_ok=True, parents=True)
        
        # Create log file
        log_file = self.logs_dir / f"{user_id}_{service_name}.log"
        
        service_info = {
            'service_name': service_name,
            'command': command,
            'workspace': str(workspace_path),
            'user_id': user_id,
            'status': 'starting',
            'started_at': datetime.now().isoformat(),
            'log_file': str(log_file),
            'metadata': metadata or {}
        }
        
        try:
            # Check if service already running
            existing = self.get_service_by_name(service_name, user_id)
            if existing and existing.get('pid') and self._is_process_running(existing['pid']):
                self.logger.warning(f"Service {service_name} already running with PID {existing['pid']}")
                service_info['status'] = 'running'
                service_info['pid'] = existing['pid']
                service_info['message'] = 'Service already running'
                return service_info
            
            # Prepare command
            # Use nohup for background execution, redirect output to log file
            if command.startswith('nohup') or '&' in command:
                # Command already has background execution
                full_command = f"cd {workspace_path} && {command}"
            else:
                # Add nohup and background execution
                full_command = f"cd {workspace_path} && nohup {command} > {log_file} 2>&1 &"
            
            # Start process
            process = subprocess.Popen(
                full_command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(workspace_path),
                preexec_fn=os.setsid  # Create new process group
            )
            
            # Get PID (may need to extract from process or use pgrep)
            pid = process.pid
            
            # Wait a moment to check if process started successfully
            import time
            time.sleep(0.5)
            
            if self._is_process_running(pid):
                service_info['status'] = 'running'
                service_info['pid'] = pid
                service_info['message'] = 'Service started successfully'
                self.logger.info(f"Service {service_name} started with PID {pid}")
            else:
                service_info['status'] = 'error'
                service_info['message'] = 'Service failed to start'
                self.logger.error(f"Service {service_name} failed to start")
        
        except Exception as e:
            self.logger.error(f"Error starting service {service_name}: {e}")
            service_info['status'] = 'error'
            service_info['error'] = str(e)
            service_info['message'] = f'Error starting service: {e}'
        
        return service_info
    
    def stop_service(self, service_name: str, user_id: int = None, pid: int = None) -> bool:
        """
        Stop service by name or PID
        
        Args:
            service_name: Name of service to stop
            user_id: User ID (optional, for verification)
            pid: Process ID (optional, if known)
        
        Returns:
            True if stopped successfully, False otherwise
        """
        try:
            if pid:
                # Stop by PID
                if self._is_process_running(pid):
                    try:
                        # Try graceful termination first
                        os.killpg(os.getpgid(pid), signal.SIGTERM)
                        import time
                        time.sleep(1)
                        
                        # Force kill if still running
                        if self._is_process_running(pid):
                            os.killpg(os.getpgid(pid), signal.SIGKILL)
                        
                        self.logger.info(f"Stopped service with PID {pid}")
                        return True
                    except ProcessLookupError:
                        # Process already dead
                        return True
                    except Exception as e:
                        self.logger.error(f"Error stopping process {pid}: {e}")
                        return False
                else:
                    return True  # Already stopped
            
            # Find process by name/command
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if service_name.lower() in cmdline.lower():
                        proc_pid = proc.info['pid']
                        proc.terminate()
                        import time
                        time.sleep(1)
                        if proc.is_running():
                            proc.kill()
                        self.logger.info(f"Stopped service {service_name} (PID {proc_pid})")
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            self.logger.warning(f"Service {service_name} not found")
            return False
        
        except Exception as e:
            self.logger.error(f"Error stopping service {service_name}: {e}")
            return False
    
    def get_service_status(self, service_name: str, user_id: int = None, pid: int = None) -> Dict:
        """
        Get service status (running, stopped, error)
        
        Args:
            service_name: Name of service
            user_id: User ID (optional)
            pid: Process ID (optional)
        
        Returns:
            Dict with service status information
        """
        status = {
            'service_name': service_name,
            'status': 'unknown',
            'pid': pid,
            'running': False,
            'cpu_percent': 0.0,
            'memory_mb': 0.0,
            'uptime_seconds': 0
        }
        
        try:
            if pid and self._is_process_running(pid):
                process = psutil.Process(pid)
                status['status'] = 'running'
                status['running'] = True
                status['pid'] = pid
                status['cpu_percent'] = process.cpu_percent(interval=0.1)
                status['memory_mb'] = process.memory_info().rss / 1024 / 1024
                
                # Calculate uptime
                create_time = process.create_time()
                uptime = datetime.now().timestamp() - create_time
                status['uptime_seconds'] = int(uptime)
            else:
                status['status'] = 'stopped'
                status['running'] = False
        
        except psutil.NoSuchProcess:
            status['status'] = 'stopped'
            status['running'] = False
        except Exception as e:
            self.logger.error(f"Error getting service status: {e}")
            status['status'] = 'error'
            status['error'] = str(e)
        
        return status
    
    def list_services(self, user_id: int = None) -> List[Dict]:
        """
        List all active services
        
        Args:
            user_id: Filter by user ID (None = all users)
        
        Returns:
            List of service information dicts
        """
        services = []
        
        try:
            # This will be populated from database in actual implementation
            # For now, scan running processes
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
                try:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    
                    # Check if it's a service (running in workspace)
                    if self.workspace_root and str(self.workspace_root) in cmdline:
                        service_info = {
                            'pid': proc.info['pid'],
                            'name': proc.info['name'],
                            'command': cmdline,
                            'status': 'running',
                            'started_at': datetime.fromtimestamp(proc.info['create_time']).isoformat()
                        }
                        services.append(service_info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        
        except Exception as e:
            self.logger.error(f"Error listing services: {e}")
        
        return services
    
    def get_service_logs(self, service_name: str, user_id: int, lines: int = 50) -> str:
        """
        Get service logs
        
        Args:
            service_name: Name of service
            user_id: User ID
            lines: Number of lines to return (default: 50)
        
        Returns:
            Log content as string
        """
        log_file = self.logs_dir / f"{user_id}_{service_name}.log"
        
        if not log_file.exists():
            return "No logs available"
        
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
                return ''.join(all_lines[-lines:])
        except Exception as e:
            self.logger.error(f"Error reading logs: {e}")
            return f"Error reading logs: {e}"
    
    def restart_service(self, service_name: str, user_id: int, command: str, workspace: str, metadata: Dict = None) -> Dict:
        """
        Restart a service
        
        Args:
            service_name: Name of service
            user_id: User ID
            command: Command to run
            workspace: Workspace directory
            metadata: Additional metadata
        
        Returns:
            Service info dict
        """
        # Stop existing service
        self.stop_service(service_name, user_id)
        
        import time
        time.sleep(1)
        
        # Start new instance
        return self.start_service(service_name, command, workspace, user_id, metadata)
    
    def _is_process_running(self, pid: int) -> bool:
        """Check if process is running"""
        try:
            return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False
    
    def get_service_by_name(self, service_name: str, user_id: int) -> Optional[Dict]:
        """
        Get service info by name and user ID
        This should query the database in actual implementation
        For now, returns None (will be implemented with database integration)
        """
        # TODO: Query database for service info
        return None


# Global instance
_service_manager_instance = None

def get_service_manager(workspace_root: str = None) -> ServiceManager:
    """Get or create global service manager instance"""
    global _service_manager_instance
    if _service_manager_instance is None or workspace_root:
        _service_manager_instance = ServiceManager(workspace_root)
    return _service_manager_instance
