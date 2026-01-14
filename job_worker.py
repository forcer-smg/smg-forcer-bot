# -*- coding: utf-8 -*-
"""
Job Worker - Background worker that processes jobs and streams progress
Implements rate-limited streaming for both Telegram and DeepSeek API
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from job_queue import JobQueue, JobStatus, get_job_queue
from database_hybrid import Database
from HacxGPT import HacxBrain

logger = logging.getLogger(__name__)


class JobWorker:
    """Background worker that processes jobs with rate-limited streaming"""
    
    def __init__(self, db: Database, bot_application=None):
        """
        Initialize job worker
        
        Args:
            db: Database instance
            bot_application: Telegram bot application (for sending messages)
        """
        self.db = db
        self.job_queue = get_job_queue(db)
        self.bot_application = bot_application
        self.running = False
        self.worker_task = None
        
        # Rate limiters
        try:
            from telegram_rate_limiter import get_telegram_rate_limiter
            self.telegram_limiter = get_telegram_rate_limiter()
        except ImportError:
            self.telegram_limiter = None
        
        # DeepSeek rate limiter (per-minute token/request limits)
        self.deepseek_requests = []  # Track request timestamps
        self.deepseek_tokens_used = 0
        self.deepseek_reset_time = time.time() + 60  # Reset every minute
        
        logger.info("JobWorker initialized")
    
    async def start(self):
        """Start the background worker"""
        if self.running:
            logger.warning("Worker already running")
            return
        
        self.running = True
        self.worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Job worker started")
    
    async def stop(self):
        """Stop the background worker"""
        self.running = False
        if self.worker_task:
            await self.worker_task
        logger.info("Job worker stopped")
    
    def _can_call_deepseek(self) -> bool:
        """
        Check if we can call DeepSeek API (rate limit check)
        
        Returns:
            True if can call, False if should wait
        """
        now = time.time()
        
        # Reset token counter every minute
        if now >= self.deepseek_reset_time:
            self.deepseek_tokens_used = 0
            self.deepseek_reset_time = now + 60
        
        # Remove old request timestamps (older than 1 minute)
        cutoff = now - 60.0
        self.deepseek_requests = [ts for ts in self.deepseek_requests if ts > cutoff]
        
        # Check requests per minute (soft limit: 50/min, hard limit: 60/min)
        if len(self.deepseek_requests) >= 50:
            return False
        
        # Check token usage (soft limit: 80% of limit)
        # DeepSeek free tier: ~1000 tokens/min, we use 800 as soft limit
        if self.deepseek_tokens_used >= 800:
            return False
        
        return True
    
    def _record_deepseek_call(self, tokens_used: int = 0):
        """Record a DeepSeek API call"""
        now = time.time()
        self.deepseek_requests.append(now)
        self.deepseek_tokens_used += tokens_used
    
    async def _wait_for_deepseek(self) -> float:
        """
        Wait if DeepSeek rate limit would be hit
        
        Returns:
            Time waited in seconds
        """
        if self._can_call_deepseek():
            return 0.0
        
        # Calculate wait time
        now = time.time()
        
        # Wait for request limit
        if self.deepseek_requests:
            oldest = min(self.deepseek_requests)
            wait_time = 60.0 - (now - oldest)
            if wait_time > 0:
                logger.debug(f"Waiting for DeepSeek rate limit: {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                return wait_time
        
        # Wait for token reset
        if now < self.deepseek_reset_time:
            wait_time = self.deepseek_reset_time - now
            logger.debug(f"Waiting for DeepSeek token reset: {wait_time:.2f}s")
            await asyncio.sleep(wait_time)
            return wait_time
        
        return 0.0
    
    async def _send_progress_update(self, chat_id: int, message_id: Optional[int], 
                                   text: str, is_final: bool = False) -> Optional[int]:
        """
        Send or edit progress message with rate limiting
        
        Args:
            chat_id: Telegram chat ID
            message_id: Existing message ID to edit (None to send new)
            text: Message text
            is_final: True if this is the final message
        
        Returns:
            Message ID of sent/edited message
        """
        if not self.bot_application:
            logger.warning("No bot application available for sending messages")
            return None
        
        try:
            # Wait for Telegram rate limit
            if self.telegram_limiter:
                await self.telegram_limiter.wait_if_needed(chat_id)
            
            bot = self.bot_application.bot
            
            if message_id and not is_final:
                # Edit existing message
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=text[:4000],  # Telegram limit
                        parse_mode='Markdown'
                    )
                    # Record send
                    if self.telegram_limiter:
                        self.telegram_limiter.record_message_sent(chat_id)
                    return message_id
                except Exception as e:
                    # Edit failed, send new message instead
                    logger.debug(f"Edit failed, sending new message: {e}")
                    message_id = None
            
            # Send new message
            message = await bot.send_message(
                chat_id=chat_id,
                text=text[:4000],
                parse_mode='Markdown'
            )
            # Record send
            if self.telegram_limiter:
                self.telegram_limiter.record_message_sent(chat_id)
            
            return message.message_id
            
        except Exception as e:
            logger.error(f"Error sending progress update: {e}", exc_info=True)
            return message_id  # Return existing message_id if available
    
    async def _process_job_step(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process one step of a job
        
        Args:
            job: Job dictionary
        
        Returns:
            Updated job dictionary
        """
        job_id = job['job_id']
        user_id = job['user_id']
        chat_id = job['chat_id']
        task_description = job['task_description']
        job_data = job.get('job_data', {})
        current_step = job.get('current_step', 0)
        
        logger.info(f"Processing job {job_id}, step {current_step + 1}")
        
        # Wait for DeepSeek rate limit
        await self._wait_for_deepseek()
        
        # Get user's AI brain
        try:
            from telegram_bot import get_user_brain
            brain = get_user_brain(user_id)
        except Exception as e:
            logger.error(f"Error getting user brain: {e}")
            self.job_queue.update_job(job_id, status=JobStatus.FAILED, 
                                     error_message=f"Error getting AI brain: {e}")
            return job
        
        # Prepare context for AI
        context_text = task_description
        if job_data.get('previous_steps'):
            context_text += f"\n\nPrevious steps completed:\n" + "\n".join(job_data.get('previous_steps', []))
        
        if job_data.get('last_results'):
            context_text += f"\n\nLast results:\n{job_data.get('last_results')}"
        
        # Call AI with streaming
        try:
            # Generate response (non-streaming for now, can be enhanced)
            response_text = ""
            async for chunk in brain.generate_response(context_text):
                response_text += chunk
            
            # Record DeepSeek call (estimate tokens)
            estimated_tokens = len(response_text.split()) * 1.3  # Rough estimate
            self._record_deepseek_call(tokens_used=int(estimated_tokens))
            
            # Parse response for commands/actions
            try:
                from ai_response_parser import get_ai_response_parser
                parser = get_ai_response_parser()
                parsed = parser.parse_ai_response(response_text)
                
                # Execute commands if any
                if parsed.get('commands'):
                    try:
                        from command_executor import get_command_executor
                        executor = get_command_executor()
                        
                        for cmd_info in parsed['commands']:
                            cmd = cmd_info.get('command', '')
                            if cmd:
                                result = await executor.execute_command(cmd)
                                if result.get('success'):
                                    logger.info(f"Command executed: {cmd[:50]}...")
                                else:
                                    logger.warning(f"Command failed: {cmd[:50]}...")
                    except Exception as e:
                        logger.error(f"Error executing commands: {e}")
                
                # Update job data
                job_data['last_response'] = response_text
                job_data['last_parsed'] = parsed
                if 'previous_steps' not in job_data:
                    job_data['previous_steps'] = []
                job_data['previous_steps'].append(f"Step {current_step + 1}: {response_text[:200]}...")
                
            except Exception as e:
                logger.error(f"Error parsing AI response: {e}")
                job_data['last_response'] = response_text
            
            # Check if task is complete
            is_complete = parsed.get('is_complete', False) if 'parsed' in locals() else False
            if not is_complete:
                # Check for completion keywords
                completion_keywords = ['task complete', 'done', 'finished', 'completed', 
                                     'all done', 'task finished', 'summary']
                response_lower = response_text.lower()
                is_complete = any(keyword in response_lower for keyword in completion_keywords)
            
            # Update progress
            total_steps = job.get('total_steps', 0)
            if total_steps == 0:
                # Estimate total steps (can be improved)
                total_steps = max(3, len(response_text.split()) // 100)
                job['total_steps'] = total_steps
            
            current_step += 1
            progress_pct = min(100, int((current_step / total_steps) * 100)) if total_steps > 0 else 0
            
            # Send progress update
            progress_text = f"🔄 **Step {current_step}/{total_steps}** ({progress_pct}%)\n\n"
            progress_text += response_text[:3500]  # Leave room for formatting
            
            message_id = await self._send_progress_update(
                chat_id=chat_id,
                message_id=job.get('last_message_id'),
                text=progress_text,
                is_final=is_complete
            )
            
            # Calculate next tick (respect rate limits)
            # Wait 3-5 seconds between steps (Telegram rate limit: 1 msg/sec per chat)
            next_tick = datetime.now() + timedelta(seconds=3)
            
            if is_complete:
                # Send final summary
                summary_text = f"✅ **Task Completed**\n\n{task_description}\n\n**Final Result:**\n\n{response_text[:3500]}"
                await self._send_progress_update(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=summary_text,
                    is_final=True
                )
                
                # Mark job as completed
                self.job_queue.update_job(
                    job_id=job_id,
                    status=JobStatus.COMPLETED,
                    current_step=current_step,
                    total_steps=total_steps,
                    progress_pct=100,
                    last_message_id=message_id,
                    job_data=job_data
                )
            else:
                # Update job for next step
                self.job_queue.update_job(
                    job_id=job_id,
                    status=JobStatus.RUNNING,
                    current_step=current_step,
                    total_steps=total_steps,
                    progress_pct=progress_pct,
                    last_message_id=message_id,
                    next_tick_at=next_tick,
                    job_data=job_data
                )
            
            job['current_step'] = current_step
            job['total_steps'] = total_steps
            job['progress_pct'] = progress_pct
            job['last_message_id'] = message_id
            job['status'] = JobStatus.COMPLETED.value if is_complete else JobStatus.RUNNING.value
            
            return job
            
        except Exception as e:
            logger.error(f"Error processing job step: {e}", exc_info=True)
            self.job_queue.update_job(job_id, status=JobStatus.FAILED, 
                                     error_message=str(e))
            return job
    
    async def _worker_loop(self):
        """Main worker loop that processes jobs"""
        logger.info("Worker loop started")
        
        while self.running:
            try:
                # Get pending jobs
                pending_jobs = self.job_queue.get_pending_jobs()
                
                if not pending_jobs:
                    # No jobs, wait a bit
                    await asyncio.sleep(2)
                    continue
                
                # Process each job
                for job in pending_jobs:
                    if not self.running:
                        break
                    
                    job_id = job['job_id']
                    
                    # Skip if already processing
                    if job_id in self.running_jobs:
                        continue
                    
                    # Start processing job
                    task = asyncio.create_task(self._process_job_async(job))
                    self.running_jobs[job_id] = task
                
                # Clean up completed tasks
                completed = [jid for jid, task in self.running_jobs.items() if task.done()]
                for jid in completed:
                    del self.running_jobs[jid]
                
                # Small delay before next iteration
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
                await asyncio.sleep(5)
        
        logger.info("Worker loop stopped")
    
    async def _process_job_async(self, job: Dict[str, Any]):
        """Process a job asynchronously"""
        try:
            job_id = job['job_id']
            
            # Mark as running if pending
            if job['status'] == JobStatus.PENDING.value:
                self.job_queue.update_job(job_id, status=JobStatus.RUNNING)
            
            # Process one step
            updated_job = await self._process_job_step(job)
            
            # If still running, it will be picked up in next iteration
            # If completed/failed, it won't be picked up again
            
        except Exception as e:
            logger.error(f"Error processing job {job.get('job_id', 'unknown')}: {e}", exc_info=True)
            self.job_queue.update_job(job.get('job_id'), status=JobStatus.FAILED, 
                                     error_message=str(e))


# Global instance
_job_worker_instance = None

def get_job_worker(db: Optional[Database] = None, bot_application=None) -> JobWorker:
    """Get or create global job worker instance"""
    global _job_worker_instance
    if _job_worker_instance is None:
        if db is None:
            from database_hybrid import Database
            db = Database()
        _job_worker_instance = JobWorker(db, bot_application)
    return _job_worker_instance
