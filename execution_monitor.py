# -*- coding: utf-8 -*-
"""
Execution Monitor - Real-time tool execution monitoring
Tracks tool execution, captures output, and detects errors
"""

import os
import subprocess
import threading
import queue
import logging
import time
import re
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# Check if psutil is available
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not available - resource monitoring limited")


class ExecutionMonitor:
    """Monitors tool execution in real-time"""
    
    def __init__(self, workspace_root: Optional[str] = None):
        """
        Initialize execution monitor
        workspace_root: Workspace directory for execution logs
        """
        self.workspace_root = Path(workspace_root) if workspace_root else Path(os.getcwd())
        self.execution_logs = self.workspace_root / "execution_logs"
        self.execution_logs.mkdir(exist_ok=True)
        
        # Active executions
        self.active_executions: Dict[str, Dict] = {}
        
        # Execution history
        self.execution_history: List[Dict] = []
    
    def monitor_execution(self, command: str, cwd: Optional[str] = None, 
                         timeout: Optional[int] = None, capture_output: bool = True,
                         progress_callback: Optional[Callable[[str, float], None]] = None) -> Dict:
        """
        Monitor tool execution with adaptive timeout
        Returns execution result with monitoring data
        """
        # Use adaptive timeout if not provided
        if timeout is None:
            try:
                from timeout_config import get_timeout_for_command
                timeout = get_timeout_for_command(command)
                logger.info(f"Using adaptive timeout: {timeout}s for command: {command[:100]}")
            except ImportError:
                timeout = 300  # Default fallback
                logger.warning("timeout_config not available, using default 300s timeout")
        
        execution_id = f"exec_{int(time.time())}_{os.getpid()}"
        start_time = time.time()
        
        execution_data = {
            'execution_id': execution_id,
            'command': command,
            'start_time': datetime.now().isoformat(),
            'cwd': cwd or str(self.workspace_root),
            'timeout': timeout,
            'process_id': None,
            'status': 'running',
            'stdout': '',
            'stderr': '',
            'exit_code': None,
            'execution_time': 0,
            'resource_usage': {},
            'errors': []
        }
        
        self.active_executions[execution_id] = execution_data
        
        try:
            # Start process
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=cwd or str(self.workspace_root),
                stdout=subprocess.PIPE if capture_output else None,
                stderr=subprocess.PIPE if capture_output else None,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            execution_data['process_id'] = process.pid
            
            # Monitor process
            if capture_output:
                stdout_lines = []
                stderr_lines = []
                
                # Read output in real-time
                def read_stdout():
                    try:
                        for line in iter(process.stdout.readline, ''):
                            if not line:
                                break
                            stdout_lines.append(line)
                            execution_data['stdout'] += line
                    except Exception as e:
                        execution_data['errors'].append(f"Stdout read error: {e}")
                
                def read_stderr():
                    try:
                        for line in iter(process.stderr.readline, ''):
                            if not line:
                                break
                            stderr_lines.append(line)
                            execution_data['stderr'] += line
                    except Exception as e:
                        execution_data['errors'].append(f"Stderr read error: {e}")
                
                # Start reader threads
                stdout_thread = threading.Thread(target=read_stdout, daemon=True)
                stderr_thread = threading.Thread(target=read_stderr, daemon=True)
                stdout_thread.start()
                stderr_thread.start()
                
                # Monitor resource usage
                if PSUTIL_AVAILABLE:
                    try:
                        proc = psutil.Process(process.pid)
                        max_memory = 0
                        max_cpu = 0
                        
                        while process.poll() is None:
                            try:
                                memory_info = proc.memory_info()
                                cpu_percent = proc.cpu_percent()
                                max_memory = max(max_memory, memory_info.rss)
                                max_cpu = max(max_cpu, cpu_percent)
                                time.sleep(0.1)
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                break
                        
                        execution_data['resource_usage'] = {
                            'max_memory_mb': max_memory / (1024 * 1024),
                            'max_cpu_percent': max_cpu
                        }
                    except Exception as e:
                        logger.warning(f"Resource monitoring error: {e}")
                
                # Wait for process with timeout and progress reporting
                try:
                    # Progress reporting for long-running scans
                    if progress_callback and timeout > 60:  # Only for scans longer than 1 minute
                        elapsed = 0
                        last_progress_time = time.time()
                        progress_interval = max(30, timeout / 20)  # Report every 30s or 5% of timeout
                        
                        while process.poll() is None:
                            elapsed = time.time() - start_time
                            progress_pct = min(100, (elapsed / timeout) * 100)
                            
                            # Report progress periodically
                            if time.time() - last_progress_time >= progress_interval:
                                try:
                                    progress_msg = f"Scan in progress... {progress_pct:.1f}% ({elapsed/60:.1f}/{timeout/60:.1f} min)"
                                    progress_callback(progress_msg, progress_pct)
                                    last_progress_time = time.time()
                                except Exception as e:
                                    logger.debug(f"Progress callback error: {e}")
                            
                            # Check if process finished
                            if process.poll() is not None:
                                break
                            
                            time.sleep(1)  # Check every second
                        
                        # Final progress update
                        if progress_callback:
                            try:
                                progress_callback("Scan completed", 100.0)
                            except:
                                pass
                    else:
                        # Standard wait without progress reporting
                        process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    if progress_callback:
                        try:
                            progress_callback("Scan timed out - partial results may be available", 100.0)
                        except:
                            pass
                    process.kill()
                    process.wait()
                    execution_data['errors'].append(f"Execution timed out after {timeout}s")
                    execution_data['exit_code'] = 124
                
                # Wait for reader threads
                stdout_thread.join(timeout=1)
                stderr_thread.join(timeout=1)
                
            else:
                # No output capture, just wait (with progress reporting if callback provided)
                try:
                    if progress_callback and timeout > 60:
                        elapsed = 0
                        last_progress_time = time.time()
                        progress_interval = max(30, timeout / 20)
                        
                        while process.poll() is None:
                            elapsed = time.time() - start_time
                            progress_pct = min(100, (elapsed / timeout) * 100)
                            
                            if time.time() - last_progress_time >= progress_interval:
                                try:
                                    progress_msg = f"Scan in progress... {progress_pct:.1f}% ({elapsed/60:.1f}/{timeout/60:.1f} min)"
                                    progress_callback(progress_msg, progress_pct)
                                    last_progress_time = time.time()
                                except:
                                    pass
                            
                            if process.poll() is not None:
                                break
                            
                            time.sleep(1)
                        
                        if progress_callback:
                            try:
                                progress_callback("Scan completed", 100.0)
                            except:
                                pass
                    else:
                        process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    if progress_callback:
                        try:
                            progress_callback("Scan timed out - partial results may be available", 100.0)
                        except:
                            pass
                    process.kill()
                    process.wait()
                    execution_data['errors'].append(f"Execution timed out after {timeout}s")
                    execution_data['exit_code'] = 124
            
            execution_data['exit_code'] = process.returncode
            
        except Exception as e:
            execution_data['errors'].append(f"Execution error: {e}")
            execution_data['exit_code'] = 1
            execution_data['status'] = 'error'
        
        finally:
            execution_data['execution_time'] = time.time() - start_time
            execution_data['end_time'] = datetime.now().isoformat()
            execution_data['status'] = 'completed' if execution_data['exit_code'] == 0 else 'failed'
            
            # Remove from active executions
            if execution_id in self.active_executions:
                del self.active_executions[execution_id]
            
            # Add to history
            self.execution_history.append(execution_data.copy())
            
            # Keep only last 100 executions in memory
            if len(self.execution_history) > 100:
                self.execution_history = self.execution_history[-100:]
        
        return execution_data
    
    def get_execution_status(self, execution_id: str) -> Optional[Dict]:
        """Get status of active execution"""
        return self.active_executions.get(execution_id)
    
    def get_execution_history(self, limit: int = 10) -> List[Dict]:
        """Get execution history"""
        return self.execution_history[-limit:]
    
    def get_tool_success_rate(self, tool_name: str) -> float:
        """Calculate success rate for a tool"""
        tool_executions = [
            exec_data for exec_data in self.execution_history
            if tool_name in exec_data.get('command', '')
        ]
        
        if not tool_executions:
            return 0.0
        
        successful = sum(1 for exec_data in tool_executions if exec_data.get('exit_code') == 0)
        return successful / len(tool_executions)
    
    def get_tool_metrics(self, tool_name: str) -> Dict:
        """Get metrics for a tool"""
        tool_executions = [
            exec_data for exec_data in self.execution_history
            if tool_name in exec_data.get('command', '')
        ]
        
        if not tool_executions:
            return {
                'total_executions': 0,
                'success_rate': 0.0,
                'average_execution_time': 0.0,
                'average_memory_mb': 0.0
            }
        
        successful = [e for e in tool_executions if e.get('exit_code') == 0]
        failed = [e for e in tool_executions if e.get('exit_code') != 0]
        
        avg_time = sum(e.get('execution_time', 0) for e in tool_executions) / len(tool_executions)
        
        memory_usage = []
        for e in tool_executions:
            if 'resource_usage' in e and 'max_memory_mb' in e['resource_usage']:
                memory_usage.append(e['resource_usage']['max_memory_mb'])
        avg_memory = sum(memory_usage) / len(memory_usage) if memory_usage else 0.0
        
        return {
            'total_executions': len(tool_executions),
            'successful_executions': len(successful),
            'failed_executions': len(failed),
            'success_rate': len(successful) / len(tool_executions),
            'average_execution_time': avg_time,
            'average_memory_mb': avg_memory
        }
    
    def detect_errors(self, execution_data: Dict) -> List[str]:
        """Detect errors in execution"""
        errors = []
        
        # Check exit code
        if execution_data.get('exit_code') != 0:
            errors.append(f"Non-zero exit code: {execution_data.get('exit_code')}")
        
        # Check stderr
        stderr = execution_data.get('stderr', '')
        if stderr:
            # Look for error patterns
            error_patterns = [
                r'error',
                r'failed',
                r'exception',
                r'traceback',
                r'fatal',
                r'critical'
            ]
            for pattern in error_patterns:
                if re.search(pattern, stderr, re.IGNORECASE):
                    errors.append(f"Error pattern found in stderr: {pattern}")
                    break
        
        # Check for timeout
        if execution_data.get('execution_time', 0) >= execution_data.get('timeout', 300):
            errors.append("Execution timed out")
        
        # Check for empty output (might indicate error)
        if not execution_data.get('stdout') and not execution_data.get('stderr'):
            if execution_data.get('exit_code') != 0:
                errors.append("No output and non-zero exit code")
        
        # Add execution errors
        errors.extend(execution_data.get('errors', []))
        
        return errors
    
    def format_execution_report(self, execution_data: Dict) -> str:
        """Format execution data as report"""
        lines = []
        lines.append("=" * 60)
        lines.append("EXECUTION MONITORING REPORT")
        lines.append("=" * 60)
        
        lines.append(f"\nCommand: {execution_data.get('command')}")
        lines.append(f"Execution ID: {execution_data.get('execution_id')}")
        lines.append(f"Status: {execution_data.get('status', 'unknown')}")
        lines.append(f"Exit Code: {execution_data.get('exit_code', 'N/A')}")
        lines.append(f"Execution Time: {execution_data.get('execution_time', 0):.2f}s")
        
        if execution_data.get('resource_usage'):
            usage = execution_data['resource_usage']
            lines.append(f"Max Memory: {usage.get('max_memory_mb', 0):.2f} MB")
            lines.append(f"Max CPU: {usage.get('max_cpu_percent', 0):.2f}%")
        
        if execution_data.get('stdout'):
            lines.append(f"\nStdout ({len(execution_data['stdout'])} chars):")
            stdout_preview = execution_data['stdout'][:500]
            lines.append(stdout_preview)
            if len(execution_data['stdout']) > 500:
                lines.append("... (truncated)")
        
        if execution_data.get('stderr'):
            lines.append(f"\nStderr ({len(execution_data['stderr'])} chars):")
            stderr_preview = execution_data['stderr'][:500]
            lines.append(stderr_preview)
            if len(execution_data['stderr']) > 500:
                lines.append("... (truncated)")
        
        errors = self.detect_errors(execution_data)
        if errors:
            lines.append("\nErrors Detected:")
            for error in errors:
                lines.append(f"  - {error}")
        
        lines.append("\n" + "=" * 60)
        
        return "\n".join(lines)


# Global execution monitor instance
_monitor_instance = None

def get_execution_monitor(workspace_root: Optional[str] = None) -> ExecutionMonitor:
    """Get or create global execution monitor instance"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = ExecutionMonitor(workspace_root)
    return _monitor_instance
