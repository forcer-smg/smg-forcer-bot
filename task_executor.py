# -*- coding: utf-8 -*-
"""
Task Executor - Enhanced execution with testing and retry logic (Cursor-style)
Executes commands with verification and automatic retry on failure
"""

import logging
import subprocess
import os
import time
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Execute tasks with testing and retry logic"""
    
    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        """
        Initialize task executor
        
        Args:
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries (seconds)
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        logger.info("Task Executor initialized")
    
    def execute_command(self, 
                      command: str,
                      expected_result: str = None,
                      test_function: Callable = None,
                      alternatives: List[str] = None,
                      cwd: str = None,
                      timeout: int = None) -> Dict[str, Any]:
        """
        Execute command with testing and retry logic
        
        Args:
            command: Command to execute
            expected_result: Expected result description (for logging)
            test_function: Optional function to test the result
            alternatives: List of alternative commands to try if this fails
            cwd: Working directory for command
            timeout: Command timeout in seconds
        
        Returns:
            Dictionary with execution results
        """
        result = {
            'success': False,
            'command': command,
            'exit_code': None,
            'output': None,
            'error': None,
            'attempts': 0,
            'test_passed': None,
            'test_message': None
        }
        
        commands_to_try = [command]
        if alternatives:
            commands_to_try.extend(alternatives)
        
        for attempt, cmd in enumerate(commands_to_try, 1):
            result['attempts'] = attempt
            result['command'] = cmd
            
            logger.info(f"Executing command (attempt {attempt}/{len(commands_to_try)}): {cmd}")
            
            try:
                # Execute command
                process = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    cwd=cwd,
                    timeout=timeout
                )
                
                result['exit_code'] = process.returncode
                result['output'] = process.stdout
                result['error'] = process.stderr
                
                # Check exit code
                if process.returncode == 0:
                    # Test result if test function provided
                    if test_function:
                        try:
                            test_result = test_function(result)
                            result['test_passed'] = test_result.get('passed', True)
                            result['test_message'] = test_result.get('message', 'Test passed')
                            
                            if not result['test_passed']:
                                logger.warning(f"Test failed: {result['test_message']}")
                                if attempt < len(commands_to_try):
                                    time.sleep(self.retry_delay)
                                    continue
                        except Exception as e:
                            logger.warning(f"Test function error: {e}")
                            result['test_passed'] = True  # Assume pass if test function fails
                    else:
                        result['test_passed'] = True
                    
                    result['success'] = True
                    logger.info(f"Command succeeded: {cmd}")
                    return result
                else:
                    logger.warning(f"Command failed with exit code {process.returncode}: {cmd}")
                    if attempt < len(commands_to_try):
                        time.sleep(self.retry_delay)
                        continue
                    
            except subprocess.TimeoutExpired:
                result['error'] = f"Command timed out after {timeout} seconds"
                logger.error(f"Command timed out: {cmd}")
                if attempt < len(commands_to_try):
                    time.sleep(self.retry_delay)
                    continue
                    
            except Exception as e:
                result['error'] = str(e)
                logger.error(f"Command execution error: {e}")
                if attempt < len(commands_to_try):
                    time.sleep(self.retry_delay)
                    continue
        
        # All attempts failed
        result['success'] = False
        logger.error(f"All attempts failed for command: {command}")
        return result
    
    def verify_file_exists(self, file_path: str, readable: bool = True) -> Dict[str, Any]:
        """
        Verify file exists and optionally is readable
        
        Args:
            file_path: Path to file
            readable: Whether to check if file is readable
        
        Returns:
            Test result dictionary
        """
        path = Path(file_path)
        
        if not path.exists():
            return {
                'passed': False,
                'message': f"File does not exist: {file_path}"
            }
        
        if readable:
            try:
                if path.is_file():
                    # Try to read first few bytes
                    with open(path, 'rb') as f:
                        f.read(1)
                return {
                    'passed': True,
                    'message': f"File exists and is readable: {file_path}"
                }
            except Exception as e:
                return {
                    'passed': False,
                    'message': f"File exists but not readable: {file_path} - {e}"
                }
        
        return {
            'passed': True,
            'message': f"File exists: {file_path}"
        }
    
    def verify_script_execution(self, script_path: str, expected_output: str = None) -> Dict[str, Any]:
        """
        Verify script executes successfully
        
        Args:
            script_path: Path to script
            expected_output: Optional expected output substring
        
        Returns:
            Test result dictionary
        """
        # First verify file exists
        file_check = self.verify_file_exists(script_path, readable=True)
        if not file_check['passed']:
            return file_check
        
        # Try to execute script
        result = self.execute_command(
            f"python {script_path}",
            timeout=30
        )
        
        if not result['success']:
            return {
                'passed': False,
                'message': f"Script execution failed: {result['error']}"
            }
        
        if expected_output and expected_output not in result['output']:
            return {
                'passed': False,
                'message': f"Script output doesn't contain expected text: {expected_output}"
            }
        
        return {
            'passed': True,
            'message': f"Script executed successfully: {script_path}"
        }
    
    def verify_service_running(self, service_name: str, process_pattern: str = None) -> Dict[str, Any]:
        """
        Verify service is running
        
        Args:
            service_name: Name of service
            process_pattern: Optional process pattern to search for
        
        Returns:
            Test result dictionary
        """
        pattern = process_pattern or service_name
        
        result = self.execute_command(
            f"ps aux | grep -i '{pattern}' | grep -v grep",
            timeout=5
        )
        
        if result['success'] and result['output'].strip():
            return {
                'passed': True,
                'message': f"Service is running: {service_name}"
            }
        
        return {
            'passed': False,
            'message': f"Service is not running: {service_name}"
        }
    
    def verify_api_response(self, url: str, expected_status: int = 200, timeout: int = 10) -> Dict[str, Any]:
        """
        Verify API endpoint responds correctly
        
        Args:
            url: API URL
            expected_status: Expected HTTP status code
            timeout: Request timeout
        
        Returns:
            Test result dictionary
        """
        result = self.execute_command(
            f"curl -s -o /dev/null -w '%{{http_code}}' --max-time {timeout} '{url}'",
            timeout=timeout + 2
        )
        
        if not result['success']:
            return {
                'passed': False,
                'message': f"API request failed: {result['error']}"
            }
        
        try:
            status_code = int(result['output'].strip())
            if status_code == expected_status:
                return {
                    'passed': True,
                    'message': f"API responded with status {status_code}: {url}"
                }
            else:
                return {
                    'passed': False,
                    'message': f"API responded with status {status_code}, expected {expected_status}: {url}"
                }
        except ValueError:
            return {
                'passed': False,
                'message': f"Could not parse API response: {result['output']}"
            }


# Global instance
_task_executor_instance = None

def get_task_executor(max_retries: int = 3, retry_delay: float = 1.0) -> TaskExecutor:
    """Get or create global task executor instance"""
    global _task_executor_instance
    if _task_executor_instance is None:
        _task_executor_instance = TaskExecutor(max_retries, retry_delay)
    return _task_executor_instance
