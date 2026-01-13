# -*- coding: utf-8 -*-
"""
Background Processor - Handles async task processing and clean response formatting
Processes commands in background and sends only clean text/file responses
"""

import asyncio
import re
import logging
from typing import Dict, Optional, List, Callable, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import time

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ProcessingTask:
    """Represents a background processing task"""
    task_id: str
    user_id: int
    message: str
    status: TaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict] = None
    error: Optional[str] = None
    callback: Optional[Callable] = None


class ResponseFormatter:
    """Formats AI responses to be clean and user-friendly"""
    
    @staticmethod
    def clean_code_blocks(text: str) -> str:
        """Remove code blocks, replace with file references"""
        # Pattern: ```language\ncode\n```
        pattern = r'```(?:\w+)?\n(.*?)```'
        
        def replace_code(match):
            code = match.group(1)
            # If code is substantial, replace with file reference
            if len(code.split('\n')) > 5:
                return "📄 [Code file generated - see attached files]"
            return f"`{code[:50]}...`" if len(code) > 50 else f"`{code}`"
        
        return re.sub(pattern, replace_code, text, flags=re.DOTALL)
    
    @staticmethod
    def extract_output_only(text: str) -> str:
        """Extract only output/results, remove command execution details"""
        lines = text.split('\n')
        output_lines = []
        skip_next = False
        
        for i, line in enumerate(lines):
            # Skip command execution lines
            if any(marker in line.lower() for marker in ['executing', 'running', 'command:', '$', '>']):
                continue
            
            # Skip code blocks (already handled)
            if line.strip().startswith('```'):
                continue
            
            # Skip verbose debug info
            if any(marker in line.lower() for marker in ['debug:', 'trace:', 'verbose:']):
                continue
            
            # Keep actual output
            output_lines.append(line)
        
        return '\n'.join(output_lines).strip()
    
    @staticmethod
    def format_for_telegram(text: str, max_length: int = 4000) -> str:
        """Format text for Telegram, ensuring it's within limits"""
        # Clean the text
        cleaned = ResponseFormatter.clean_code_blocks(text)
        cleaned = ResponseFormatter.extract_output_only(cleaned)
        
        # Remove excessive whitespace
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        
        # Truncate if too long
        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length - 100] + "\n\n... [Response truncated]"
        
        return cleaned
    
    @staticmethod
    def separate_code_from_text(text: str) -> tuple[str, List[str]]:
        """
        Separate code blocks from text
        Returns: (clean_text, list_of_code_blocks)
        """
        code_blocks = []
        pattern = r'```(?:\w+)?\n(.*?)```'
        
        def extract_code(match):
            code = match.group(1)
            code_blocks.append(code)
            return f"[CODE_BLOCK_{len(code_blocks)}]"
        
        clean_text = re.sub(pattern, extract_code, text, flags=re.DOTALL)
        
        return clean_text, code_blocks


class BackgroundProcessor:
    """Manages background task processing queue"""
    
    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.task_queue = asyncio.Queue()
        self.active_tasks: Dict[str, ProcessingTask] = {}
        self.completed_tasks: Dict[str, ProcessingTask] = {}
        self.worker_running = False
        self.workers: List[asyncio.Task] = []
        self.formatter = ResponseFormatter()
    
    async def start_workers(self, num_workers: Optional[int] = None):
        """Start background worker tasks"""
        if self.worker_running:
            return
        
        num_workers = num_workers or self.max_concurrent
        self.worker_running = True
        
        for i in range(num_workers):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            self.workers.append(worker)
        
        logger.info(f"Started {num_workers} background workers")
    
    async def stop_workers(self):
        """Stop background workers"""
        self.worker_running = False
        
        # Wait for queue to empty
        await self.task_queue.join()
        
        # Cancel workers
        for worker in self.workers:
            worker.cancel()
        
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
        logger.info("Background workers stopped")
    
    async def add_task(self, task: ProcessingTask) -> str:
        """Add task to processing queue"""
        # Start workers if not already running
        if not self.worker_running:
            await self.start_workers()
        
        await self.task_queue.put(task)
        self.active_tasks[task.task_id] = task
        logger.info(f"Added task {task.task_id} to queue")
        return task.task_id
    
    async def _worker(self, worker_name: str):
        """Background worker that processes tasks"""
        logger.info(f"Worker {worker_name} started")
        
        while self.worker_running:
            try:
                # Get task from queue
                task = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)
                
                logger.info(f"Worker {worker_name} processing task {task.task_id}")
                task.status = TaskStatus.PROCESSING
                task.started_at = datetime.now()
                
                try:
                    # Execute task callback
                    if task.callback:
                        result = await task.callback(task)
                        task.result = result
                        task.status = TaskStatus.COMPLETED
                    else:
                        task.status = TaskStatus.FAILED
                        task.error = "No callback provided"
                
                except Exception as e:
                    logger.error(f"Task {task.task_id} failed: {e}")
                    task.status = TaskStatus.FAILED
                    task.error = str(e)
                
                finally:
                    task.completed_at = datetime.now()
                    self.completed_tasks[task.task_id] = task
                    if task.task_id in self.active_tasks:
                        del self.active_tasks[task.task_id]
                    
                    self.task_queue.task_done()
            
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Worker {worker_name} error: {e}")
                await asyncio.sleep(1)
    
    def get_task_status(self, task_id: str) -> Optional[ProcessingTask]:
        """Get task status by ID"""
        if task_id in self.active_tasks:
            return self.active_tasks[task_id]
        if task_id in self.completed_tasks:
            return self.completed_tasks[task_id]
        return None
    
    async def process_ai_response(self, response_text: str, 
                                  extract_files: bool = True) -> Dict:
        """
        Process AI response: clean it and extract files
        Returns dict with: clean_text, code_blocks, files
        """
        # Separate code from text
        clean_text, code_blocks = self.formatter.separate_code_from_text(response_text)
        
        # Format clean text
        formatted_text = self.formatter.format_for_telegram(clean_text)
        
        result = {
            'clean_text': formatted_text,
            'code_blocks': code_blocks,
            'has_code': len(code_blocks) > 0,
            'original_length': len(response_text),
            'formatted_length': len(formatted_text)
        }
        
        return result
    
    def create_task(self, user_id: int, message: str, 
                   callback: Callable) -> ProcessingTask:
        """Create a new processing task"""
        task_id = f"task_{user_id}_{int(time.time() * 1000)}"
        
        task = ProcessingTask(
            task_id=task_id,
            user_id=user_id,
            message=message,
            status=TaskStatus.PENDING,
            created_at=datetime.now(),
            callback=callback
        )
        
        return task


# Global processor instance
_processor_instance = None

def get_background_processor(max_concurrent: int = 3) -> BackgroundProcessor:
    """Get or create global background processor instance"""
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = BackgroundProcessor(max_concurrent=max_concurrent)
        # Start workers lazily when event loop is available
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Event loop is running, schedule workers to start
                asyncio.create_task(_processor_instance.start_workers())
            else:
                # No event loop yet, workers will start when first task is added
                pass
        except RuntimeError:
            # No event loop exists yet, workers will start when first task is added
            pass
    return _processor_instance
