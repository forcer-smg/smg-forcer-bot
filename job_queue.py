# -*- coding: utf-8 -*-
"""
Job Queue System - Background job processing with streaming
Implements job-based task execution with automatic streaming until completion
"""

import asyncio
import time
import logging
import json
import uuid
from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime, timedelta
from database_hybrid import Database

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Job status enumeration"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"  # Paused due to rate limit
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobQueue:
    """Manages background jobs with streaming support"""
    
    def __init__(self, db: Database):
        """
        Initialize job queue
        
        Args:
            db: Database instance
        """
        self.db = db
        self._ensure_table()
        self.running_jobs: Dict[str, asyncio.Task] = {}
        logger.info("JobQueue initialized")
    
    def _ensure_table(self):
        """Ensure jobs table exists in database"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # Check if table exists (PostgreSQL)
            if hasattr(self.db, 'is_postgres') and self.db.is_postgres:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS jobs (
                        job_id VARCHAR(255) PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        chat_id BIGINT NOT NULL,
                        status VARCHAR(50) NOT NULL,
                        task_description TEXT,
                        job_data JSONB,
                        current_step INTEGER DEFAULT 0,
                        total_steps INTEGER DEFAULT 0,
                        progress_pct INTEGER DEFAULT 0,
                        last_message_id INTEGER,
                        last_update_time TIMESTAMP DEFAULT NOW(),
                        next_tick_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT NOW(),
                        completed_at TIMESTAMP,
                        error_message TEXT
                    )
                """)
            else:
                # SQLite
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS jobs (
                        job_id TEXT PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        chat_id INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        task_description TEXT,
                        job_data TEXT,
                        current_step INTEGER DEFAULT 0,
                        total_steps INTEGER DEFAULT 0,
                        progress_pct INTEGER DEFAULT 0,
                        last_message_id INTEGER,
                        last_update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        next_tick_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP,
                        error_message TEXT
                    )
                """)
            
            conn.commit()
            cursor.close()
            conn.close()
            logger.info("Jobs table ensured")
        except Exception as e:
            logger.error(f"Error ensuring jobs table: {e}", exc_info=True)
    
    def create_job(self, user_id: int, chat_id: int, task_description: str, 
                   job_data: Optional[Dict] = None) -> str:
        """
        Create a new job
        
        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID
            task_description: Description of the task
            job_data: Optional job-specific data
        
        Returns:
            Job ID
        """
        job_id = str(uuid.uuid4())
        
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            job_data_json = json.dumps(job_data) if job_data else None
            
            if hasattr(self.db, 'is_postgres') and self.db.is_postgres:
                cursor.execute("""
                    INSERT INTO jobs (job_id, user_id, chat_id, status, task_description, 
                                    job_data, next_tick_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """, (job_id, user_id, chat_id, JobStatus.PENDING.value, 
                      task_description, job_data_json))
            else:
                cursor.execute("""
                    INSERT INTO jobs (job_id, user_id, chat_id, status, task_description, 
                                    job_data, next_tick_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """, (job_id, user_id, chat_id, JobStatus.PENDING.value, 
                      task_description, job_data_json))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"Created job {job_id} for user {user_id}: {task_description}")
            return job_id
            
        except Exception as e:
            logger.error(f"Error creating job: {e}", exc_info=True)
            raise
    
    def get_pending_jobs(self) -> List[Dict[str, Any]]:
        """
        Get all jobs that are ready to run (status=running and next_tick_at <= now)
        
        Returns:
            List of job dictionaries
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            if hasattr(self.db, 'is_postgres') and self.db.is_postgres:
                cursor.execute("""
                    SELECT job_id, user_id, chat_id, status, task_description, job_data,
                           current_step, total_steps, progress_pct, last_message_id,
                           next_tick_at, created_at
                    FROM jobs
                    WHERE status IN (%s, %s)
                    AND (next_tick_at IS NULL OR next_tick_at <= NOW())
                    ORDER BY created_at ASC
                    LIMIT 50
                """, (JobStatus.PENDING.value, JobStatus.RUNNING.value))
            else:
                cursor.execute("""
                    SELECT job_id, user_id, chat_id, status, task_description, job_data,
                           current_step, total_steps, progress_pct, last_message_id,
                           next_tick_at, created_at
                    FROM jobs
                    WHERE status IN (?, ?)
                    AND (next_tick_at IS NULL OR next_tick_at <= datetime('now'))
                    ORDER BY created_at ASC
                    LIMIT 50
                """, (JobStatus.PENDING.value, JobStatus.RUNNING.value))
            
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            jobs = []
            for row in rows:
                job = {
                    'job_id': row[0],
                    'user_id': row[1],
                    'chat_id': row[2],
                    'status': row[3],
                    'task_description': row[4],
                    'job_data': json.loads(row[5]) if row[5] else {},
                    'current_step': row[6] or 0,
                    'total_steps': row[7] or 0,
                    'progress_pct': row[8] or 0,
                    'last_message_id': row[9],
                    'next_tick_at': row[10],
                    'created_at': row[11]
                }
                jobs.append(job)
            
            return jobs
            
        except Exception as e:
            logger.error(f"Error getting pending jobs: {e}", exc_info=True)
            return []
    
    def update_job(self, job_id: str, status: Optional[JobStatus] = None,
                   current_step: Optional[int] = None, total_steps: Optional[int] = None,
                   progress_pct: Optional[int] = None, last_message_id: Optional[int] = None,
                   next_tick_at: Optional[datetime] = None, job_data: Optional[Dict] = None,
                   error_message: Optional[str] = None):
        """
        Update job status and progress
        
        Args:
            job_id: Job ID
            status: New status (optional)
            current_step: Current step number (optional)
            total_steps: Total steps (optional)
            progress_pct: Progress percentage (optional)
            last_message_id: Last Telegram message ID (optional)
            next_tick_at: When to run next tick (optional)
            job_data: Updated job data (optional)
            error_message: Error message if failed (optional)
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            updates = []
            params = []
            
            if status:
                updates.append("status = %s" if hasattr(self.db, 'is_postgres') and self.db.is_postgres else "status = ?")
                params.append(status.value)
            
            if current_step is not None:
                updates.append("current_step = %s" if hasattr(self.db, 'is_postgres') and self.db.is_postgres else "current_step = ?")
                params.append(current_step)
            
            if total_steps is not None:
                updates.append("total_steps = %s" if hasattr(self.db, 'is_postgres') and self.db.is_postgres else "total_steps = ?")
                params.append(total_steps)
            
            if progress_pct is not None:
                updates.append("progress_pct = %s" if hasattr(self.db, 'is_postgres') and self.db.is_postgres else "progress_pct = ?")
                params.append(progress_pct)
            
            if last_message_id is not None:
                updates.append("last_message_id = %s" if hasattr(self.db, 'is_postgres') and self.db.is_postgres else "last_message_id = ?")
                params.append(last_message_id)
            
            if next_tick_at:
                if hasattr(self.db, 'is_postgres') and self.db.is_postgres:
                    updates.append("next_tick_at = %s")
                else:
                    updates.append("next_tick_at = ?")
                params.append(next_tick_at)
            
            if job_data:
                job_data_json = json.dumps(job_data)
                if hasattr(self.db, 'is_postgres') and self.db.is_postgres:
                    updates.append("job_data = %s")
                else:
                    updates.append("job_data = ?")
                params.append(job_data_json)
            
            if error_message:
                updates.append("error_message = %s" if hasattr(self.db, 'is_postgres') and self.db.is_postgres else "error_message = ?")
                params.append(error_message)
            
            if status == JobStatus.COMPLETED:
                if hasattr(self.db, 'is_postgres') and self.db.is_postgres:
                    updates.append("completed_at = NOW()")
                else:
                    updates.append("completed_at = datetime('now')")
            
            updates.append("last_update_time = %s" if hasattr(self.db, 'is_postgres') and self.db.is_postgres else "last_update_time = datetime('now')")
            
            if updates:
                query = f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = {'%s' if hasattr(self.db, 'is_postgres') and self.db.is_postgres else '?'}"
                params.append(job_id)
                
                cursor.execute(query, params)
                conn.commit()
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error updating job {job_id}: {e}", exc_info=True)
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job by ID"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            if hasattr(self.db, 'is_postgres') and self.db.is_postgres:
                cursor.execute("""
                    SELECT job_id, user_id, chat_id, status, task_description, job_data,
                           current_step, total_steps, progress_pct, last_message_id,
                           next_tick_at, created_at, error_message
                    FROM jobs
                    WHERE job_id = %s
                """, (job_id,))
            else:
                cursor.execute("""
                    SELECT job_id, user_id, chat_id, status, task_description, job_data,
                           current_step, total_steps, progress_pct, last_message_id,
                           next_tick_at, created_at, error_message
                    FROM jobs
                    WHERE job_id = ?
                """, (job_id,))
            
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if row:
                return {
                    'job_id': row[0],
                    'user_id': row[1],
                    'chat_id': row[2],
                    'status': row[3],
                    'task_description': row[4],
                    'job_data': json.loads(row[5]) if row[5] else {},
                    'current_step': row[6] or 0,
                    'total_steps': row[7] or 0,
                    'progress_pct': row[8] or 0,
                    'last_message_id': row[9],
                    'next_tick_at': row[10],
                    'created_at': row[11],
                    'error_message': row[12]
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting job {job_id}: {e}", exc_info=True)
            return None


# Global instance
_job_queue_instance = None

def get_job_queue(db: Optional[Database] = None) -> JobQueue:
    """Get or create global job queue instance"""
    global _job_queue_instance
    if _job_queue_instance is None:
        if db is None:
            from database_hybrid import Database
            db = Database()
        _job_queue_instance = JobQueue(db)
    return _job_queue_instance
