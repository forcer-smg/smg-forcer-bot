# -*- coding: utf-8 -*-
"""
Auto Retry Manager - Automatic retry with alternative approaches (like Cursor)
Analyzes errors and determines best retry strategy
"""

import re
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


class AutoRetryManager:
    """Manage automatic retries with alternative approaches"""
    
    def __init__(self, max_retries: int = 3):
        """
        Initialize auto retry manager
        
        Args:
            max_retries: Maximum number of retry attempts
        """
        self.max_retries = max_retries
        logger.info(f"Auto Retry Manager initialized (max_retries: {max_retries})")
    
    def should_retry(self, error: str, attempt: int) -> bool:
        """
        Determine if should retry based on error and attempt count
        
        Args:
            error: Error message or exception string
            attempt: Current attempt number (1-indexed)
        
        Returns:
            True if should retry, False otherwise
        """
        if attempt >= self.max_retries:
            logger.debug(f"Max retries reached ({attempt}/{self.max_retries})")
            return False
        
        error_lower = error.lower()
        
        # Errors that should NOT be retried
        no_retry_errors = [
            'permission denied',
            'access denied',
            'authentication failed',
            'invalid credentials',
            'not found',  # File not found - won't be found on retry
            'syntax error',
            'invalid syntax'
        ]
        
        for no_retry in no_retry_errors:
            if no_retry in error_lower:
                logger.debug(f"Error indicates no retry: {no_retry}")
                return False
        
        # Errors that SHOULD be retried
        retry_errors = [
            'timeout',
            'timed out',
            'connection',
            'network',
            'temporary',
            'rate limit',
            'too many requests',
            'service unavailable',
            'bad gateway',
            'gateway timeout',
            'internal server error',
            '502',
            '503',
            '504'
        ]
        
        for retry_error in retry_errors:
            if retry_error in error_lower:
                logger.debug(f"Error indicates retry: {retry_error}")
                return True
        
        # Default: retry if attempt < max_retries
        return True
    
    def get_alternative_command(self, command: str, error: str) -> Optional[str]:
        """
        Get alternative command based on original command and error
        
        Args:
            command: Original command that failed
            error: Error message
        
        Returns:
            Alternative command, or None if no alternative found
        """
        error_lower = error.lower()
        command_lower = command.lower()
        
        alternatives = []
        
        # Tool-specific alternatives
        if 'nmap' in command_lower:
            if 'permission denied' in error_lower or 'requires root' in error_lower:
                # Try with sudo or alternative scan
                alternatives.append(command.replace('nmap', 'nmap --privileged', 1))
                alternatives.append(command.replace('nmap', 'sudo nmap', 1))
        
        if 'sqlmap' in command_lower:
            if 'not found' in error_lower or 'command not found' in error_lower:
                # Try with python -m
                alternatives.append(command.replace('sqlmap', 'python -m sqlmap', 1))
                alternatives.append(command.replace('sqlmap', 'python3 -m sqlmap', 1))
        
        if 'nuclei' in command_lower:
            if 'not found' in error_lower:
                # Try with full path or alternative
                alternatives.append(command.replace('nuclei', '$HOME/go/bin/nuclei', 1))
                alternatives.append(command.replace('nuclei', '/usr/local/bin/nuclei', 1))
        
        if 'gobuster' in command_lower:
            if 'not found' in error_lower:
                # Try with full path
                alternatives.append(command.replace('gobuster', '$HOME/go/bin/gobuster', 1))
                alternatives.append(command.replace('gobuster', '/usr/local/bin/gobuster', 1))
        
        # Python command alternatives
        if command_lower.startswith('python '):
            if 'python: command not found' in error_lower or 'python: not found' in error_lower:
                alternatives.append(command.replace('python ', 'python3 ', 1))
                alternatives.append(command.replace('python ', 'py ', 1))
        
        if command_lower.startswith('python3 '):
            if 'python3: command not found' in error_lower:
                alternatives.append(command.replace('python3 ', 'python ', 1))
                alternatives.append(command.replace('python3 ', 'py ', 1))
        
        # curl alternatives
        if 'curl' in command_lower:
            if 'not found' in error_lower:
                alternatives.append(command.replace('curl', 'wget', 1))
        
        # wget alternatives
        if 'wget' in command_lower:
            if 'not found' in error_lower:
                alternatives.append(command.replace('wget', 'curl', 1))
        
        # Timeout alternatives - add timeout flag or increase timeout
        if 'timeout' in error_lower or 'timed out' in error_lower:
            # Try adding timeout flag if not present
            if '--timeout' not in command_lower and '--max-time' not in command_lower:
                if 'curl' in command_lower:
                    alternatives.append(command + ' --max-time 60')
                elif 'wget' in command_lower:
                    alternatives.append(command + ' --timeout=60')
        
        # Permission alternatives - try with different permissions
        if 'permission denied' in error_lower:
            # Try with sudo (but be careful)
            if 'sudo' not in command_lower:
                alternatives.append(f"sudo {command}")
        
        # Network/connection alternatives
        if 'connection' in error_lower or 'network' in error_lower:
            # Try with different options
            if 'curl' in command_lower:
                alternatives.append(command + ' --retry 3 --retry-delay 2')
            elif 'wget' in command_lower:
                alternatives.append(command + ' --tries=3 --waitretry=2')
        
        # Return first alternative if any found
        if alternatives:
            logger.info(f"Found {len(alternatives)} alternative(s) for command: {command}")
            return alternatives[0]
        
        logger.debug(f"No alternative found for command: {command}")
        return None
    
    def get_alternative_tool(self, command: str, error: str) -> Optional[str]:
        """
        Get alternative tool command (different tool for same goal)
        
        Args:
            command: Original command
            error: Error message
        
        Returns:
            Alternative tool command, or None
        """
        command_lower = command.lower()
        error_lower = error.lower()
        
        # Tool replacements
        replacements = {
            'nmap': ['masscan', 'rustscan', 'zmap'],
            'sqlmap': ['nosqlmap', 'jSQL Injection'],
            'nuclei': ['vulners', 'vulscan'],
            'gobuster': ['ffuf', 'dirb', 'dirsearch'],
            'nikto': ['wapiti', 'skipfish'],
            'curl': ['wget', 'httpie'],
            'wget': ['curl', 'httpie']
        }
        
        for tool, alternatives in replacements.items():
            if tool in command_lower:
                for alt_tool in alternatives:
                    # Simple replacement (may need more sophisticated logic)
                    alt_command = command_lower.replace(tool, alt_tool, 1)
                    logger.info(f"Trying alternative tool: {alt_tool} instead of {tool}")
                    return alt_command
        
        return None
    
    def analyze_error(self, error: str) -> Dict[str, Any]:
        """
        Analyze error to determine retry strategy
        
        Args:
            error: Error message or exception string
        
        Returns:
            Dictionary with analysis and retry strategy
        """
        error_lower = error.lower()
        
        analysis = {
            'error_type': 'unknown',
            'retry_strategy': 'simple_retry',
            'should_retry': True,
            'backoff_time': 1.0,
            'alternative_approach': None
        }
        
        # Classify error type
        if 'timeout' in error_lower or 'timed out' in error_lower:
            analysis['error_type'] = 'timeout'
            analysis['retry_strategy'] = 'timeout_retry'
            analysis['backoff_time'] = 2.0
        
        elif 'rate limit' in error_lower or 'too many requests' in error_lower or '429' in error_lower:
            analysis['error_type'] = 'rate_limit'
            analysis['retry_strategy'] = 'rate_limit_retry'
            analysis['backoff_time'] = 5.0
        
        elif 'connection' in error_lower or 'network' in error_lower:
            analysis['error_type'] = 'network'
            analysis['retry_strategy'] = 'network_retry'
            analysis['backoff_time'] = 3.0
        
        elif 'not found' in error_lower or 'command not found' in error_lower:
            analysis['error_type'] = 'not_found'
            analysis['retry_strategy'] = 'alternative_command'
            analysis['backoff_time'] = 0.5
        
        elif 'permission denied' in error_lower or 'access denied' in error_lower:
            analysis['error_type'] = 'permission'
            analysis['retry_strategy'] = 'permission_retry'
            analysis['backoff_time'] = 1.0
        
        elif 'internal server error' in error_lower or '500' in error_lower:
            analysis['error_type'] = 'server_error'
            analysis['retry_strategy'] = 'server_retry'
            analysis['backoff_time'] = 5.0
        
        # Determine if should retry
        analysis['should_retry'] = self.should_retry(error, 1)  # Assume first attempt
        
        logger.debug(f"Error analysis: {analysis}")
        
        return analysis
    
    def retry_with_alternative(self, 
                              command: str, 
                              error: str, 
                              attempt: int) -> Optional[str]:
        """
        Get alternative command for retry
        
        Args:
            command: Original command
            error: Error message
            attempt: Current attempt number
        
        Returns:
            Alternative command, or None if no alternative
        """
        if attempt >= self.max_retries:
            return None
        
        # Try to get alternative command
        alt_command = self.get_alternative_command(command, error)
        if alt_command:
            return alt_command
        
        # Try alternative tool
        alt_tool = self.get_alternative_tool(command, error)
        if alt_tool:
            return alt_tool
        
        # If no alternative found, return original (will retry with same command)
        return command


# Global instance
_auto_retry_manager_instance = None

def get_auto_retry_manager(max_retries: int = 3) -> AutoRetryManager:
    """Get or create global auto retry manager instance"""
    global _auto_retry_manager_instance
    if _auto_retry_manager_instance is None:
        _auto_retry_manager_instance = AutoRetryManager(max_retries)
    return _auto_retry_manager_instance
