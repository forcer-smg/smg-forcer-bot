# -*- coding: utf-8 -*-
"""
HexStrike AI Integration - 150+ security tools with multi-agent architecture
Integrates HexStrike AI framework for autonomous security testing
"""

import os
import json
import subprocess
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
import asyncio

logger = logging.getLogger(__name__)

# Check if HexStrike AI is available
HEXSTRIKE_AVAILABLE = False
HEXSTRIKE_PATH = None

# Try to find HexStrike AI installation
possible_paths = [
    Path('/app/hexstrike-ai'),
    Path(os.getcwd()) / 'hexstrike-ai',
    Path(os.getcwd()) / 'hexstrike_ai',
    Path.home() / 'hexstrike-ai',
]

for path in possible_paths:
    if path.exists() and (path / 'hexstrike.py').exists():
        HEXSTRIKE_PATH = path
        HEXSTRIKE_AVAILABLE = True
        logger.info(f"HexStrike AI found at: {HEXSTRIKE_PATH}")
        break

# If not found, try to import as module
if not HEXSTRIKE_AVAILABLE:
    try:
        import hexstrike
        HEXSTRIKE_AVAILABLE = True
        logger.info("HexStrike AI imported as module")
    except ImportError:
        logger.warning("HexStrike AI not found. Install from: https://github.com/0x4m4/hexstrike-ai")


class HexStrikeTool:
    """Represents a HexStrike AI tool"""
    
    def __init__(self, name: str, description: str, category: str, 
                 command: Optional[str] = None, agent: Optional[str] = None):
        self.name = name
        self.description = description
        self.category = category
        self.command = command
        self.agent = agent
        self.hexstrike_tool = True
    
    def to_dict(self) -> Dict:
        """Convert tool to dictionary"""
        return {
            'name': self.name,
            'description': self.description,
            'category': self.category,
            'command': self.command,
            'agent': self.agent,
            'hexstrike_tool': True,
            'source': 'hexstrike-ai'
        }


class HexStrikeIntegration:
    """Integration with HexStrike AI framework"""
    
    def __init__(self, workspace_root: Optional[str] = None):
        """
        Initialize HexStrike integration
        workspace_root: Workspace directory
        """
        self.workspace_root = Path(workspace_root) if workspace_root else Path(os.getcwd())
        self.hexstrike_path = HEXSTRIKE_PATH
        self.tools_cache: List[HexStrikeTool] = []
        self.agents_cache: List[Dict] = []
        
        if HEXSTRIKE_AVAILABLE:
            self._discover_tools()
            self._discover_agents()
    
    def _discover_tools(self):
        """Discover available HexStrike tools"""
        if not HEXSTRIKE_AVAILABLE:
            return
        
        try:
            # Try to get tools from HexStrike framework
            if self.hexstrike_path:
                # Look for tools directory or configuration
                tools_dir = self.hexstrike_path / 'tools'
                config_file = self.hexstrike_path / 'tools.json'
                
                if config_file.exists():
                    with open(config_file, 'r') as f:
                        tools_config = json.load(f)
                        for tool_data in tools_config.get('tools', []):
                            tool = HexStrikeTool(
                                name=tool_data.get('name', ''),
                                description=tool_data.get('description', ''),
                                category=tool_data.get('category', 'security'),
                                command=tool_data.get('command'),
                                agent=tool_data.get('agent')
                            )
                            self.tools_cache.append(tool)
                
                elif tools_dir.exists():
                    # Discover tools from directory structure
                    for tool_file in tools_dir.glob('*.py'):
                        tool_name = tool_file.stem
                        # Try to extract tool info from file
                        try:
                            with open(tool_file, 'r') as f:
                                content = f.read()
                                # Look for docstring or metadata
                                if 'def main' in content or 'def run' in content:
                                    tool = HexStrikeTool(
                                        name=tool_name,
                                        description=f"HexStrike tool: {tool_name}",
                                        category='security',
                                        command=f"python {tool_file}"
                                    )
                                    self.tools_cache.append(tool)
                        except Exception as e:
                            logger.warning(f"Error reading tool file {tool_file}: {e}")
            
            # Default HexStrike tools (common security tools)
            default_tools = [
                {'name': 'nmap', 'description': 'Network mapper and port scanner', 'category': 'reconnaissance'},
                {'name': 'sqlmap', 'description': 'SQL injection tool', 'category': 'exploitation'},
                {'name': 'burpsuite', 'description': 'Web application security testing', 'category': 'web_testing'},
                {'name': 'metasploit', 'description': 'Penetration testing framework', 'category': 'exploitation'},
                {'name': 'nikto', 'description': 'Web server scanner', 'category': 'reconnaissance'},
                {'name': 'dirb', 'description': 'Web content scanner', 'category': 'reconnaissance'},
                {'name': 'hydra', 'description': 'Password cracker', 'category': 'credential_access'},
                {'name': 'john', 'description': 'John the Ripper password cracker', 'category': 'credential_access'},
                {'name': 'hashcat', 'description': 'Advanced password recovery', 'category': 'credential_access'},
                {'name': 'wireshark', 'description': 'Network protocol analyzer', 'category': 'analysis'},
                {'name': 'tcpdump', 'description': 'Packet analyzer', 'category': 'analysis'},
                {'name': 'aircrack-ng', 'description': 'WiFi security auditing', 'category': 'wireless'},
                {'name': 'subfinder', 'description': 'Subdomain discovery tool', 'category': 'reconnaissance'},
                {'name': 'amass', 'description': 'In-depth DNS enumeration', 'category': 'reconnaissance'},
                {'name': 'masscan', 'description': 'Fast port scanner', 'category': 'reconnaissance'},
                {'name': 'gobuster', 'description': 'Directory/file brute forcer', 'category': 'reconnaissance'},
                {'name': 'ffuf', 'description': 'Fast web fuzzer', 'category': 'reconnaissance'},
                {'name': 'nuclei', 'description': 'Vulnerability scanner', 'category': 'vulnerability_scanning'},
                {'name': 'zap', 'description': 'OWASP ZAP security scanner', 'category': 'web_testing'},
                {'name': 'wpscan', 'description': 'WordPress security scanner', 'category': 'web_testing'},
            ]
            
            # Add default tools if not already discovered
            existing_names = {t.name for t in self.tools_cache}
            for tool_data in default_tools:
                if tool_data['name'] not in existing_names:
                    tool = HexStrikeTool(
                        name=tool_data['name'],
                        description=tool_data['description'],
                        category=tool_data['category']
                    )
                    self.tools_cache.append(tool)
            
            logger.info(f"Discovered {len(self.tools_cache)} HexStrike tools")
        
        except Exception as e:
            logger.error(f"Error discovering HexStrike tools: {e}")
    
    def _discover_agents(self):
        """Discover HexStrike AI agents"""
        if not HEXSTRIKE_AVAILABLE:
            return
        
        try:
            # HexStrike multi-agent architecture
            agents = [
                {
                    'name': 'reconnaissance_agent',
                    'description': 'Autonomous reconnaissance and information gathering',
                    'capabilities': ['subdomain_enumeration', 'port_scanning', 'osint']
                },
                {
                    'name': 'exploitation_agent',
                    'description': 'Vulnerability exploitation and attack automation',
                    'capabilities': ['exploit_generation', 'payload_creation', 'attack_execution']
                },
                {
                    'name': 'web_testing_agent',
                    'description': 'Web application security testing',
                    'capabilities': ['xss_testing', 'sql_injection', 'csrf_testing', 'authentication_bypass']
                },
                {
                    'name': 'binary_analysis_agent',
                    'description': 'Binary analysis and reverse engineering',
                    'capabilities': ['disassembly', 'decompilation', 'vulnerability_analysis']
                },
                {
                    'name': 'network_analysis_agent',
                    'description': 'Network traffic analysis and monitoring',
                    'capabilities': ['packet_capture', 'traffic_analysis', 'protocol_analysis']
                }
            ]
            
            self.agents_cache = agents
            logger.info(f"Discovered {len(agents)} HexStrike agents")
        
        except Exception as e:
            logger.error(f"Error discovering HexStrike agents: {e}")
    
    def get_all_tools(self) -> List[HexStrikeTool]:
        """Get all discovered HexStrike tools"""
        return self.tools_cache
    
    def find_tools_by_category(self, category: str) -> List[HexStrikeTool]:
        """Find tools by category"""
        return [tool for tool in self.tools_cache if tool.category == category]
    
    def find_tools_by_name(self, name: str) -> List[HexStrikeTool]:
        """Find tools by name (fuzzy match)"""
        name_lower = name.lower()
        return [
            tool for tool in self.tools_cache
            if name_lower in tool.name.lower() or tool.name.lower() in name_lower
        ]
    
    def get_tool_info(self, tool_name: str) -> Optional[HexStrikeTool]:
        """Get tool information by name"""
        for tool in self.tools_cache:
            if tool.name == tool_name:
                return tool
        return None
    
    def execute_tool(self, tool_name: str, parameters: List[str] = None) -> Dict:
        """
        Execute HexStrike tool
        Returns execution result
        """
        if not HEXSTRIKE_AVAILABLE:
            return {'success': False, 'error': 'HexStrike AI not available'}
        
        tool = self.get_tool_info(tool_name)
        if not tool:
            return {'success': False, 'error': f'Tool {tool_name} not found'}
        
        try:
            # Build command
            if tool.command:
                cmd = tool.command.split() + (parameters or [])
            else:
                # Default: try to execute tool directly
                cmd = [tool_name] + (parameters or [])
            
            # Execute tool
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                encoding='utf-8',
                errors='replace'
            )
            
            return {
                'success': result.returncode == 0,
                'exit_code': result.returncode,
                'output': result.stdout,
                'error': result.stderr,
                'tool': tool_name
            }
        
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Tool execution timed out', 'tool': tool_name}
        except Exception as e:
            return {'success': False, 'error': str(e), 'tool': tool_name}
    
    def get_agents(self) -> List[Dict]:
        """Get all available agents"""
        return self.agents_cache
    
    def execute_agent_task(self, agent_name: str, task: str) -> Dict:
        """
        Execute task using HexStrike agent
        Returns agent execution result
        """
        if not HEXSTRIKE_AVAILABLE:
            return {'success': False, 'error': 'HexStrike AI not available'}
        
        # Find agent
        agent = None
        for a in self.agents_cache:
            if a['name'] == agent_name:
                agent = a
                break
        
        if not agent:
            return {'success': False, 'error': f'Agent {agent_name} not found'}
        
        # For now, return agent info (full integration would require HexStrike framework)
        return {
            'success': True,
            'agent': agent_name,
            'task': task,
            'capabilities': agent.get('capabilities', []),
            'message': f'Agent {agent_name} would execute: {task}'
        }
    
    def get_tools_for_task(self, task: str, limit: int = 10) -> List[HexStrikeTool]:
        """Find best HexStrike tools for a task"""
        task_lower = task.lower()
        scored_tools = []
        
        for tool in self.tools_cache:
            score = 0
            
            # Name match
            if tool.name.lower() in task_lower:
                score += 100
            
            # Description match
            if tool.description.lower() in task_lower:
                score += 50
            
            # Category keywords
            category_keywords = {
                'reconnaissance': ['scan', 'recon', 'discover', 'enumerate', 'find'],
                'exploitation': ['exploit', 'attack', 'breach', 'hack'],
                'web_testing': ['web', 'website', 'http', 'browser', 'xss', 'sql'],
                'credential_access': ['password', 'hash', 'crack', 'brute'],
                'vulnerability_scanning': ['vulnerability', 'vuln', 'cve', 'scan']
            }
            
            if tool.category in category_keywords:
                for keyword in category_keywords[tool.category]:
                    if keyword in task_lower:
                        score += 20
                        break
            
            if score > 0:
                scored_tools.append((score, tool))
        
        # Sort by score
        scored_tools.sort(key=lambda x: x[0], reverse=True)
        return [tool for score, tool in scored_tools[:limit]]


# Global HexStrike integration instance
_hexstrike_instance = None

def get_hexstrike_integration(workspace_root: Optional[str] = None) -> HexStrikeIntegration:
    """Get or create global HexStrike integration instance"""
    global _hexstrike_instance
    if _hexstrike_instance is None:
        _hexstrike_instance = HexStrikeIntegration(workspace_root)
    return _hexstrike_instance
