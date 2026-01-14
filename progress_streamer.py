# -*- coding: utf-8 -*-
"""
Progress Streamer - Stream status updates for long-running tasks
Provides periodic updates (10-30 seconds) during task execution
"""

import time
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ProgressStreamer:
    """Stream progress updates for long-running tasks"""
    
    def __init__(self, update=None, context=None, update_interval: int = 15):
        """
        Initialize progress streamer
        
        Args:
            update: Telegram Update object (optional)
            context: Telegram Context object (optional)
            update_interval: Seconds between updates (default: 15)
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
            
            # Send update
            if self.last_message:
                # Try to edit existing message
                try:
                    await self.last_message.edit_text(message, parse_mode='Markdown')
                except Exception as e:
                    # If edit fails, send new message
                    logger.debug(f"Could not edit progress message: {e}")
                    self.last_message = await self.update.message.reply_text(message, parse_mode='Markdown')
            else:
                # Send first message
                self.last_message = await self.update.message.reply_text(message, parse_mode='Markdown')
            
            self.last_update = current_time
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


def create_progress_streamer(update=None, context=None, update_interval: int = 15) -> ProgressStreamer:
    """Create a progress streamer instance"""
    return ProgressStreamer(update=update, context=context, update_interval=update_interval)
