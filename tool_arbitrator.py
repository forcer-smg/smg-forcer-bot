# -*- coding: utf-8 -*-
"""
Tool Arbitrator - Cursor-style tool call validation and safety gates
Validates tool calls before execution, prevents dangerous operations, and requires confirmation for risky actions
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# Risky tools that require confirmation
RISKY_TOOLS = {
    'delete_files',
    'rm',
    'format',
    'shutdown',
    'reboot',
    'chmod',
    'chown',
    'sudo',
    'dd',
    'mkfs'
}

# Dangerous command patterns
DANGEROUS_PATTERNS = [
    r'rm\s+-rf\s+/',  # System-wide deletion
    r'rm\s+-rf\s+/home',  # Home directory deletion
    r'rm\s+-rf\s+/root',  # Root directory deletion
    r'format\s+',  # Disk formatting
    r'mkfs\s+',  # File system creation
    r'dd\s+if=/dev/zero',  # Disk wiping
    r'shutdown\s+',  # System shutdown
    r'reboot\s+',  # System reboot
    r'chmod\s+777\s+/',  # System-wide permissions
    r'chmod\s+-R\s+777\s+/',  # Recursive system permissions
    r'>\s+/dev/sd',  # Direct disk writes
    r'>\s+/dev/hd',  # Direct disk writes
]

# Safe paths (allowed operations)
SAFE_PATHS = [
    r'/tmp/',
    r'/app/',
    r'user_\d+/',  # User workspace
    r'\./',
    r'[a-zA-Z]:\\',  # Windows drives (relative)
]

# Commands that are always blocked
BLOCKED_COMMANDS = [
    'rm -rf /',
    'rm -rf /home',
    'rm -rf /root',
    'format c:',
    'mkfs',
    'dd if=/dev/zero of=/dev/sda',
    'shutdown',
    'reboot',
    'halt',
    'poweroff',
]


class ToolArbitrator:
    """Validates and arbitrates tool calls before execution (Cursor-style safety layer)"""
    
    def __init__(self, workspace_root: Optional[Path] = None):
        """
        Initialize Tool Arbitrator
        
        Args:
            workspace_root: Base workspace directory for path validation
        """
        self.workspace_root = workspace_root or Path.cwd()
        logger.info(f"ToolArbitrator initialized with workspace: {self.workspace_root}")
    
    def validate_tool_call(self, tool_call: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validate tool call before execution
        
        Args:
            tool_call: Tool call dictionary with 'tool', 'arguments', etc.
        
        Returns:
            Tuple of (is_valid, reason, metadata)
            - is_valid: Whether tool call is safe to execute
            - reason: Explanation of validation result
            - metadata: Additional info (risk_level, requires_confirmation, etc.)
        """
        try:
            tool_name = tool_call.get('tool', '').lower()
            arguments = tool_call.get('arguments', {})
            command = tool_call.get('command', '')
            
            # Check if tool is in risky tools list
            if tool_name in RISKY_TOOLS:
                risk_level = self._assess_risk_level(tool_call)
                if risk_level == 'critical':
                    return False, f"Critical risk: {tool_name} operation blocked", {
                        'risk_level': 'critical',
                        'requires_confirmation': True,
                        'blocked': True
                    }
                elif risk_level == 'high':
                    return True, f"High risk: {tool_name} requires confirmation", {
                        'risk_level': 'high',
                        'requires_confirmation': True,
                        'blocked': False
                    }
            
            # Check command string if provided
            if command:
                # Check for blocked commands
                for blocked in BLOCKED_COMMANDS:
                    if blocked.lower() in command.lower():
                        return False, f"Blocked command detected: {blocked}", {
                            'risk_level': 'critical',
                            'requires_confirmation': False,
                            'blocked': True
                        }
                
                # Check for dangerous patterns
                for pattern in DANGEROUS_PATTERNS:
                    if re.search(pattern, command, re.IGNORECASE):
                        return False, f"Dangerous pattern detected: {pattern}", {
                            'risk_level': 'critical',
                            'requires_confirmation': False,
                            'blocked': True
                        }
                
                # Validate paths in command
                path_validation = self._validate_paths_in_command(command)
                if not path_validation[0]:
                    return False, path_validation[1], {
                        'risk_level': 'critical',
                        'requires_confirmation': False,
                        'blocked': True
                    }
            
            # Validate arguments if provided
            if arguments:
                # Check for dangerous paths in arguments
                for key, value in arguments.items():
                    if isinstance(value, str) and ('path' in key.lower() or 'file' in key.lower()):
                        path_validation = self._validate_path(value)
                        if not path_validation[0]:
                            return False, f"Invalid path in {key}: {path_validation[1]}", {
                                'risk_level': 'critical',
                                'requires_confirmation': False,
                                'blocked': True
                            }
            
            # All checks passed
            return True, "Tool call validated", {
                'risk_level': 'low',
                'requires_confirmation': False,
                'blocked': False
            }
            
        except Exception as e:
            logger.error(f"Error validating tool call: {e}", exc_info=True)
            return False, f"Validation error: {str(e)}", {
                'risk_level': 'unknown',
                'requires_confirmation': True,
                'blocked': False
            }
    
    def _assess_risk_level(self, tool_call: Dict[str, Any]) -> str:
        """Assess risk level of a tool call"""
        tool_name = tool_call.get('tool', '').lower()
        arguments = tool_call.get('arguments', {})
        command = tool_call.get('command', '')
        
        # Critical risk operations
        if tool_name in ['rm', 'delete_files']:
            path = arguments.get('path', '') or command
            if path:
                # Check if path is system directory
                if any(sys_path in path for sys_path in ['/', '/home', '/root', '/etc', '/usr', '/bin', '/sbin']):
                    return 'critical'
                # Check if path contains wildcards in dangerous locations
                if '*' in path and any(dangerous in path for dangerous in ['/', '/home', '/root']):
                    return 'critical'
        
        if tool_name in ['format', 'mkfs', 'dd']:
            return 'critical'
        
        if tool_name in ['shutdown', 'reboot', 'halt', 'poweroff']:
            return 'critical'
        
        # High risk operations
        if tool_name in ['chmod', 'chown']:
            path = arguments.get('path', '') or command
            if path and any(sys_path in path for sys_path in ['/', '/home', '/root']):
                return 'high'
        
        if tool_name == 'sudo':
            return 'high'
        
        # Medium risk (default for risky tools)
        return 'medium'
    
    def _validate_path(self, path: str) -> Tuple[bool, str]:
        """Validate a file path for safety"""
        if not path:
            return True, "OK"
        
        path_lower = path.lower()
        
        # Block system directories
        blocked_paths = ['/', '/home', '/root', '/etc', '/usr', '/bin', '/sbin', '/var', '/sys', '/proc', '/dev']
        for blocked in blocked_paths:
            if path_lower.startswith(blocked) and path_lower != blocked + '/':
                return False, f"Cannot operate on system directory: {blocked}"
        
        # Allow safe paths
        for safe_pattern in SAFE_PATHS:
            if re.search(safe_pattern, path, re.IGNORECASE):
                return True, "OK"
        
        # Check if path is within workspace
        try:
            path_obj = Path(path)
            if path_obj.is_absolute():
                # Check if absolute path is within workspace
                try:
                    path_obj.relative_to(self.workspace_root)
                    return True, "OK"
                except ValueError:
                    return False, f"Path outside workspace: {path}"
            else:
                # Relative paths are generally safer
                return True, "OK"
        except Exception:
            # If path parsing fails, be conservative
            return False, f"Invalid path format: {path}"
    
    def _validate_paths_in_command(self, command: str) -> Tuple[bool, str]:
        """Extract and validate paths from a command string"""
        # Extract potential paths (simplified - looks for common path patterns)
        path_patterns = [
            r'[\'"](/[^\'"]+)[\'"]',  # Quoted absolute paths
            r'[\'"](\.[^\'"]+)[\'"]',  # Quoted relative paths
            r'\s+([/\w][^\s]+)',  # Space-separated paths
        ]
        
        for pattern in path_patterns:
            matches = re.findall(pattern, command)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0] if match else ''
                if match:
                    # Skip if it's clearly not a path (e.g., command flags)
                    if match.startswith('-') or match.startswith('--'):
                        continue
                    # Validate the path
                    path_validation = self._validate_path(match)
                    if not path_validation[0]:
                        return False, f"Invalid path in command: {path_validation[1]}"
        
        return True, "OK"
    
    def requires_confirmation(self, tool_call: Dict[str, Any]) -> bool:
        """Check if tool call requires user confirmation"""
        is_valid, reason, metadata = self.validate_tool_call(tool_call)
        return metadata.get('requires_confirmation', False) and not metadata.get('blocked', False)
    
    def is_blocked(self, tool_call: Dict[str, Any]) -> bool:
        """Check if tool call is blocked"""
        is_valid, reason, metadata = self.validate_tool_call(tool_call)
        return metadata.get('blocked', False)
    
    def get_risk_level(self, tool_call: Dict[str, Any]) -> str:
        """Get risk level of a tool call"""
        is_valid, reason, metadata = self.validate_tool_call(tool_call)
        return metadata.get('risk_level', 'unknown')
    
    def format_tool_call(self, tool_name: str, arguments: Dict[str, Any] = None, command: str = None) -> Dict[str, Any]:
        """Format a tool call in structured format (Cursor-style)"""
        tool_call = {
            'tool': tool_name,
            'arguments': arguments or {},
            'timestamp': datetime.now().isoformat()
        }
        
        if command:
            tool_call['command'] = command
        
        return tool_call
    
    def parse_command_to_tool_call(self, command: str) -> Dict[str, Any]:
        """Parse a command string into structured tool call format"""
        command_lower = command.lower().strip()
        
        # Detect tool type from command
        tool_name = 'run_command'
        arguments = {'command': command}
        
        # Detect specific tools
        if command_lower.startswith('rm '):
            tool_name = 'delete_files'
            # Extract path from rm command
            parts = command.split()
            if len(parts) > 1:
                path = parts[-1]  # Last argument is usually the path
                arguments = {
                    'path': path,
                    'recursive': '-r' in parts or '-rf' in parts or '--recursive' in parts
                }
        elif command_lower.startswith('chmod '):
            tool_name = 'change_permissions'
            parts = command.split()
            if len(parts) >= 3:
                arguments = {
                    'mode': parts[1],
                    'path': parts[2],
                    'recursive': '-R' in parts or '--recursive' in parts
                }
        elif command_lower.startswith('chown '):
            tool_name = 'change_ownership'
            parts = command.split()
            if len(parts) >= 3:
                arguments = {
                    'owner': parts[1],
                    'path': parts[2],
                    'recursive': '-R' in parts or '--recursive' in parts
                }
        
        return self.format_tool_call(tool_name, arguments, command)
