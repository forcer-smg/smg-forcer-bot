# -*- coding: utf-8 -*-
"""
Model Context Protocol (MCP) Integration
Enables dynamic tool integration through MCP protocol
"""

import os
import json
import logging
import subprocess
import asyncio
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
import httpx
import aiohttp

logger = logging.getLogger(__name__)

# Try to import MCP SDK if available
try:
    # Check if mcp package exists (may need to install)
    import mcp
    MCP_SDK_AVAILABLE = True
except ImportError:
    MCP_SDK_AVAILABLE = False
    logger.info("MCP SDK not available, using custom implementation")


class MCPTool:
    """Represents an MCP tool"""
    
    def __init__(self, name: str, description: str, parameters: Dict, 
                 mcp_server: Optional[str] = None, handler: Optional[Callable] = None):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.mcp_server = mcp_server
        self.handler = handler
        self.capabilities = ['read', 'write', 'execute']  # Default capabilities
    
    def to_dict(self) -> Dict:
        """Convert tool to dictionary"""
        return {
            'name': self.name,
            'description': self.description,
            'parameters': self.parameters,
            'mcp_server': self.mcp_server,
            'capabilities': self.capabilities
        }


class MCPClient:
    """MCP Client for connecting to MCP servers"""
    
    def __init__(self, server_url: Optional[str] = None, server_command: Optional[List[str]] = None):
        """
        Initialize MCP client
        server_url: HTTP/WebSocket URL for MCP server
        server_command: Command to start MCP server (stdin/stdout)
        """
        self.server_url = server_url
        self.server_command = server_command
        self.server_process = None
        self.session = None
        self.tools: List[MCPTool] = []
        self.connected = False
    
    async def connect(self) -> bool:
        """Connect to MCP server"""
        try:
            if self.server_url:
                # HTTP/WebSocket connection
                self.session = aiohttp.ClientSession()
                # Test connection
                async with self.session.get(f"{self.server_url}/health") as response:
                    if response.status == 200:
                        self.connected = True
                        await self.discover_tools()
                        return True
            elif self.server_command:
                # Stdio connection
                self.server_process = await asyncio.create_subprocess_exec(
                    *self.server_command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                self.connected = True
                await self.discover_tools()
                return True
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}")
            self.connected = False
            return False
        
        return False
    
    async def discover_tools(self) -> List[MCPTool]:
        """Discover available tools from MCP server"""
        if not self.connected:
            return []
        
        try:
            if self.server_url:
                # HTTP discovery
                async with self.session.get(f"{self.server_url}/tools") as response:
                    if response.status == 200:
                        data = await response.json()
                        tools_data = data.get('tools', [])
                        for tool_data in tools_data:
                            tool = MCPTool(
                                name=tool_data.get('name'),
                                description=tool_data.get('description', ''),
                                parameters=tool_data.get('parameters', {}),
                                mcp_server=self.server_url
                            )
                            self.tools.append(tool)
            elif self.server_process:
                # Stdio discovery - send MCP protocol message
                request = {
                    'jsonrpc': '2.0',
                    'id': 1,
                    'method': 'tools/list',
                    'params': {}
                }
                request_json = json.dumps(request) + '\n'
                self.server_process.stdin.write(request_json.encode())
                await self.server_process.stdin.drain()
                
                # Read response
                response_line = await self.server_process.stdout.readline()
                response = json.loads(response_line.decode())
                
                if 'result' in response:
                    tools_data = response['result'].get('tools', [])
                    for tool_data in tools_data:
                        tool = MCPTool(
                            name=tool_data.get('name'),
                            description=tool_data.get('description', ''),
                            parameters=tool_data.get('parameters', {}),
                            mcp_server='stdio'
                        )
                        self.tools.append(tool)
        except Exception as e:
            logger.error(f"Error discovering MCP tools: {e}")
        
        return self.tools
    
    async def execute_tool(self, tool_name: str, parameters: Dict) -> Dict:
        """Execute an MCP tool"""
        if not self.connected:
            return {'error': 'Not connected to MCP server'}
        
        # Find tool
        tool = None
        for t in self.tools:
            if t.name == tool_name:
                tool = t
                break
        
        if not tool:
            return {'error': f'Tool {tool_name} not found'}
        
        try:
            if self.server_url:
                # HTTP execution
                async with self.session.post(
                    f"{self.server_url}/tools/{tool_name}/execute",
                    json=parameters
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result
                    else:
                        return {'error': f'HTTP {response.status}'}
            elif self.server_process:
                # Stdio execution
                request = {
                    'jsonrpc': '2.0',
                    'id': 2,
                    'method': 'tools/call',
                    'params': {
                        'name': tool_name,
                        'arguments': parameters
                    }
                }
                request_json = json.dumps(request) + '\n'
                self.server_process.stdin.write(request_json.encode())
                await self.server_process.stdin.drain()
                
                # Read response
                response_line = await self.server_process.stdout.readline()
                response = json.loads(response_line.decode())
                
                if 'result' in response:
                    return response['result']
                elif 'error' in response:
                    return {'error': response['error']}
        except Exception as e:
            logger.error(f"Error executing MCP tool {tool_name}: {e}")
            return {'error': str(e)}
        
        return {'error': 'Unknown execution error'}
    
    async def disconnect(self):
        """Disconnect from MCP server"""
        if self.session:
            await self.session.close()
            self.session = None
        
        if self.server_process:
            self.server_process.terminate()
            await self.server_process.wait()
            self.server_process = None
        
        self.connected = False


class MCPIntegration:
    """Main MCP integration manager"""
    
    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = Path(workspace_root) if workspace_root else Path(os.getcwd())
        self.clients: List[MCPClient] = []
        self.local_tools: List[MCPTool] = []
        self.tools_cache: Dict[str, MCPTool] = {}
        
        # Load MCP server configurations
        self.mcp_config_path = self.workspace_root / 'mcp_config.json'
        self.servers = self._load_server_configs()
    
    def _load_server_configs(self) -> List[Dict]:
        """Load MCP server configurations from file"""
        if not self.mcp_config_path.exists():
            return []
        
        try:
            with open(self.mcp_config_path, 'r') as f:
                config = json.load(f)
                return config.get('servers', [])
        except Exception as e:
            logger.error(f"Error loading MCP config: {e}")
            return []
    
    def _save_server_configs(self):
        """Save MCP server configurations to file"""
        try:
            config = {'servers': self.servers}
            with open(self.mcp_config_path, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving MCP config: {e}")
    
    async def register_server(self, name: str, server_url: Optional[str] = None, 
                             server_command: Optional[List[str]] = None) -> bool:
        """Register an MCP server"""
        try:
            client = MCPClient(server_url=server_url, server_command=server_command)
            connected = await client.connect()
            
            if connected:
                self.clients.append(client)
                self.servers.append({
                    'name': name,
                    'url': server_url,
                    'command': server_command
                })
                self._save_server_configs()
                logger.info(f"MCP server '{name}' registered successfully")
                return True
            else:
                logger.warning(f"Failed to connect to MCP server '{name}'")
                return False
        except Exception as e:
            logger.error(f"Error registering MCP server: {e}")
            return False
    
    def register_local_tool(self, tool: MCPTool):
        """Register a local tool (not from MCP server)"""
        self.local_tools.append(tool)
        self.tools_cache[tool.name] = tool
        logger.info(f"Local MCP tool '{tool.name}' registered")
    
    async def discover_all_tools(self) -> List[MCPTool]:
        """Discover all available tools from all MCP servers"""
        all_tools = []
        
        # Add local tools
        all_tools.extend(self.local_tools)
        
        # Discover tools from all clients
        for client in self.clients:
            if client.connected:
                tools = await client.discover_tools()
                all_tools.extend(tools)
        
        # Update cache
        for tool in all_tools:
            self.tools_cache[tool.name] = tool
        
        return all_tools
    
    def find_tool(self, tool_name: str) -> Optional[MCPTool]:
        """Find a tool by name"""
        # Check cache first
        if tool_name in self.tools_cache:
            return self.tools_cache[tool_name]
        
        # Search all tools
        for tool in self.local_tools:
            if tool.name == tool_name:
                self.tools_cache[tool_name] = tool
                return tool
        
        for client in self.clients:
            for tool in client.tools:
                if tool.name == tool_name:
                    self.tools_cache[tool_name] = tool
                    return tool
        
        return None
    
    async def execute_tool(self, tool_name: str, parameters: Dict) -> Dict:
        """Execute an MCP tool"""
        # Check local tools first
        for tool in self.local_tools:
            if tool.name == tool_name:
                if tool.handler:
                    try:
                        if asyncio.iscoroutinefunction(tool.handler):
                            result = await tool.handler(**parameters)
                        else:
                            result = tool.handler(**parameters)
                        return {'success': True, 'result': result}
                    except Exception as e:
                        return {'success': False, 'error': str(e)}
                else:
                    return {'success': False, 'error': 'No handler for local tool'}
        
        # Try MCP clients
        for client in self.clients:
            if client.connected:
                for tool in client.tools:
                    if tool.name == tool_name:
                        result = await client.execute_tool(tool_name, parameters)
                        return result
        
        return {'success': False, 'error': f'Tool {tool_name} not found'}
    
    def get_tools_by_category(self, category: str) -> List[MCPTool]:
        """Get tools filtered by category (if tools have category metadata)"""
        # This is a placeholder - can be extended based on tool metadata
        return [tool for tool in self.local_tools if hasattr(tool, 'category') and tool.category == category]
    
    def get_tools_info(self) -> List[Dict]:
        """Get information about all available tools"""
        tools_info = []
        
        for tool in self.local_tools:
            tools_info.append(tool.to_dict())
        
        for client in self.clients:
            for tool in client.tools:
                tools_info.append(tool.to_dict())
        
        return tools_info
    
    async def initialize(self):
        """Initialize all registered MCP servers"""
        for server_config in self.servers:
            name = server_config.get('name')
            url = server_config.get('url')
            command = server_config.get('command')
            
            await self.register_server(name, server_url=url, server_command=command)
        
        # Discover all tools
        await self.discover_all_tools()
        logger.info(f"MCP Integration initialized: {len(self.clients)} servers, {len(self.tools_cache)} tools")


# Global MCP integration instance
_mcp_instance = None

def get_mcp_integration(workspace_root: Optional[str] = None) -> MCPIntegration:
    """Get or create global MCP integration instance"""
    global _mcp_instance
    if _mcp_instance is None:
        _mcp_instance = MCPIntegration(workspace_root)
    return _mcp_instance
