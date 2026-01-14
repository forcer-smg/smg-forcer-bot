# -*- coding: utf-8 -*-
"""
Continuous Executor - Keep executing until results are delivered to user
Ensures tasks complete and files are sent, even after redeployments
"""

import logging
import asyncio
import time
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class ContinuousExecutor:
    """Execute tasks continuously until results are delivered"""
    
    def __init__(self, max_iterations: int = 10, check_interval: float = 2.0):
        """
        Initialize continuous executor
        
        Args:
            max_iterations: Maximum number of execution iterations
            check_interval: Seconds between result checks
        """
        self.max_iterations = max_iterations
        self.check_interval = check_interval
        logger.info("Continuous Executor initialized")
    
    async def execute_until_delivered(self,
                                    task_description: str,
                                    execution_function: Callable,
                                    expected_results: List[str],
                                    result_checker: Callable = None,
                                    user_id: int = None,
                                    workspace_path: str = None) -> Dict[str, Any]:
        """
        Execute task continuously until all expected results are delivered
        
        Args:
            task_description: Description of the task
            execution_function: Async function that executes the task
            expected_results: List of expected result types (e.g., ['file', 'message', 'id_image'])
            result_checker: Optional function to check if results exist
            user_id: User ID (for state persistence)
            workspace_path: Workspace path (for checking files)
        
        Returns:
            Dictionary with execution results
        """
        logger.info(f"Starting continuous execution: {task_description}")
        
        # Save pending task to state
        if user_id:
            try:
                from user_state_manager import get_user_state_manager
                state_mgr = get_user_state_manager()
                state_mgr.save_pending_task(
                    user_id,
                    task_description,
                    'continuous',
                    expected_results,
                    workspace_path
                )
            except Exception as e:
                logger.warning(f"Could not save pending task: {e}")
        
        delivered_results = []
        iteration = 0
        
        while iteration < self.max_iterations:
            iteration += 1
            logger.info(f"Execution iteration {iteration}/{self.max_iterations}")
            
            try:
                # Execute the task
                execution_result = await execution_function()
                
                # Check if results were delivered
                if result_checker:
                    results = await result_checker(execution_result, expected_results, workspace_path)
                else:
                    results = self._default_result_checker(execution_result, expected_results, workspace_path)
                
                # Track delivered results
                for result in results:
                    if result not in delivered_results:
                        delivered_results.append(result)
                        if user_id:
                            try:
                                from user_state_manager import get_user_state_manager
                                state_mgr = get_user_state_manager()
                                state_mgr.mark_result_delivered(user_id, result['type'], result.get('path'))
                            except Exception as e:
                                logger.warning(f"Could not mark result delivered: {e}")
                
                # Check if all expected results are delivered
                expected_types = [r if isinstance(r, str) else r.get('type') for r in expected_results]
                delivered_types = [r['type'] for r in delivered_results]
                
                all_delivered = all(exp_type in delivered_types for exp_type in expected_types)
                
                if all_delivered:
                    logger.info(f"All results delivered after {iteration} iterations")
                    if user_id:
                        try:
                            from user_state_manager import get_user_state_manager
                            state_mgr = get_user_state_manager()
                            state_mgr.clear_pending_task(user_id)
                        except Exception as e:
                            logger.warning(f"Could not clear pending task: {e}")
                    
                    return {
                        'success': True,
                        'iterations': iteration,
                        'delivered_results': delivered_results,
                        'execution_result': execution_result
                    }
                
                # Wait before next iteration
                if iteration < self.max_iterations:
                    logger.info(f"Not all results delivered yet. Waiting {self.check_interval}s before next iteration...")
                    await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in execution iteration {iteration}: {e}", exc_info=True)
                if iteration < self.max_iterations:
                    await asyncio.sleep(self.check_interval)
                else:
                    return {
                        'success': False,
                        'error': str(e),
                        'iterations': iteration,
                        'delivered_results': delivered_results
                    }
        
        # Max iterations reached
        logger.warning(f"Max iterations reached. Delivered: {delivered_results}")
        return {
            'success': False,
            'iterations': iteration,
            'delivered_results': delivered_results,
            'message': 'Max iterations reached, not all results delivered'
        }
    
    def _default_result_checker(self, execution_result: Any, expected_results: List[str], workspace_path: str = None) -> List[Dict]:
        """
        Default result checker - checks for files in workspace
        
        Args:
            execution_result: Result from execution function
            expected_results: List of expected result types
            workspace_path: Workspace path to check
        
        Returns:
            List of delivered results
        """
        delivered = []
        
        if not workspace_path:
            return delivered
        
        workspace = Path(workspace_path)
        if not workspace.exists():
            return delivered
        
        # Check for common result file patterns
        result_patterns = {
            'file': ['*.py', '*.txt', '*.json', '*.md'],
            'id_image': ['*id*.png', '*id*.jpg', '*texas*.png', '*driver*.png'],
            'document': ['*.pdf', '*.docx', '*.xlsx'],
            'image': ['*.png', '*.jpg', '*.jpeg'],
            'script': ['*.py', '*.sh', '*.js']
        }
        
        for result_type in expected_results:
            if isinstance(result_type, str):
                patterns = result_patterns.get(result_type.lower(), [])
                for pattern in patterns:
                    files = list(workspace.rglob(pattern))
                    if files:
                        # Get most recent file
                        latest_file = max(files, key=lambda p: p.stat().st_mtime)
                        delivered.append({
                            'type': result_type,
                            'path': str(latest_file),
                            'file': latest_file.name,
                            'size': latest_file.stat().st_size,
                            'modified': datetime.fromtimestamp(latest_file.stat().st_mtime).isoformat()
                        })
                        break
        
        return delivered
    
    async def check_and_resume_task(self, user_id: int) -> Optional[Dict]:
        """
        Check if user has pending task and resume execution
        
        Args:
            user_id: User ID
        
        Returns:
            Task info if pending task found, None otherwise
        """
        try:
            from user_state_manager import get_user_state_manager
            state_mgr = get_user_state_manager()
            
            pending_task = state_mgr.get_pending_task(user_id)
            if pending_task:
                logger.info(f"Found pending task for user {user_id}: {pending_task.get('task_description')}")
                return pending_task
            
            return None
            
        except Exception as e:
            logger.warning(f"Could not check pending task: {e}")
            return None


# Global instance
_continuous_executor_instance = None

def get_continuous_executor(max_iterations: int = 10, check_interval: float = 2.0) -> ContinuousExecutor:
    """Get or create global continuous executor instance"""
    global _continuous_executor_instance
    if _continuous_executor_instance is None:
        _continuous_executor_instance = ContinuousExecutor(max_iterations, check_interval)
    return _continuous_executor_instance
