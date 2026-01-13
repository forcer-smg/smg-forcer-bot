# -*- coding: utf-8 -*-
"""
Supabase Task Queue System - Offload long-running tasks to Supabase
Handles code generation, testing, and other time-consuming operations
Designed for 400+ concurrent users with proper isolation
"""

import os
import logging
import json
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)

# Try to import Supabase client
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logger.warning("Supabase client not available. Install with: pip install supabase")

# Try to import PostgreSQL adapter as fallback
try:
    from database_postgres import Database
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False


class TaskStatus(Enum):
    """Task status enumeration"""
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class TaskType(Enum):
    """Task type enumeration"""
    CODE_GENERATION = "code_generation"
    CODE_TESTING = "code_testing"
    BRUTE_FORCE = "brute_force"
    VULNERABILITY_SCAN = "vulnerability_scan"
    FILE_PROCESSING = "file_processing"
    SCRIPT_EXECUTION = "script_execution"
    LONG_RUNNING = "long_running"


class SupabaseTaskQueue:
    """Task queue system using Supabase for long-running tasks"""
    
    def __init__(self, supabase_url: Optional[str] = None, supabase_key: Optional[str] = None):
        """
        Initialize Supabase Task Queue
        
        Args:
            supabase_url: Supabase project URL
            supabase_key: Supabase anon/service key
        """
        self.supabase_url = supabase_url or os.getenv('SUPABASE_URL')
        self.supabase_key = supabase_key or os.getenv('SUPABASE_KEY') or os.getenv('SUPABASE_ANON_KEY')
        
        # Initialize Supabase client if available
        self.supabase_client: Optional[Client] = None
        if SUPABASE_AVAILABLE and self.supabase_url and self.supabase_key:
            try:
                self.supabase_client = create_client(self.supabase_url, self.supabase_key)
                logger.info("Supabase client initialized for task queue")
            except Exception as e:
                logger.warning(f"Failed to initialize Supabase client: {e}")
                self.supabase_client = None
        
        # Fallback to PostgreSQL if Supabase not available
        self.postgres_db = None
        if not self.supabase_client and POSTGRES_AVAILABLE:
            try:
                self.postgres_db = Database()
                logger.info("Using PostgreSQL as fallback for task queue")
            except Exception as e:
                logger.warning(f"Failed to initialize PostgreSQL fallback: {e}")
        
        # Initialize tables
        self._init_tables()
    
    def _init_tables(self):
        """Initialize task queue tables in Supabase/PostgreSQL"""
        if self.supabase_client:
            # Supabase will create tables via SQL migrations
            # For now, we'll use RPC calls or direct SQL
            try:
                # Try to create table if it doesn't exist
                self.supabase_client.table('task_queue').select('id').limit(1).execute()
                logger.info("Task queue table exists")
            except Exception as e:
                logger.warning(f"Task queue table may not exist: {e}")
                # Table will be created via migration
        elif self.postgres_db:
            # Create table in PostgreSQL
            try:
                conn = self.postgres_db.get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS task_queue (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id BIGINT NOT NULL,
                        task_type TEXT NOT NULL,
                        task_data JSONB NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        priority INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        started_at TIMESTAMP,
                        completed_at TIMESTAMP,
                        result_data JSONB,
                        error_message TEXT,
                        retry_count INTEGER DEFAULT 0,
                        max_retries INTEGER DEFAULT 3,
                        timeout_seconds INTEGER DEFAULT 300,
                        worker_id TEXT,
                        progress_percentage INTEGER DEFAULT 0,
                        progress_message TEXT
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_task_queue_user_status 
                    ON task_queue(user_id, status)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_task_queue_status_priority 
                    ON task_queue(status, priority DESC, created_at ASC)
                """)
                conn.commit()
                cursor.close()
                conn.close()
                logger.info("Task queue table created in PostgreSQL")
            except Exception as e:
                logger.error(f"Error creating task queue table: {e}")
    
    async def enqueue_task(
        self,
        user_id: int,
        task_type: TaskType,
        task_data: Dict,
        priority: int = 0,
        timeout_seconds: int = 300,
        max_retries: int = 3
    ) -> str:
        """
        Enqueue a task for background processing
        
        Args:
            user_id: Telegram user ID
            task_type: Type of task
            task_data: Task-specific data (code, commands, etc.)
            priority: Task priority (higher = more important)
            timeout_seconds: Task timeout in seconds
            max_retries: Maximum retry attempts
        
        Returns:
            Task ID (UUID string)
        """
        task_id = str(uuid.uuid4())
        
        task_record = {
            'id': task_id,
            'user_id': user_id,
            'task_type': task_type.value,
            'task_data': json.dumps(task_data) if isinstance(task_data, dict) else task_data,
            'status': TaskStatus.PENDING.value,
            'priority': priority,
            'timeout_seconds': timeout_seconds,
            'max_retries': max_retries,
            'progress_percentage': 0,
            'progress_message': 'Task queued',
            'created_at': datetime.now().isoformat()
        }
        
        try:
            if self.supabase_client:
                # Insert into Supabase
                result = self.supabase_client.table('task_queue').insert(task_record).execute()
                logger.info(f"Task {task_id} enqueued in Supabase for user {user_id}")
            elif self.postgres_db:
                # Insert into PostgreSQL
                conn = self.postgres_db.get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO task_queue (
                        id, user_id, task_type, task_data, status, priority,
                        timeout_seconds, max_retries, progress_percentage, progress_message
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    task_id, user_id, task_type.value,
                    json.dumps(task_data) if isinstance(task_data, dict) else task_data,
                    TaskStatus.PENDING.value, priority, timeout_seconds, max_retries,
                    0, 'Task queued'
                ))
                conn.commit()
                cursor.close()
                conn.close()
                logger.info(f"Task {task_id} enqueued in PostgreSQL for user {user_id}")
            else:
                logger.error("No database available for task queue")
                return None
            
            return task_id
        except Exception as e:
            logger.error(f"Error enqueuing task: {e}")
            return None
    
    async def get_task_status(self, task_id: str) -> Optional[Dict]:
        """Get current status of a task"""
        try:
            if self.supabase_client:
                result = self.supabase_client.table('task_queue').select('*').eq('id', task_id).execute()
                if result.data:
                    return self._format_task_record(result.data[0])
            elif self.postgres_db:
                conn = self.postgres_db.get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM task_queue WHERE id = %s
                """, (task_id,))
                row = cursor.fetchone()
                cursor.close()
                conn.close()
                if row:
                    return self._format_task_record(row)
            return None
        except Exception as e:
            logger.error(f"Error getting task status: {e}")
            return None
    
    async def update_task_progress(
        self,
        task_id: str,
        progress_percentage: int,
        progress_message: str,
        result_data: Optional[Dict] = None
    ) -> bool:
        """Update task progress"""
        try:
            update_data = {
                'progress_percentage': progress_percentage,
                'progress_message': progress_message
            }
            
            if result_data:
                update_data['result_data'] = json.dumps(result_data) if isinstance(result_data, dict) else result_data
            
            if self.supabase_client:
                self.supabase_client.table('task_queue').update(update_data).eq('id', task_id).execute()
            elif self.postgres_db:
                conn = self.postgres_db.get_connection()
                cursor = conn.cursor()
                if result_data:
                    cursor.execute("""
                        UPDATE task_queue 
                        SET progress_percentage = %s, progress_message = %s, result_data = %s
                        WHERE id = %s
                    """, (progress_percentage, progress_message, json.dumps(result_data), task_id))
                else:
                    cursor.execute("""
                        UPDATE task_queue 
                        SET progress_percentage = %s, progress_message = %s
                        WHERE id = %s
                    """, (progress_percentage, progress_message, task_id))
                conn.commit()
                cursor.close()
                conn.close()
            return True
        except Exception as e:
            logger.error(f"Error updating task progress: {e}")
            return False
    
    async def complete_task(
        self,
        task_id: str,
        result_data: Dict,
        status: TaskStatus = TaskStatus.COMPLETED
    ) -> bool:
        """Mark task as completed"""
        try:
            update_data = {
                'status': status.value,
                'completed_at': datetime.now().isoformat(),
                'result_data': json.dumps(result_data) if isinstance(result_data, dict) else result_data,
                'progress_percentage': 100,
                'progress_message': 'Task completed'
            }
            
            if self.supabase_client:
                self.supabase_client.table('task_queue').update(update_data).eq('id', task_id).execute()
            elif self.postgres_db:
                conn = self.postgres_db.get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE task_queue 
                    SET status = %s, completed_at = CURRENT_TIMESTAMP, 
                        result_data = %s, progress_percentage = %s, progress_message = %s
                    WHERE id = %s
                """, (status.value, json.dumps(result_data), 100, 'Task completed', task_id))
                conn.commit()
                cursor.close()
                conn.close()
            return True
        except Exception as e:
            logger.error(f"Error completing task: {e}")
            return False
    
    async def fail_task(self, task_id: str, error_message: str) -> bool:
        """Mark task as failed"""
        try:
            update_data = {
                'status': TaskStatus.FAILED.value,
                'completed_at': datetime.now().isoformat(),
                'error_message': error_message,
                'progress_message': f'Task failed: {error_message[:100]}'
            }
            
            if self.supabase_client:
                self.supabase_client.table('task_queue').update(update_data).eq('id', task_id).execute()
            elif self.postgres_db:
                conn = self.postgres_db.get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE task_queue 
                    SET status = %s, completed_at = CURRENT_TIMESTAMP, 
                        error_message = %s, progress_message = %s
                    WHERE id = %s
                """, (TaskStatus.FAILED.value, error_message, f'Task failed: {error_message[:100]}', task_id))
                conn.commit()
                cursor.close()
                conn.close()
            return True
        except Exception as e:
            logger.error(f"Error failing task: {e}")
            return False
    
    async def get_pending_tasks(self, limit: int = 10) -> List[Dict]:
        """Get pending tasks for processing (for workers)"""
        try:
            if self.supabase_client:
                result = self.supabase_client.table('task_queue').select('*').eq('status', TaskStatus.PENDING.value).order('priority', desc=True).order('created_at').limit(limit).execute()
                return [self._format_task_record(record) for record in result.data]
            elif self.postgres_db:
                conn = self.postgres_db.get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM task_queue 
                    WHERE status = %s 
                    ORDER BY priority DESC, created_at ASC 
                    LIMIT %s
                """, (TaskStatus.PENDING.value, limit))
                rows = cursor.fetchall()
                cursor.close()
                conn.close()
                return [self._format_task_record(row) for row in rows]
            return []
        except Exception as e:
            logger.error(f"Error getting pending tasks: {e}")
            return []
    
    def _format_task_record(self, record: Any) -> Dict:
        """Format task record from database"""
        if isinstance(record, dict):
            return record
        # If it's a PostgreSQL row, convert to dict
        return {
            'id': record[0] if isinstance(record, (list, tuple)) else record.get('id'),
            'user_id': record[1] if isinstance(record, (list, tuple)) else record.get('user_id'),
            'task_type': record[2] if isinstance(record, (list, tuple)) else record.get('task_type'),
            'task_data': json.loads(record[3]) if isinstance(record, (list, tuple)) else (json.loads(record.get('task_data')) if isinstance(record.get('task_data'), str) else record.get('task_data')),
            'status': record[4] if isinstance(record, (list, tuple)) else record.get('status'),
            'priority': record[5] if isinstance(record, (list, tuple)) else record.get('priority'),
            'progress_percentage': record[14] if isinstance(record, (list, tuple)) else record.get('progress_percentage', 0),
            'progress_message': record[15] if isinstance(record, (list, tuple)) else record.get('progress_message', ''),
            'result_data': json.loads(record[10]) if isinstance(record, (list, tuple)) and record[10] else (json.loads(record.get('result_data')) if isinstance(record.get('result_data'), str) else record.get('result_data')),
            'error_message': record[11] if isinstance(record, (list, tuple)) else record.get('error_message')
        }


def get_task_queue() -> Optional[SupabaseTaskQueue]:
    """Get or create task queue instance"""
    try:
        return SupabaseTaskQueue()
    except Exception as e:
        logger.error(f"Failed to initialize task queue: {e}")
        return None
