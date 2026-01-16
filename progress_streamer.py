# -*- coding: utf-8 -*-
"""
Progress Streamer - Stream status updates for long-running tasks
Provides periodic updates (10-30 seconds) during task execution
Handles Telegram API timeouts and rate limits gracefully
Supports long-running tasks (hours, not just minutes) with checkpointing
"""

import time
import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ProgressStreamer:
    """Stream progress updates for long-running tasks with Telegram API resilience"""
    
    def __init__(self, update=None, context=None, update_interval: int = 60):
        """
        Initialize progress streamer
        
        Args:
            update: Telegram Update object (optional)
            context: Telegram Context object (optional)
            update_interval: Seconds between updates (default: 60 - 1 minute to avoid rate limits)
        """
        self.update = update
        self.context = context
        self.update_interval = update_interval
        self.last_update = time.time()
        self.start_time = time.time()
        self.task_start_time = None
        self.current_step = "Initializing"
        self.progress_pct = 0
        self.results_count = 0
        self.details = []
        self.last_message = None
        self.enabled = True
        
        # Telegram API resilience
        try:
            from telegram_rate_limiter import get_telegram_rate_limiter
            self.rate_limiter = get_telegram_rate_limiter()
        except ImportError:
            self.rate_limiter = None
            logger.warning("Telegram rate limiter not available")
        
        # Checkpointing for long-running tasks
        self.checkpoints = []
        self.last_checkpoint_time = None
        self.checkpoint_interval = 300  # 5 minutes
        
    def set_task_info(self, task_name: str, estimated_duration: int = None):
        """Set task information"""
        self.task_name = task_name
        self.task_start_time = time.time()
        self.estimated_duration = estimated_duration  # in seconds
    
    def update_progress(self, step: str, progress_pct: int = None, results_count: int = None, details: str = None):
        """
        Update progress information
        
        Args:
            step: Current step description
            progress_pct: Progress percentage (0-100)
            results_count: Number of results found so far
            details: Additional details string
        """
        self.current_step = step
        if progress_pct is not None:
            self.progress_pct = progress_pct
        if results_count is not None:
            self.results_count = results_count
        if details:
            if isinstance(details, list):
                self.details = details
            else:
                self.details = [details] if details else []
    
    async def send_progress_update(self, force: bool = False) -> bool:
        """
        Send progress update if interval has passed
        Handles Telegram API timeouts and rate limits gracefully
        
        Args:
            force: Force update even if interval hasn't passed
        
        Returns:
            True if update was sent, False otherwise
        """
        if not self.enabled or not self.update:
            return False
        
        current_time = time.time()
        time_since_last = current_time - self.last_update
        
        # Check if enough time has passed or if forced
        if not force and time_since_last < self.update_interval:
            return False
        
        try:
            # Build progress message
            message = self._build_progress_message()
            
            # For progress updates, ALWAYS send new messages instead of editing
            # This avoids 400 errors from rapid edits and is more reliable
            # With 60-second intervals, we should never hit rate limits
            if not self.update or not self.update.message:
                return False
            
            # Use rate limiter if available
            if self.rate_limiter:
                try:
                    # Wait if needed to avoid rate limit (shouldn't be needed with 60s intervals)
                    chat_id = self.update.effective_chat.id if self.update.effective_chat else None
                    if chat_id:
                        await self.rate_limiter.wait_if_needed(chat_id)
                    
                    # Always send new message (don't edit) - prevents 400 errors
                    async def send_message():
                        return await self.update.message.reply_text(message, parse_mode='Markdown')
                    
                    self.last_message = await self.rate_limiter.send_with_retry(send_message, max_retries=2)
                    
                    # Record message sent
                    if self.rate_limiter and chat_id:
                        self.rate_limiter.record_message_sent(chat_id)
                    
                except Exception as e:
                    logger.warning(f"Error sending progress update (with rate limiter): {e}")
                    # Fallback: direct send with error handling
                    try:
                        self.last_message = await self.update.message.reply_text(message, parse_mode='Markdown')
                    except Exception as e2:
                        logger.warning(f"Fallback send also failed: {e2}")
                        return False
            else:
                # Fallback: direct send without rate limiter
                try:
                    self.last_message = await self.update.message.reply_text(message, parse_mode='Markdown')
                except Exception as e:
                    logger.warning(f"Error sending progress update: {e}")
                    return False
            
            self.last_update = current_time
            
            # Save checkpoint for long-running tasks
            self._save_checkpoint()
            
            return True
            
        except Exception as e:
            logger.warning(f"Error sending progress update: {e}")
            return False
    
    def _build_progress_message(self) -> str:
        """Build formatted progress message"""
        elapsed = time.time() - (self.task_start_time or self.start_time)
        elapsed_str = self._format_duration(elapsed)
        
        message = f"🔄 *Progress Update*\n\n"
        message += f"*Task:* {getattr(self, 'task_name', 'Processing')}\n"
        message += f"*Status:* {self.current_step}\n"
        message += f"*Progress:* {self.progress_pct}%\n"
        
        if self.results_count > 0:
            message += f"*Results Found:* {self.results_count}\n"
        
        message += f"*Elapsed:* {elapsed_str}\n"
        
        if hasattr(self, 'estimated_duration') and self.estimated_duration:
            remaining = max(0, self.estimated_duration - elapsed)
            remaining_str = self._format_duration(remaining)
            message += f"*Estimated Remaining:* {remaining_str}\n"
        
        if self.details:
            message += f"\n*Details:*\n"
            for detail in self.details[-3:]:  # Show last 3 details
                message += f"• {detail}\n"
        
        return message
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format"""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
    
    async def send_final_update(self, success: bool = True, summary: str = None):
        """Send final progress update"""
        elapsed = time.time() - (self.task_start_time or self.start_time)
        elapsed_str = self._format_duration(elapsed)
        
        status_emoji = "✅" if success else "❌"
        status_text = "Complete" if success else "Failed"
        
        message = f"{status_emoji} *Task {status_text}*\n\n"
        message += f"*Task:* {getattr(self, 'task_name', 'Processing')}\n"
        message += f"*Duration:* {elapsed_str}\n"
        
        if self.results_count > 0:
            message += f"*Total Results:* {self.results_count}\n"
        
        if summary:
            message += f"\n*Summary:*\n{summary}\n"
        
        try:
            if self.last_message:
                await self.last_message.edit_text(message, parse_mode='Markdown')
            else:
                await self.update.message.reply_text(message, parse_mode='Markdown')
        except Exception as e:
            logger.warning(f"Error sending final update: {e}")
            try:
                await self.update.message.reply_text(message, parse_mode='Markdown')
            except:
                pass
    
    def disable(self):
        """Disable progress streaming"""
        self.enabled = False
    
    def enable(self):
        """Enable progress streaming"""
        self.enabled = True
    
    def _save_checkpoint(self):
        """Save checkpoint for long-running task resumability"""
        current_time = time.time()
        
        # Only checkpoint every N minutes (to avoid too many checkpoints)
        if self.last_checkpoint_time and (current_time - self.last_checkpoint_time) < self.checkpoint_interval:
            return
        
        checkpoint = {
            'timestamp': current_time,
            'step': self.current_step,
            'progress_pct': self.progress_pct,
            'results_count': self.results_count,
            'elapsed_time': current_time - (self.task_start_time or self.start_time),
            'details': self.details[-5:]  # Last 5 details
        }
        
        self.checkpoints.append(checkpoint)
        self.last_checkpoint_time = current_time
        
        # Keep only last 20 checkpoints
        if len(self.checkpoints) > 20:
            self.checkpoints = self.checkpoints[-20:]
        
        logger.debug(f"Checkpoint saved: {self.current_step} ({self.progress_pct}%)")
    
    def get_latest_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Get latest checkpoint for resumability"""
        if self.checkpoints:
            return self.checkpoints[-1]
        return None
    
    def restore_from_checkpoint(self, checkpoint: Dict[str, Any]):
        """Restore progress from checkpoint"""
        self.current_step = checkpoint.get('step', 'Initializing')
        self.progress_pct = checkpoint.get('progress_pct', 0)
        self.results_count = checkpoint.get('results_count', 0)
        self.details = checkpoint.get('details', [])
        logger.info(f"Progress restored from checkpoint: {self.current_step} ({self.progress_pct}%)")


def create_progress_streamer(update=None, context=None, update_interval: int = 15) -> ProgressStreamer:
    """Create a progress streamer instance"""
    return ProgressStreamer(update=update, context=context, update_interval=update_interval)
