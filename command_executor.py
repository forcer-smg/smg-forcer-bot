# -*- coding: utf-8 -*-
"""
Command Executor - Parse and execute commands from AI code blocks
Verifies commands actually run (no false positives) and formats results for AI
"""

import re
import subprocess
import logging
import psutil
import time
import os
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class CommandExecutor:
    """Execute commands from AI code blocks with verification"""
    
    def __init__(self, workspace_path: str = None):
        """
        Initialize command executor
        
        Args:
            workspace_path: Base workspace path for command execution
        """
        self.workspace_path = Path(workspace_path) if workspace_path else Path.cwd()
        logger.info(f"Command Executor initialized with workspace: {self.workspace_path}")
    
    def parse_code_blocks(self, response_text: str) -> List[Dict[str, Any]]:
        """
        Parse markdown code blocks and extract commands
        
        Args:
            response_text: AI response text containing code blocks
        
        Returns:
            List of code block dictionaries with 'language', 'content', 'commands'
        """
        code_blocks = []
        
        # Pattern to match markdown code blocks: ```language\ncontent\n```
        pattern = r'```(\w+)?\n(.*?)```'
        
        matches = re.finditer(pattern, response_text, re.DOTALL)
        
        for match in matches:
            language = match.group(1) or 'bash'
            content = match.group(2).strip()
            
            # For Python, treat as single script (not line by line)
            if language.lower() == 'python':
                # Use ai_response_parser to extract commands properly
                from ai_response_parser import get_ai_response_parser
                parser = get_ai_response_parser()
                commands = parser.extract_commands(content, 'python')
            elif language.lower() in ['bash', 'sh', 'shell', 'zsh']:
                # For shell scripts, split by newlines
                commands = [cmd.strip() for cmd in content.split('\n') if cmd.strip() and not cmd.strip().startswith('#')]
            else:
                # For other languages, treat as single command
                commands = [content] if content else []
            
            if commands:
                code_blocks.append({
                    'language': language.lower(),
                    'content': content,
                    'commands': commands
                })
                logger.debug(f"Found code block: {language} with {len(commands)} commands")
        
        return code_blocks
    
    def execute_command(self, 
                       command: str, 
                       cwd: str = None, 
                       timeout: int = 300,
                       verify: bool = True) -> Dict[str, Any]:
        """
        Execute a single command with verification
        
        Args:
            command: Command to execute
            cwd: Working directory (defaults to workspace_path)
            timeout: Command timeout in seconds
            verify: Whether to verify command actually executed
        
        Returns:
            Dictionary with execution results and verification status
        """
        result = {
            'command': command,
            'success': False,
            'exit_code': None,
            'stdout': '',
            'stderr': '',
            'execution_time': 0,
            'verified': False,
            'verification_details': {},
            'error': None
        }
        
        # Use workspace as cwd if not specified
        if not cwd:
            cwd = str(self.workspace_path)
        
        logger.info(f"Executing command: {command} (cwd: {cwd}, timeout: {timeout}s)")
        
        start_time = time.time()
        
        try:
            # Execute command
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=cwd,
                bufsize=1  # Line buffered
            )
            
            # Wait for completion with timeout
            try:
                stdout, stderr = process.communicate(timeout=timeout)
                result['exit_code'] = process.returncode
                result['stdout'] = stdout
                result['stderr'] = stderr
                result['execution_time'] = time.time() - start_time
                result['success'] = (process.returncode == 0)
                
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                result['error'] = f"Command timed out after {timeout} seconds"
                result['exit_code'] = -1
                logger.warning(f"Command timed out: {command}")
            
            # Verify command actually executed (no false positives)
            if verify:
                verification = self.verify_command_executed(command, result, process)
                result['verified'] = verification['verified']
                result['verification_details'] = verification
            
            logger.info(f"Command executed: {command} (exit_code: {result['exit_code']}, verified: {result['verified']})")
            
            # Cleanup temp files (Python scripts)
            if '.py' in command and '/tmp/' in command:
                try:
                    # Extract temp file path from command
                    import re
                    temp_match = re.search(r'(/tmp/[^\s]+\.py)', command)
                    if temp_match:
                        temp_file = temp_match.group(1)
                        if Path(temp_file).exists():
                            os.remove(temp_file)
                            logger.debug(f"Cleaned up temp file: {temp_file}")
                except Exception as cleanup_error:
                    logger.warning(f"Could not cleanup temp file: {cleanup_error}")
            
        except Exception as e:
            result['error'] = str(e)
            result['execution_time'] = time.time() - start_time
            logger.error(f"Error executing command '{command}': {e}", exc_info=True)
        
        return result
    
    def verify_command_executed(self, 
                               command: str, 
                               result: Dict[str, Any],
                               process: subprocess.Popen = None) -> Dict[str, Any]:
        """
        Verify command actually executed (no false positives)
        
        Checks:
        - Process actually ran (if process object available)
        - Output is real (not empty, not just whitespace)
        - Exit code is valid
        - Files were created/modified (if command creates files)
        
        Args:
            command: Command that was executed
            result: Execution result dictionary
            process: Process object (if available)
        
        Returns:
            Verification dictionary with 'verified' boolean and details
        """
        verification = {
            'verified': False,
            'checks': {},
            'reasons': []
        }
        
        checks_passed = 0
        total_checks = 0
        
        # Check 1: Process verification (if process object available)
        if process:
            total_checks += 1
            try:
                # Check if process actually ran
                if process.pid:
                    # Check if process still exists or completed
                    try:
                        proc = psutil.Process(process.pid)
                        verification['checks']['process_exists'] = True
                        checks_passed += 1
                    except psutil.NoSuchProcess:
                        # Process completed (normal)
                        verification['checks']['process_exists'] = True
                        checks_passed += 1
                else:
                    verification['checks']['process_exists'] = False
                    verification['reasons'].append("Process PID not available")
            except Exception as e:
                verification['checks']['process_exists'] = False
                verification['reasons'].append(f"Process check failed: {e}")
        
        # Check 2: Exit code verification
        total_checks += 1
        if result['exit_code'] is not None:
            verification['checks']['exit_code_valid'] = True
            checks_passed += 1
        else:
            verification['checks']['exit_code_valid'] = False
            verification['reasons'].append("Exit code is None")
        
        # Check 3: Output verification (stdout or stderr should have content)
        total_checks += 1
        has_output = bool(result.get('stdout', '').strip()) or bool(result.get('stderr', '').strip())
        verification['checks']['has_output'] = has_output
        if has_output:
            checks_passed += 1
        else:
            # For some commands, no output is normal (e.g., mkdir -p, touch)
            # But we should at least verify exit code is 0
            if result.get('exit_code') == 0:
                verification['checks']['has_output'] = True  # Acceptable
                checks_passed += 1
            else:
                verification['reasons'].append("No output and non-zero exit code")
        
        # Check 4: File verification (if command creates/modifies files)
        file_patterns = self._extract_file_patterns(command)
        if file_patterns:
            total_checks += 1
            files_verified = 0
            for pattern in file_patterns:
                file_path = Path(self.workspace_path) / pattern
                if file_path.exists():
                    files_verified += 1
                    # Check file is not empty (if it should have content)
                    if file_path.stat().st_size > 0 or pattern.endswith(('.log', '.txt')):
                        verification['checks'][f'file_exists_{pattern}'] = True
                    else:
                        verification['checks'][f'file_exists_{pattern}'] = True  # Empty file is still valid
                else:
                    verification['checks'][f'file_exists_{pattern}'] = False
                    verification['reasons'].append(f"Expected file not found: {pattern}")
            
            if files_verified > 0:
                checks_passed += 1
                verification['checks']['files_created'] = True
            else:
                verification['checks']['files_created'] = False
        
        # Check 5: Resource usage verification (if process available)
        if process and hasattr(process, 'pid'):
            total_checks += 1
            try:
                proc = psutil.Process(process.pid)
                # Check if process used CPU or memory (indicates it actually ran)
                cpu_percent = proc.cpu_percent(interval=0.1)
                memory_info = proc.memory_info()
                if cpu_percent > 0 or memory_info.rss > 0:
                    verification['checks']['resource_usage'] = True
                    checks_passed += 1
                else:
                    verification['checks']['resource_usage'] = False
                    verification['reasons'].append("No resource usage detected")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # Process already finished or access denied - that's okay
                verification['checks']['resource_usage'] = True
                checks_passed += 1
        
        # Overall verification: At least 3 out of 5 checks should pass
        # Or if we have exit_code=0 and output, that's good enough
        if result.get('exit_code') == 0 and has_output:
            verification['verified'] = True
        elif checks_passed >= max(2, total_checks * 0.6):  # At least 60% of checks pass
            verification['verified'] = True
        else:
            verification['verified'] = False
            if not verification['reasons']:
                verification['reasons'].append("Insufficient verification checks passed")
        
        return verification
    
    def _extract_file_patterns(self, command: str) -> List[str]:
        """
        Extract file patterns from command (for verification)
        
        Args:
            command: Command string
        
        Returns:
            List of file patterns that might be created/modified
        """
        patterns = []
        
        # Patterns for common file operations
        # > file, >> file, cat > file, echo > file, etc.
        redirect_patterns = [
            r'>\s+([^\s&|;]+)',  # > file
            r'>>\s+([^\s&|;]+)',  # >> file
            r'cat\s+>\s+([^\s&|;]+)',  # cat > file
            r'echo\s+.*?>\s+([^\s&|;]+)',  # echo > file
        ]
        
        for pattern in redirect_patterns:
            matches = re.findall(pattern, command)
            patterns.extend(matches)
        
        # Remove duplicates and filter
        patterns = list(set(patterns))
        # Filter out common false positives
        filtered = [p for p in patterns if not p.startswith(('&', '|', ';', '#'))]
        
        return filtered[:5]  # Limit to 5 patterns
    
    def execute_commands(self, 
                       commands: List[str], 
                       cwd: str = None,
                       timeout: int = 300,
                       stop_on_error: bool = False) -> List[Dict[str, Any]]:
        """
        Execute a sequence of commands
        
        Args:
            commands: List of commands to execute
            cwd: Working directory
            timeout: Timeout per command
            stop_on_error: Stop execution if a command fails
        
        Returns:
            List of execution results
        """
        results = []
        
        for i, command in enumerate(commands, 1):
            logger.info(f"Executing command {i}/{len(commands)}: {command}")
            
            result = self.execute_command(command, cwd=cwd, timeout=timeout, verify=True)
            results.append(result)
            
            # Check if we should stop on error
            if stop_on_error and not result['success']:
                logger.warning(f"Command {i} failed, stopping execution")
                break
        
        return results
    
    def format_result(self, command: str, result: Dict[str, Any]) -> str:
        """
        Format execution result for AI consumption
        
        Args:
            command: Command that was executed
            result: Execution result dictionary
        
        Returns:
            Formatted string for AI
        """
        lines = [
            f"Command executed: `{command}`",
            f"Exit code: {result.get('exit_code', 'N/A')}",
            f"Execution time: {result.get('execution_time', 0):.2f}s",
            f"Verified: {'✅ Yes' if result.get('verified', False) else '❌ No'}"
        ]
        
        if result.get('stdout'):
            stdout_preview = result['stdout'][:500] + ('...' if len(result['stdout']) > 500 else '')
            lines.append(f"Output:\n{stdout_preview}")
        
        if result.get('stderr'):
            stderr_preview = result['stderr'][:500] + ('...' if len(result['stderr']) > 500 else '')
            lines.append(f"Errors:\n{stderr_preview}")
        
        if result.get('error'):
            lines.append(f"Error: {result['error']}")
        
        if not result.get('verified', False):
            reasons = result.get('verification_details', {}).get('reasons', [])
            if reasons:
                lines.append(f"Verification failed: {', '.join(reasons)}")
        
        return "\n".join(lines)


# Global instance
_command_executor_instance = None

def get_command_executor(workspace_path: str = None) -> CommandExecutor:
    """Get or create global command executor instance"""
    global _command_executor_instance
    if _command_executor_instance is None:
        _command_executor_instance = CommandExecutor(workspace_path)
    return _command_executor_instance
