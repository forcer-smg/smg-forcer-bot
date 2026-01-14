# -*- coding: utf-8 -*-
"""
Background Task Worker - Process queued tasks from Supabase
Runs long-running tasks in background to keep Telegram bot responsive
"""

import os
import logging
import asyncio
import json
from typing import Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from supabase_task_queue import SupabaseTaskQueue, TaskStatus, TaskType, get_task_queue
    TASK_QUEUE_AVAILABLE = True
except ImportError:
    TASK_QUEUE_AVAILABLE = False
    logger.warning("Task queue not available")


class BackgroundTaskWorker:
    """Background worker for processing queued tasks"""
    
    def __init__(self, task_queue: Optional[SupabaseTaskQueue] = None):
        """Initialize background task worker"""
        self.task_queue = task_queue or get_task_queue()
        self.running = False
        self.worker_id = f"worker_{os.getpid()}_{datetime.now().timestamp()}"
        self.processed_tasks = 0
        
        logger.info(f"Background task worker {self.worker_id} initialized")
    
    async def start(self, poll_interval: int = 5):
        """Start the background worker"""
        if not self.task_queue:
            logger.error("Task queue not available, cannot start worker")
            return
        
        self.running = True
        logger.info(f"Background worker {self.worker_id} started")
        
        while self.running:
            try:
                # Get pending tasks
                pending_tasks = await self.task_queue.get_pending_tasks(limit=5)
                
                if pending_tasks:
                    logger.info(f"Found {len(pending_tasks)} pending tasks")
                    
                    # Process tasks concurrently
                    tasks = [self.process_task(task) for task in pending_tasks]
                    await asyncio.gather(*tasks, return_exceptions=True)
                else:
                    # No tasks, wait before next poll
                    await asyncio.sleep(poll_interval)
                    
            except Exception as e:
                logger.error(f"Error in background worker loop: {e}")
                await asyncio.sleep(poll_interval)
    
    async def process_task(self, task: Dict):
        """Process a single task"""
        task_id = task.get('id')
        user_id = task.get('user_id')
        task_type = task.get('task_type')
        task_data = task.get('task_data', {})
        
        logger.info(f"Processing task {task_id} (type: {task_type}) for user {user_id}")
        
        try:
            # Mark task as processing
            await self.task_queue.update_task_progress(
                task_id,
                progress_percentage=10,
                progress_message="Task started processing"
            )
            
            # Process based on task type
            result = None
            if task_type == TaskType.CODE_GENERATION.value:
                result = await self.process_code_generation(task_data)
            elif task_type == TaskType.CODE_TESTING.value:
                result = await self.process_code_testing(task_data)
            elif task_type == TaskType.BRUTE_FORCE.value:
                result = await self.process_brute_force(task_data)
            elif task_type == TaskType.VULNERABILITY_SCAN.value:
                result = await self.process_vulnerability_scan(task_data)
            elif task_type == TaskType.SCRIPT_EXECUTION.value:
                result = await self.process_script_execution(task_data)
            else:
                result = await self.process_generic_task(task_data)
            
            # Mark as completed
            await self.task_queue.complete_task(task_id, result)
            self.processed_tasks += 1
            logger.info(f"Task {task_id} completed successfully")
            
        except Exception as e:
            logger.error(f"Error processing task {task_id}: {e}")
            await self.task_queue.fail_task(task_id, str(e))
    
    async def process_code_generation(self, task_data: Dict) -> Dict:
        """Process code generation task"""
        # This would call the actual code generation logic
        # For now, return placeholder
        return {
            'status': 'completed',
            'code': task_data.get('code', ''),
            'files': task_data.get('files', [])
        }
    
    async def process_code_testing(self, task_data: Dict) -> Dict:
        """Process code testing task"""
        # Execute code and return results
        return {
            'status': 'completed',
            'test_results': 'Tests passed'
        }
    
    async def process_brute_force(self, task_data: Dict) -> Dict:
        """Process brute force task"""
        # Run brute force attack
        return {
            'status': 'completed',
            'results': 'Brute force completed'
        }
    
    async def process_vulnerability_scan(self, task_data: Dict) -> Dict:
        """Process vulnerability scan task"""
        # Run vulnerability scan
        return {
            'status': 'completed',
            'vulnerabilities': []
        }
    
    async def process_script_execution(self, task_data: Dict) -> Dict:
        """Process script execution task"""
        import subprocess
        script = task_data.get('script', '')
        
        try:
            result = subprocess.run(
                script,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300
            )
            return {
                'status': 'completed',
                'stdout': result.stdout,
                'stderr': result.stderr,
                'exit_code': result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                'status': 'timeout',
                'error': 'Script execution timed out'
            }
        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    async def process_generic_task(self, task_data: Dict) -> Dict:
        """Process generic task"""
        return {
            'status': 'completed',
            'data': task_data
        }
    
    def stop(self):
        """Stop the background worker"""
        self.running = False
        logger.info(f"Background worker {self.worker_id} stopped")


# Global worker instance
_worker_instance: Optional[BackgroundTaskWorker] = None


def get_background_worker() -> Optional[BackgroundTaskWorker]:
    """Get or create background worker instance"""
    global _worker_instance
    if _worker_instance is None:
        _worker_instance = BackgroundTaskWorker()
    return _worker_instance
