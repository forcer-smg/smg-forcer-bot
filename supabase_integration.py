# -*- coding: utf-8 -*-
"""
Supabase Integration - Integrate Supabase task queue and conversation context
with existing Telegram bot for smooth 400+ concurrent user handling
"""

import os
import logging
import asyncio
from typing import Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# Import Supabase modules
try:
    from supabase_task_queue import SupabaseTaskQueue, TaskType, get_task_queue
    from supabase_conversation_context import SupabaseConversationContext, get_conversation_context
    from background_task_worker import BackgroundTaskWorker, get_background_worker
    SUPABASE_INTEGRATION_AVAILABLE = True
except ImportError:
    SUPABASE_INTEGRATION_AVAILABLE = False
    logger.warning("Supabase integration modules not available")


class SupabaseIntegration:
    """Integration layer for Supabase task queue and conversation context"""
    
    def __init__(self):
        """Initialize Supabase integration"""
        self.task_queue: Optional[SupabaseTaskQueue] = None
        self.conversation_context: Optional[SupabaseConversationContext] = None
        self.background_worker: Optional[BackgroundTaskWorker] = None
        self.worker_started = False
        
        if SUPABASE_INTEGRATION_AVAILABLE:
            try:
                self.task_queue = get_task_queue()
                self.conversation_context = get_conversation_context()
                self.background_worker = get_background_worker()
                logger.info("Supabase integration initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Supabase integration: {e}")
    
    async def start_background_worker(self):
        """Start background task worker"""
        if self.background_worker and not self.worker_started:
            try:
                # Start worker in background
                asyncio.create_task(self.background_worker.start())
                self.worker_started = True
                logger.info("Background task worker started")
            except Exception as e:
                logger.error(f"Error starting background worker: {e}")
    
    async def handle_long_running_task(
        self,
        user_id: int,
        task_type: TaskType,
        task_data: Dict,
        update,
        context
    ) -> str:
        """
        Handle long-running task by queuing it in Supabase
        
        Returns:
            Task ID for status tracking
        """
        if not self.task_queue:
            # Fallback to direct execution if task queue not available
            logger.warning("Task queue not available, executing directly")
            return None
        
        try:
            # Determine priority based on task type
            priority = 5  # Default
            if task_type == TaskType.VULNERABILITY_SCAN:
                priority = 8
            elif task_type == TaskType.BRUTE_FORCE:
                priority = 7
            elif task_type == TaskType.CODE_GENERATION:
                priority = 6
            
            # Enqueue task
            task_id = await self.task_queue.enqueue_task(
                user_id=user_id,
                task_type=task_type,
                task_data=task_data,
                priority=priority,
                timeout_seconds=600,  # 10 minutes default
                max_retries=3
            )
            
            if task_id:
                # Notify user that task is queued
                await update.message.reply_text(
                    f"⏳ **Task Queued**\n\n"
                    f"Your {task_type.value.replace('_', ' ')} task has been queued for background processing.\n\n"
                    f"Task ID: `{task_id[:8]}...`\n\n"
                    f"I'll notify you when it's complete. You can continue using the bot while it processes.",
                    parse_mode='Markdown'
                )
                
                # Start background worker if not started
                await self.start_background_worker()
                
                # Start status polling
                asyncio.create_task(self.poll_task_status(task_id, user_id, update, context))
                
                return task_id
            else:
                logger.error("Failed to enqueue task")
                return None
                
        except Exception as e:
            logger.error(f"Error handling long-running task: {e}")
            return None
    
    async def poll_task_status(
        self,
        task_id: str,
        user_id: int,
        update,
        context,
        poll_interval: int = 3,
        max_polls: int = 200  # 10 minutes max (200 * 3s)
    ):
        """Poll task status and send updates to user"""
        if not self.task_queue:
            return
        
        last_progress = 0
        last_message = None
        polls = 0
        
        try:
            while polls < max_polls:
                await asyncio.sleep(poll_interval)
                polls += 1
                
                # Get task status
                task_status = await self.task_queue.get_task_status(task_id)
                
                if not task_status:
                    logger.warning(f"Task {task_id} not found")
                    break
                
                status = task_status.get('status')
                progress = task_status.get('progress_percentage', 0)
                progress_msg = task_status.get('progress_message', '')
                
                # Send update if progress changed
                if progress != last_progress or progress_msg != last_message:
                    try:
                        status_text = (
                            f"📊 **Task Progress**\n\n"
                            f"Status: `{status}`\n"
                            f"Progress: {progress}%\n"
                            f"{progress_msg}\n\n"
                            f"Task ID: `{task_id[:8]}...`"
                        )
                        
                        # Edit previous message or send new one
                        if last_message is None:
                            status_msg = await update.message.reply_text(
                                status_text,
                                parse_mode='Markdown'
                            )
                            last_message = status_text
                        else:
                            # Try to edit previous message
                            try:
                                await status_msg.edit_text(
                                    status_text,
                                    parse_mode='Markdown'
                                )
                            except:
                                # If edit fails, send new message
                                status_msg = await update.message.reply_text(
                                    status_text,
                                    parse_mode='Markdown'
                                )
                        
                        last_progress = progress
                        last_message = progress_msg
                    except Exception as e:
                        logger.warning(f"Error sending status update: {e}")
                
                # Check if task is complete
                if status in ['completed', 'failed', 'cancelled', 'timeout']:
                    # Send final result
                    await self.send_task_result(task_id, task_status, update)
                    break
                    
        except Exception as e:
            logger.error(f"Error polling task status: {e}")
    
    async def send_task_result(self, task_id: str, task_status: Dict, update):
        """Send final task result to user"""
        status = task_status.get('status')
        result_data = task_status.get('result_data', {})
        error_message = task_status.get('error_message')
        
        if status == 'completed':
            result_text = (
                f"✅ **Task Completed**\n\n"
                f"Task ID: `{task_id[:8]}...`\n\n"
            )
            
            # Add result details
            if isinstance(result_data, dict):
                if 'files' in result_data:
                    result_text += f"Generated {len(result_data['files'])} file(s)\n"
                if 'code' in result_data:
                    result_text += f"Code generated successfully\n"
                if 'vulnerabilities' in result_data:
                    result_text += f"Found {len(result_data.get('vulnerabilities', []))} vulnerability(ies)\n"
            
            await update.message.reply_text(result_text, parse_mode='Markdown')
            
            # Send files if any
            if isinstance(result_data, dict) and 'files' in result_data:
                for file_path in result_data['files']:
                    try:
                        if os.path.exists(file_path):
                            await update.message.reply_document(
                                document=open(file_path, 'rb')
                            )
                    except Exception as e:
                        logger.warning(f"Error sending file {file_path}: {e}")
                        
        elif status == 'failed':
            await update.message.reply_text(
                f"❌ **Task Failed**\n\n"
                f"Error: {error_message or 'Unknown error'}\n\n"
                f"Task ID: `{task_id[:8]}...`",
                parse_mode='Markdown'
            )
    
    async def store_conversation_message(
        self,
        user_id: int,
        chat_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None
    ):
        """Store conversation message in Supabase (Cursor-style)"""
        if not self.conversation_context:
            return
        
        try:
            await self.conversation_context.store_message(
                user_id=user_id,
                chat_id=chat_id,
                role=role,
                content=content,
                metadata=metadata
            )
        except Exception as e:
            logger.warning(f"Error storing conversation message: {e}")
    
    async def get_conversation_context_for_user(
        self,
        user_id: int,
        chat_id: str,
        current_message: str,
        max_tokens: Optional[int] = None
    ) -> str:
        """Get conversation context for user (Cursor-style)"""
        if not self.conversation_context:
            return current_message
        
        try:
            return await self.conversation_context.get_conversation_context(
                user_id=user_id,
                chat_id=chat_id,
                current_message=current_message,
                max_tokens=max_tokens
            )
        except Exception as e:
            logger.warning(f"Error getting conversation context: {e}")
            return current_message


# Global integration instance
_supabase_integration: Optional[SupabaseIntegration] = None


def get_supabase_integration() -> Optional[SupabaseIntegration]:
    """Get or create Supabase integration instance"""
    global _supabase_integration
    if _supabase_integration is None:
        _supabase_integration = SupabaseIntegration()
    return _supabase_integration
