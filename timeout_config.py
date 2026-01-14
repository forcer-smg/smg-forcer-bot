# -*- coding: utf-8 -*-
"""
Timeout Configuration - Adaptive timeouts based on scan type and tool
Provides intelligent timeout management for different types of operations
"""

import os
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Base timeout configuration (in seconds)
TIMEOUT_CONFIG = {
    # Quick operations
    'quick': 30,           # 30 seconds - quick checks, version checks
    'fast': 60,          # 1 minute - simple commands
    
    # Standard operations
    'standard': 300,     # 5 minutes - default for most operations
    'normal': 300,       # 5 minutes - alias for standard
    
    # Scanning operations
    'scan_basic': 600,   # 10 minutes - basic scans (nmap quick, simple nuclei)
    'scan_standard': 900,  # 15 minutes - standard scans (nmap, nuclei, nikto)
    'scan_comprehensive': 1800,  # 30 minutes - comprehensive scans (full nmap, multiple tools)
    'scan_deep': 3600,   # 60 minutes - deep scans (full enumeration, all tools)
    
    # Tool-specific timeouts
    'nmap_quick': 300,   # 5 minutes - nmap -F (fast scan)
    'nmap_standard': 900,  # 15 minutes - nmap standard scan
    'nmap_full': 1800,   # 30 minutes - nmap full scan
    'nmap_deep': 3600,   # 60 minutes - nmap deep scan with all scripts
    
    'nuclei_quick': 300,  # 5 minutes - nuclei with limited templates
    'nuclei_standard': 900,  # 15 minutes - nuclei standard scan
    'nuclei_full': 1800,  # 30 minutes - nuclei full scan
    
    'nikto_standard': 600,  # 10 minutes - nikto scan
    'nikto_full': 1200,   # 20 minutes - nikto full scan
    
    'sqlmap_quick': 600,  # 10 minutes - sqlmap quick test
    'sqlmap_standard': 1800,  # 30 minutes - sqlmap standard
    'sqlmap_full': 3600,  # 60 minutes - sqlmap full enumeration
    
    'gobuster_quick': 300,  # 5 minutes - gobuster quick wordlist
    'gobuster_standard': 900,  # 15 minutes - gobuster standard
    'gobuster_full': 1800,  # 30 minutes - gobuster large wordlist
    
    'subfinder_standard': 300,  # 5 minutes - subdomain enumeration
    'amass_standard': 1800,  # 30 minutes - amass passive
    'amass_active': 3600,  # 60 minutes - amass active
    
    # Installation operations
    'install_tool': 600,  # 10 minutes - tool installation
    'install_package': 300,  # 5 minutes - package installation
    
    # Background operations
    'background': 7200,  # 2 hours - background tasks
    'long_running': 10800,  # 3 hours - very long operations
}

# Tool detection patterns
TOOL_PATTERNS = {
    'nmap': {
        'quick': ['-F', '--top-ports', 'quick'],
        'standard': ['-sV', '-sC', 'standard'],
        'full': ['-p-', 'full', 'all-ports'],
        'deep': ['-A', 'deep', 'aggressive']
    },
    'nuclei': {
        'quick': ['-t', 'quick', 'fast'],
        'standard': ['standard'],
        'full': ['-t', 'all', 'full']
    },
    'nikto': {
        'standard': ['standard'],
        'full': ['-C', 'all', 'full']
    },
    'sqlmap': {
        'quick': ['--batch', '--level', '1'],
        'standard': ['--batch', '--level', '2'],
        'full': ['--batch', '--level', '5', '--risk', '3']
    },
    'gobuster': {
        'quick': ['-w', 'small'],
        'standard': ['-w', 'medium'],
        'full': ['-w', 'large', 'big']
    }
}

# Scan type detection
SCAN_TYPE_KEYWORDS = {
    'comprehensive': ['comprehensive', 'full', 'complete', 'deep', 'all', 'everything'],
    'standard': ['standard', 'normal', 'regular', 'scan'],
    'basic': ['basic', 'quick', 'fast', 'simple'],
    'deep': ['deep', 'thorough', 'extensive', 'detailed']
}


def detect_scan_type(command: str) -> str:
    """
    Detect scan type from command
    Returns: 'basic', 'standard', 'comprehensive', or 'deep'
    """
    command_lower = command.lower()
    
    # Check for comprehensive/deep keywords
    for keyword in SCAN_TYPE_KEYWORDS['comprehensive'] + SCAN_TYPE_KEYWORDS['deep']:
        if keyword in command_lower:
            return 'comprehensive' if keyword in SCAN_TYPE_KEYWORDS['comprehensive'] else 'deep'
    
    # Check for basic keywords
    for keyword in SCAN_TYPE_KEYWORDS['basic']:
        if keyword in command_lower:
            return 'basic'
    
    # Default to standard
    return 'standard'


def detect_tool_type(command: str) -> Optional[Dict[str, str]]:
    """
    Detect tool and scan intensity from command
    Returns: {'tool': 'nmap', 'intensity': 'standard'} or None
    """
    command_lower = command.lower()
    
    for tool, patterns in TOOL_PATTERNS.items():
        if tool in command_lower:
            # Check intensity patterns
            for intensity, keywords in patterns.items():
                for keyword in keywords:
                    if keyword in command_lower:
                        return {'tool': tool, 'intensity': intensity}
            # Tool found but no intensity pattern - use standard
            return {'tool': tool, 'intensity': 'standard'}
    
    return None


def get_timeout_for_command(command: str, default_timeout: int = 300) -> int:
    """
    Get appropriate timeout for a command based on its content
    Returns timeout in seconds
    """
    # Check environment variable for global timeout override
    env_timeout = os.getenv('SCAN_TIMEOUT')
    if env_timeout:
        try:
            return int(env_timeout)
        except ValueError:
            logger.warning(f"Invalid SCAN_TIMEOUT value: {env_timeout}")
    
    # Detect tool and intensity
    tool_info = detect_tool_type(command)
    if tool_info:
        tool = tool_info['tool']
        intensity = tool_info['intensity']
        timeout_key = f"{tool}_{intensity}"
        
        if timeout_key in TIMEOUT_CONFIG:
            timeout = TIMEOUT_CONFIG[timeout_key]
            logger.info(f"Detected {tool} {intensity} scan - using {timeout}s timeout")
            return timeout
    
    # Detect scan type
    scan_type = detect_scan_type(command)
    scan_timeout_key = f"scan_{scan_type}"
    
    if scan_timeout_key in TIMEOUT_CONFIG:
        timeout = TIMEOUT_CONFIG[scan_timeout_key]
        logger.info(f"Detected {scan_type} scan - using {timeout}s timeout")
        return timeout
    
    # Check for specific scan keywords
    command_lower = command.lower()
    
    # Multiple tools = comprehensive scan
    tool_count = sum(1 for tool in ['nmap', 'nuclei', 'nikto', 'sqlmap', 'gobuster'] if tool in command_lower)
    if tool_count >= 3:
        timeout = TIMEOUT_CONFIG['scan_comprehensive']
        logger.info(f"Multiple tools detected ({tool_count}) - using comprehensive scan timeout: {timeout}s")
        return timeout
    
    # Check for installation commands
    if any(keyword in command_lower for keyword in ['install', 'pip install', 'apt-get install', 'go install']):
        if 'tool' in command_lower:
            return TIMEOUT_CONFIG['install_tool']
        return TIMEOUT_CONFIG['install_package']
    
    # Default timeout
    logger.debug(f"Using default timeout {default_timeout}s for command: {command[:100]}")
    return default_timeout


def get_timeout_for_scan_type(scan_type: str = 'standard') -> int:
    """
    Get timeout for a specific scan type
    scan_type: 'basic', 'standard', 'comprehensive', or 'deep'
    """
    timeout_key = f"scan_{scan_type}"
    return TIMEOUT_CONFIG.get(timeout_key, TIMEOUT_CONFIG['scan_standard'])


def get_timeout_for_tool(tool: str, intensity: str = 'standard') -> int:
    """
    Get timeout for a specific tool and intensity
    tool: 'nmap', 'nuclei', 'nikto', etc.
    intensity: 'quick', 'standard', 'full', 'deep'
    """
    timeout_key = f"{tool}_{intensity}"
    return TIMEOUT_CONFIG.get(timeout_key, TIMEOUT_CONFIG['standard'])


# Export configuration
__all__ = [
    'TIMEOUT_CONFIG',
    'get_timeout_for_command',
    'get_timeout_for_scan_type',
    'get_timeout_for_tool',
    'detect_scan_type',
    'detect_tool_type'
]
