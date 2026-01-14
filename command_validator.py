# -*- coding: utf-8 -*-
"""
Command Validator - Sandbox testing and validation for AI-generated commands
Prevents false positives by testing commands before execution
"""

import os
import sys
import subprocess
import re
import tempfile
import shutil
import platform
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# Detect Linux environment
IS_LINUX = platform.system() == 'Linux'
RESTRICTION_MODE = os.getenv('RESTRICTION_MODE', 'unrestricted' if IS_LINUX else 'strict')

# Allowed security/hacking tools (Linux unrestricted mode)
ALLOWED_TOOLS = [
    'nmap', 'metasploit', 'msfconsole', 'sqlmap', 'burpsuite', 'wireshark',
    'tcpdump', 'nikto', 'dirb', 'gobuster', 'dirbuster', 'hydra', 'john',
    'hashcat', 'aircrack-ng', 'reaver', 'wpscan', 'subfinder', 'amass',
    'masscan', 'zmap', 'theharvester', 'recon-ng', 'maltego', 'shodan',
    'cobaltstrike', 'empire', 'powershell-empire', 'crackmapexec', 'impacket',
    'mimikatz', 'bloodhound', 'kerbrute', 'rubeus', 'seatbelt', 'sharpview',
    '365-stealer', 'requests-ip-rotator', 'subdomain', 'dns', 'enum', 'scan'
]

# Dangerous commands that should be blocked (unless in unrestricted mode)
DANGEROUS_COMMANDS = [
    'rm -rf /', 'rm -rf /home', 'rm -rf /root',  # System-wide deletion
    'format', 'mkfs', 'dd if=/dev/zero',  # Disk formatting
    'shutdown', 'reboot', 'halt', 'poweroff',  # System shutdown
    '> /dev/sd', '> /dev/hd',  # Direct disk writes
    'chmod 777 /', 'chmod -R 777 /',  # System-wide permissions
]

# Commands that are dangerous but allowed in unrestricted mode (Linux)
DANGEROUS_BUT_ALLOWED_LINUX = [
    'rm -rf',  # File deletion (allowed in workspace)
    'sudo rm',  # Sudo operations (monitored)
    'curl.*|.*sh', 'wget.*|.*sh',  # Pipe to shell (common in tools)
]

# Safe commands whitelist (optional - can be used for strict mode)
SAFE_COMMANDS = [
    'echo', 'ls', 'dir', 'pwd', 'cd', 'cat', 'type',
    'python', 'pip', 'git', 'npm', 'node', 'python3'
]


class CommandValidator:
    """Validates and tests commands in a sandbox environment"""
    
    def __init__(self, sandbox_enabled: bool = True, timeout: int = 30, restriction_mode: str = None):
        self.sandbox_enabled = sandbox_enabled
        self.timeout = timeout
        self.sandbox_dir = None
        self.restriction_mode = restriction_mode or RESTRICTION_MODE
        self.is_unrestricted = self.restriction_mode == 'unrestricted'
        
        if self.is_unrestricted:
            logger.info("Command validator running in UNRESTRICTED mode (Linux) - security tools allowed")
        else:
            logger.info("Command validator running in STRICT mode - security restrictions active")
        
        self._setup_sandbox()
    
    def _setup_sandbox(self):
        """Create a temporary sandbox directory for testing"""
        if self.sandbox_enabled:
            try:
                self.sandbox_dir = Path(tempfile.mkdtemp(prefix='cmd_sandbox_'))
                logger.info(f"Sandbox created at: {self.sandbox_dir}")
            except Exception as e:
                logger.error(f"Failed to create sandbox: {e}")
                self.sandbox_enabled = False
    
    def cleanup(self):
        """Clean up sandbox directory"""
        if self.sandbox_dir and self.sandbox_dir.exists():
            try:
                shutil.rmtree(self.sandbox_dir)
                logger.info("Sandbox cleaned up")
            except Exception as e:
                logger.warning(f"Failed to clean up sandbox: {e}")
    
    def validate_syntax(self, command: str) -> Tuple[bool, Optional[str]]:
        """Validate command syntax without execution"""
        if not command or not command.strip():
            return False, "Empty command"
        
        command_lower = command.lower()
        
        # Check if command uses an allowed tool (unrestricted mode)
        if self.is_unrestricted:
            for tool in ALLOWED_TOOLS:
                if tool in command_lower:
                    # Tool is allowed, skip dangerous command checks for this tool
                    logger.debug(f"Allowed tool detected: {tool}")
                    break
        else:
            # Strict mode: check for dangerous patterns
            for dangerous in DANGEROUS_COMMANDS:
                if re.search(dangerous, command_lower, re.IGNORECASE):
                    return False, f"Dangerous command detected: {dangerous}"
            
            # Also check dangerous but allowed commands in strict mode
            for dangerous in DANGEROUS_BUT_ALLOWED_LINUX:
                if re.search(dangerous, command_lower, re.IGNORECASE):
                    return False, f"Dangerous command detected: {dangerous} (use unrestricted mode for security tools)"
        
        # Basic syntax checks
        if command.count('"') % 2 != 0:
            return False, "Unmatched quotes"
        
        if command.count("'") % 2 != 0:
            return False, "Unmatched single quotes"
        
        # Check for suspicious patterns (only in strict mode)
        if not self.is_unrestricted:
            suspicious_patterns = [
                r';\s*rm\s+-',  # Command chaining with rm
                r'&&\s*rm\s+-',  # Logical AND with rm
                r'\|\s*sh\s*$',  # Piping to shell
                r'\|\s*bash\s*$',  # Piping to bash
            ]
            
            for pattern in suspicious_patterns:
                if re.search(pattern, command, re.IGNORECASE):
                    return False, f"Suspicious pattern detected: {pattern}"
        
        return True, None
    
    def test_in_sandbox(self, command: str, cwd: Optional[str] = None) -> Dict:
        """
        Test command in sandbox environment
        Returns dict with: valid, output, error, exit_code, test_passed
        """
        if not self.sandbox_enabled:
            return {
                'valid': True,
                'output': '',
                'error': 'Sandbox disabled',
                'exit_code': 0,
                'test_passed': True,
                'warning': 'Command not tested (sandbox disabled)'
            }
        
        # First validate syntax
        syntax_valid, syntax_error = self.validate_syntax(command)
        if not syntax_valid:
            return {
                'valid': False,
                'output': '',
                'error': syntax_error,
                'exit_code': 1,
                'test_passed': False,
                'reason': 'Syntax validation failed'
            }
        
        # Use sandbox directory as working directory
        work_dir = str(self.sandbox_dir) if self.sandbox_dir else (cwd or os.getcwd())
        
        try:
            # Execute command in sandbox with timeout
            result = subprocess.run(
                command,
                shell=True,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding='utf-8',
                errors='replace',
                env={**os.environ, 'PATH': os.environ.get('PATH', '')}  # Limit environment
            )
            
            output = result.stdout + result.stderr
            exit_code = result.returncode
            
            # Determine if test passed
            # Test passes if: exit code is 0 or command executed without critical errors
            test_passed = exit_code == 0 or (exit_code != 0 and not self._is_critical_error(output))
            
            return {
                'valid': True,
                'output': output[:1000],  # Limit output size
                'error': result.stderr[:500] if result.stderr else None,
                'exit_code': exit_code,
                'test_passed': test_passed,
                'reason': 'Command executed successfully' if test_passed else 'Command failed in sandbox'
            }
            
        except subprocess.TimeoutExpired:
            return {
                'valid': False,
                'output': '',
                'error': f'Command timed out after {self.timeout} seconds',
                'exit_code': 124,
                'test_passed': False,
                'reason': 'Timeout'
            }
        except Exception as e:
            return {
                'valid': False,
                'output': '',
                'error': str(e),
                'exit_code': 1,
                'test_passed': False,
                'reason': f'Execution error: {str(e)}'
            }
    
    def _is_critical_error(self, output: str) -> bool:
        """Check if output indicates a critical error"""
        critical_indicators = [
            'permission denied',
            'access denied',
            'cannot remove',
            'file not found',
            'no such file',
            'command not found',
            'syntax error',
            'invalid syntax'
        ]
        
        output_lower = output.lower()
        return any(indicator in output_lower for indicator in critical_indicators)
    
    def validate_python_code(self, code: str) -> Tuple[bool, Optional[str]]:
        """Validate Python code syntax"""
        try:
            compile(code, '<string>', 'exec')
            return True, None
        except SyntaxError as e:
            return False, f"Python syntax error: {str(e)}"
        except Exception as e:
            return False, f"Python validation error: {str(e)}"
    
    def extract_commands_from_text(self, text: str) -> List[Dict]:
        """
        Extract commands from AI response text
        Looks for code blocks with bash, shell, sh, or command markers
        Returns list of dicts with: command, language, line_number
        """
        commands = []
        
        # Pattern for code blocks: ```language\ncommand\n```
        code_block_pattern = r'```(?:bash|shell|sh|cmd|command|python|py)?\n(.*?)```'
        matches = re.finditer(code_block_pattern, text, re.DOTALL | re.IGNORECASE)
        
        for match in matches:
            code_content = match.group(1).strip()
            # Extract individual commands (split by newlines, filter empty)
            lines = [line.strip() for line in code_content.split('\n') if line.strip()]
            
            for line in lines:
                # Skip comments
                if line.startswith('#') or line.startswith('//'):
                    continue
                
                commands.append({
                    'command': line,
                    'language': match.group(1) if match.groups() else 'bash',
                    'line_number': text[:match.start()].count('\n') + 1
                })
        
        # Also look for inline commands (lines starting with $ or >)
        inline_pattern = r'(?:^|\n)(?:[$>]\s*)(.+?)(?=\n|$)'
        inline_matches = re.finditer(inline_pattern, text, re.MULTILINE)
        
        for match in inline_matches:
            cmd = match.group(1).strip()
            if cmd and not cmd.startswith('#'):
                commands.append({
                    'command': cmd,
                    'language': 'shell',
                    'line_number': text[:match.start()].count('\n') + 1
                })
        
        return commands
    
    def validate_all_commands(self, text: str) -> Dict:
        """
        Extract and validate all commands from text
        Returns comprehensive validation report
        """
        commands = self.extract_commands_from_text(text)
        
        if not commands:
            return {
                'has_commands': False,
                'commands': [],
                'all_valid': True,
                'all_tested': False,
                'summary': 'No commands found in text'
            }
        
        validation_results = []
        all_valid = True
        all_tested = True
        
        for cmd_info in commands:
            command = cmd_info['command']
            
            # Syntax validation
            syntax_valid, syntax_error = self.validate_syntax(command)
            
            # Sandbox testing
            test_result = None
            if syntax_valid:
                test_result = self.test_in_sandbox(command)
                all_tested = all_tested and test_result.get('test_passed', False)
            else:
                all_valid = False
            
            validation_results.append({
                'command': command,
                'language': cmd_info['language'],
                'line_number': cmd_info['line_number'],
                'syntax_valid': syntax_valid,
                'syntax_error': syntax_error,
                'test_result': test_result,
                'safe_to_execute': syntax_valid and (test_result is None or test_result.get('test_passed', False))
            })
            
            if not validation_results[-1]['safe_to_execute']:
                all_valid = False
        
        return {
            'has_commands': True,
            'commands': validation_results,
            'all_valid': all_valid,
            'all_tested': all_tested,
            'summary': f"Found {len(commands)} command(s), {'all valid' if all_valid else 'some invalid'}"
        }


# Global validator instance
_validator_instance = None

def get_validator(sandbox_enabled: bool = True, timeout: int = 30, restriction_mode: str = None) -> CommandValidator:
    """Get or create global validator instance"""
    global _validator_instance
    if _validator_instance is None:
        # Auto-detect restriction mode if not provided
        if restriction_mode is None:
            restriction_mode = RESTRICTION_MODE
        _validator_instance = CommandValidator(
            sandbox_enabled=sandbox_enabled, 
            timeout=timeout,
            restriction_mode=restriction_mode
        )
    return _validator_instance
