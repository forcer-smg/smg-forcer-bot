# -*- coding: utf-8 -*-
"""
Tool Detector - Detect all available system tools and provide them to AI
Ensures AI uses all available tools on the system
"""

import subprocess
import os
import logging
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ToolDetector:
    """Detect available security and system tools"""
    
    def __init__(self):
        """Initialize tool detector"""
        self._available_tools = {}
        self._tool_cache = None
    
    def detect_all_tools(self) -> Dict[str, Dict]:
        """
        Detect all available tools on the system
        
        Returns:
            Dictionary mapping tool names to their info (path, version, etc.)
        """
        if self._tool_cache is not None:
            return self._tool_cache
        
        tools = {}
        
        # Security/Reconnaissance tools
        security_tools = [
            'nmap', 'nuclei', 'sqlmap', 'nikto', 'gobuster', 'dirb', 'ffuf',
            'subfinder', 'amass', 'masscan', 'zmap', 'theHarvester',
            'recon-ng', 'shodan', 'crackmapexec', 'impacket', 'kerbrute',
            'bloodhound', 'mimikatz', 'hydra', 'john', 'hashcat', 'aircrack-ng',
            'wpscan', 'arjun', 'burpsuite', 'metasploit', 'msfconsole',
            'tcpdump', 'wireshark', 'tshark'
        ]
        
        # System/Development tools
        system_tools = [
            'python', 'python3', 'pip', 'pip3', 'node', 'npm', 'go', 'git',
            'curl', 'wget', 'jq', 'yq', 'awk', 'sed', 'grep', 'find',
            'tar', 'zip', 'unzip', 'gzip', 'bzip2', 'xz',
            'docker', 'docker-compose', 'kubectl', 'helm',
            'ssh', 'scp', 'rsync', 'nc', 'netcat', 'socat',
            'perl', 'ruby', 'php', 'java', 'javac', 'mvn', 'gradle'
        ]
        
        # Network tools
        network_tools = [
            'dig', 'nslookup', 'host', 'whois', 'traceroute', 'tracepath',
            'ping', 'fping', 'hping3', 'arp', 'route', 'ip', 'ifconfig',
            'netstat', 'ss', 'lsof', 'tcpdump', 'tshark', 'wireshark'
        ]
        
        # All tools to check
        all_tools = security_tools + system_tools + network_tools
        
        logger.info(f"Detecting {len(all_tools)} tools...")
        
        for tool in all_tools:
            tool_info = self._check_tool(tool)
            if tool_info:
                tools[tool] = tool_info
        
        self._tool_cache = tools
        logger.info(f"Found {len(tools)} available tools")
        
        return tools
    
    def _check_tool(self, tool_name: str) -> Optional[Dict]:
        """
        Check if a tool is available and get its info
        
        Args:
            tool_name: Name of the tool to check
        
        Returns:
            Dictionary with tool info or None if not available
        """
        try:
            # Always use 'which' on Linux (Railway runs on Linux)
            # Check using 'which' (Linux/Mac) or 'where' (Windows)
            import sys
            if os.name == 'nt' and sys.platform != 'linux':
                result = subprocess.run(
                    ['where', tool_name],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
            else:
                # Linux/Mac: use 'which'
                result = subprocess.run(
                    ['which', tool_name],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
            
            if result.returncode == 0:
                path = result.stdout.strip().split('\n')[0]
                
                # Try to get version
                version = None
                try:
                    version_result = subprocess.run(
                        [tool_name, '--version'],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    if version_result.returncode == 0:
                        version = version_result.stdout.strip()[:100]
                except:
                    try:
                        version_result = subprocess.run(
                            [tool_name, '-v'],
                            capture_output=True,
                            text=True,
                            timeout=2
                        )
                        if version_result.returncode == 0:
                            version = version_result.stdout.strip()[:100]
                    except:
                        pass
                
                return {
                    'path': path,
                    'version': version,
                    'available': True
                }
        except Exception as e:
            logger.debug(f"Tool {tool_name} not available: {e}")
        
        return None
    
    def get_tools_summary(self) -> str:
        """
        Get a formatted summary of available tools for AI
        
        Returns:
            Formatted string describing available tools
        """
        tools = self.detect_all_tools()
        
        if not tools:
            return "No tools detected. Use basic system commands."
        
        # Group by category
        security_tools = []
        system_tools = []
        network_tools = []
        
        security_keywords = ['nmap', 'nuclei', 'sqlmap', 'nikto', 'gobuster', 'dirb', 
                           'ffuf', 'subfinder', 'amass', 'masscan', 'hydra', 'john',
                           'hashcat', 'aircrack', 'wpscan', 'burp', 'metasploit',
                           'crackmap', 'impacket', 'kerbrute', 'bloodhound', 'mimikatz']
        
        network_keywords = ['dig', 'nslookup', 'host', 'whois', 'traceroute', 'ping',
                          'fping', 'hping', 'tcpdump', 'tshark', 'wireshark', 'netstat']
        
        for tool_name, tool_info in tools.items():
            tool_lower = tool_name.lower()
            if any(kw in tool_lower for kw in security_keywords):
                security_tools.append(tool_name)
            elif any(kw in tool_lower for kw in network_keywords):
                network_tools.append(tool_name)
            else:
                system_tools.append(tool_name)
        
        summary = "**Available Tools on System:**\n\n"
        
        if security_tools:
            summary += f"**Security/Reconnaissance Tools ({len(security_tools)}):**\n"
            summary += ", ".join(sorted(security_tools)) + "\n\n"
        
        if network_tools:
            summary += f"**Network Tools ({len(network_tools)}):**\n"
            summary += ", ".join(sorted(network_tools)) + "\n\n"
        
        if system_tools:
            summary += f"**System/Development Tools ({len(system_tools)}):**\n"
            summary += ", ".join(sorted(system_tools)) + "\n\n"
        
        summary += f"\n**Total: {len(tools)} tools available**\n"
        summary += "Use these tools in your commands. Check availability with 'which <tool>' or '<tool> --version' if needed.\n"
        
        return summary
    
    def is_tool_available(self, tool_name: str) -> bool:
        """
        Check if a specific tool is available
        
        Args:
            tool_name: Name of the tool
        
        Returns:
            True if tool is available
        """
        tools = self.detect_all_tools()
        return tool_name in tools or tool_name.lower() in [t.lower() for t in tools.keys()]


# Global instance
_tool_detector_instance = None

def get_tool_detector() -> ToolDetector:
    """Get or create global tool detector instance"""
    global _tool_detector_instance
    if _tool_detector_instance is None:
        _tool_detector_instance = ToolDetector()
    return _tool_detector_instance
