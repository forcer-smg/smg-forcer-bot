# -*- coding: utf-8 -*-
"""
Task Focus Manager - Tracks what the bot is working on and filters what gets sent to Telegram
Only sends relevant, meaningful updates instead of every character/command
"""

import logging
import time
from typing import Dict, Optional, List
from enum import Enum

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task execution status"""
    STARTING = "starting"
    RECONNAISSANCE = "reconnaissance"
    SCANNING = "scanning"
    TESTING = "testing"
    EXECUTING = "executing"
    ANALYZING = "analyzing"
    COMPLETING = "completing"
    COMPLETE = "complete"
    ERROR = "error"


class TaskFocusManager:
    """Manages task focus and filters what gets sent to Telegram"""
    
    def __init__(self, user_id: int, task_description: str):
        """Initialize task focus manager"""
        self.user_id = user_id
        self.task_description = task_description
        self.current_status = TaskStatus.STARTING
        self.current_step = "Initializing"
        self.steps_completed = []
        self.results = []
        self.last_update_time = time.time()
        self.last_sent_message = ""
        self.commands_executed = 0
        self.files_generated = []
        self.vulnerabilities_found = []
        self.errors = []
        
        # Filtering settings
        self.min_update_interval = 30  # Minimum seconds between updates
        self.min_content_change = 200  # Minimum characters changed before sending update
        self.suppress_command_streaming = True  # Don't stream individual commands
        
    def update_status(self, status: TaskStatus, step: str = None, details: str = None):
        """Update current task status"""
        self.current_status = status
        if step:
            self.current_step = step
        if details:
            logger.info(f"[TASK-FOCUS] User {self.user_id} - Status: {status.value}, Step: {step}, Details: {details[:100]}")
        else:
            logger.info(f"[TASK-FOCUS] User {self.user_id} - Status: {status.value}, Step: {step}")
    
    def add_result(self, result_type: str, result_data: str):
        """Add a result (vulnerability, file, etc.)"""
        self.results.append({
            'type': result_type,
            'data': result_data,
            'timestamp': time.time()
        })
        logger.info(f"[TASK-FOCUS] Result added: {result_type} - {result_data[:100]}")
    
    def should_send_update(self, new_content: str) -> bool:
        """
        Determine if we should send an update to Telegram
        
        Args:
            new_content: The new content to potentially send
        
        Returns:
            True if we should send, False if we should suppress
        """
        current_time = time.time()
        time_since_last = current_time - self.last_update_time
        
        # Always send if enough time has passed (min_update_interval)
        if time_since_last >= self.min_update_interval:
            logger.debug(f"[TASK-FOCUS] Sending update - enough time passed ({time_since_last:.1f}s)")
            return True
        
        # Check if content changed significantly
        if self.last_sent_message:
            content_diff = abs(len(new_content) - len(self.last_sent_message))
            if content_diff >= self.min_content_change:
                logger.debug(f"[TASK-FOCUS] Sending update - significant content change ({content_diff} chars)")
                return True
        
        # Suppress if too soon and no significant change
        logger.debug(f"[TASK-FOCUS] Suppressing update - too soon ({time_since_last:.1f}s) and no significant change")
        return False
    
    def filter_content_for_telegram(self, content: str) -> Optional[str]:
        """
        Filter content to only include relevant information for Telegram
        
        Args:
            content: Raw content from AI/commands
        
        Returns:
            Filtered content or None if should be suppressed
        """
        # Suppress command-by-command streaming
        if self.suppress_command_streaming:
            # Check if this is just a command being typed
            if content.strip().startswith('cd ') or content.strip().startswith('```bash'):
                # Check if it's a partial command (being typed)
                if len(content.strip()) < 100 and '&&' not in content:
                    logger.debug(f"[TASK-FOCUS] Suppressing partial command: {content[:50]}...")
                    return None
        
        # Filter out repetitive content
        if content == self.last_sent_message:
            logger.debug(f"[TASK-FOCUS] Suppressing duplicate content")
            return None
        
        # Extract only meaningful information
        filtered = self._extract_meaningful_info(content)
        
        if filtered and filtered != self.last_sent_message:
            self.last_sent_message = filtered
            self.last_update_time = time.time()
            return filtered
        
        return None
    
    def _extract_meaningful_info(self, content: str) -> str:
        """Extract only meaningful information from content"""
        # Focus on:
        # - Task status updates
        # - Results (vulnerabilities, files, etc.)
        # - Errors
        # - Completion status
        # - NOT individual commands being typed
        
        lines = content.split('\n')
        meaningful_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Skip partial commands
            if line.startswith('cd ') and len(line) < 50:
                continue
            
            # Keep status updates
            if any(keyword in line.lower() for keyword in ['step', 'status', 'progress', 'complete', 'found', 'vulnerability', 'result', 'error', 'success']):
                meaningful_lines.append(line)
            # Keep code blocks (complete ones)
            elif line.startswith('```') or (line.startswith('```') and '```' in content):
                meaningful_lines.append(line)
            # Keep results
            elif any(keyword in line.lower() for keyword in ['file', 'generated', 'discovered', 'detected', 'exploited']):
                meaningful_lines.append(line)
        
        if meaningful_lines:
            return '\n'.join(meaningful_lines[:20])  # Limit to 20 most relevant lines
        
        # If no meaningful lines, return summary
        return f"**{self.current_step}** - {self.current_status.value}"
    
    def get_summary(self) -> str:
        """Get current task summary for Telegram"""
        summary = f"**Task:** {self.task_description[:100]}\n\n"
        summary += f"**Status:** {self.current_status.value.title()}\n"
        summary += f"**Current Step:** {self.current_step}\n"
        
        if self.results:
            summary += f"\n**Results Found:** {len(self.results)}\n"
            for result in self.results[-5:]:  # Last 5 results
                summary += f"• {result['type']}: {result['data'][:50]}...\n"
        
        if self.commands_executed > 0:
            summary += f"\n**Commands Executed:** {self.commands_executed}\n"
        
        if self.files_generated:
            summary += f"\n**Files Generated:** {len(self.files_generated)}\n"
        
        if self.vulnerabilities_found:
            summary += f"\n**Vulnerabilities Found:** {len(self.vulnerabilities_found)}\n"
        
        return summary
    
    def mark_step_complete(self, step: str):
        """Mark a step as complete"""
        self.steps_completed.append({
            'step': step,
            'timestamp': time.time()
        })
        logger.info(f"[TASK-FOCUS] Step completed: {step}")


# Global instances per user
_task_focus_managers: Dict[int, TaskFocusManager] = {}

def get_task_focus_manager(user_id: int, task_description: str = None) -> TaskFocusManager:
    """Get or create task focus manager for user"""
    if user_id not in _task_focus_managers:
        if not task_description:
            task_description = "Unknown task"
        _task_focus_managers[user_id] = TaskFocusManager(user_id, task_description)
    elif task_description and _task_focus_managers[user_id].task_description == "Unknown task":
        _task_focus_managers[user_id].task_description = task_description
    
    return _task_focus_managers[user_id]

def clear_task_focus(user_id: int):
    """Clear task focus for user (when task complete)"""
    if user_id in _task_focus_managers:
        del _task_focus_managers[user_id]
        logger.info(f"[TASK-FOCUS] Cleared task focus for user {user_id}")
