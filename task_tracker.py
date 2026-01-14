# -*- coding: utf-8 -*-
"""
Task Tracker - Track task completion status (Cursor-style)
Tracks plan steps, execution status, and results
"""

import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class TaskTracker:
    """Track task completion status"""
    
    def __init__(self, task_description: str, plan_file: Path = None):
        """
        Initialize task tracker
        
        Args:
            task_description: Description of the task
            plan_file: Optional path to plan file
        """
        self.task = task_description
        self.plan = []
        self.completed_steps = []
        self.failed_steps = []
        self.retried_steps = []
        self.results = []
        self.start_time = datetime.now()
        self.end_time = None
        self.plan_file = plan_file
        logger.info(f"Task tracker initialized: {task_description}")
    
    def add_step(self, step: str, step_type: str = "execution") -> int:
        """
        Add step to plan
        
        Args:
            step: Step description
            step_type: Type of step ('execution', 'test', 'retry')
        
        Returns:
            Step number (1-indexed)
        """
        step_num = len(self.plan) + 1
        step_info = {
            'number': step_num,
            'description': step,
            'type': step_type,
            'status': 'pending',
            'start_time': None,
            'end_time': None,
            'result': None,
            'error': None,
            'retry_count': 0
        }
        self.plan.append(step_info)
        logger.debug(f"Added step {step_num}: {step}")
        return step_num
    
    def mark_complete(self, step_number: int, result: Dict[str, Any] = None) -> bool:
        """
        Mark step as complete with results
        
        Args:
            step_number: Step number (1-indexed)
            result: Optional result dictionary
        
        Returns:
            True if marked successfully
        """
        if step_number < 1 or step_number > len(self.plan):
            logger.warning(f"Invalid step number: {step_number}")
            return False
        
        step = self.plan[step_number - 1]
        step['status'] = 'complete'
        step['end_time'] = datetime.now()
        step['result'] = result
        
        if step_number not in [s['number'] for s in self.completed_steps]:
            self.completed_steps.append(step)
        
        # Remove from failed if it was retried
        self.failed_steps = [s for s in self.failed_steps if s['number'] != step_number]
        
        logger.info(f"Step {step_number} marked as complete")
        return True
    
    def mark_failed(self, step_number: int, error: str, will_retry: bool = False) -> bool:
        """
        Mark step as failed
        
        Args:
            step_number: Step number (1-indexed)
            error: Error message
            will_retry: Whether step will be retried
        
        Returns:
            True if marked successfully
        """
        if step_number < 1 or step_number > len(self.plan):
            logger.warning(f"Invalid step number: {step_number}")
            return False
        
        step = self.plan[step_number - 1]
        step['status'] = 'failed' if not will_retry else 'retrying'
        step['end_time'] = datetime.now()
        step['error'] = error
        
        if step_number not in [s['number'] for s in self.failed_steps]:
            self.failed_steps.append(step)
        
        if will_retry:
            step['retry_count'] += 1
            if step_number not in [s['number'] for s in self.retried_steps]:
                self.retried_steps.append(step)
        
        logger.warning(f"Step {step_number} marked as failed: {error}")
        return True
    
    def mark_started(self, step_number: int) -> bool:
        """Mark step as started"""
        if step_number < 1 or step_number > len(self.plan):
            return False
        
        step = self.plan[step_number - 1]
        step['status'] = 'running'
        step['start_time'] = datetime.now()
        return True
    
    def add_result(self, result_text: str, result_type: str = "info"):
        """
        Add result to tracker
        
        Args:
            result_text: Result text
            result_type: Type of result ('info', 'success', 'warning', 'error')
        """
        result = {
            'text': result_text,
            'type': result_type,
            'timestamp': datetime.now()
        }
        self.results.append(result)
        logger.debug(f"Result added: {result_type} - {result_text}")
    
    def is_complete(self) -> bool:
        """
        Check if all steps complete
        
        Returns:
            True if all steps are complete
        """
        if not self.plan:
            return False
        
        all_complete = all(
            step['status'] == 'complete' 
            for step in self.plan
        )
        
        return all_complete
    
    def get_progress(self) -> Dict[str, Any]:
        """
        Get task progress information
        
        Returns:
            Dictionary with progress stats
        """
        total_steps = len(self.plan)
        completed = len(self.completed_steps)
        failed = len(self.failed_steps)
        retried = len(self.retried_steps)
        
        progress_pct = (completed / total_steps * 100) if total_steps > 0 else 0
        
        return {
            'total_steps': total_steps,
            'completed': completed,
            'failed': failed,
            'retried': retried,
            'progress_percent': progress_pct,
            'is_complete': self.is_complete(),
            'elapsed_time': str(datetime.now() - self.start_time) if self.start_time else None
        }
    
    def generate_summary(self) -> str:
        """
        Generate final summary markdown
        
        Returns:
            Markdown summary string
        """
        progress = self.get_progress()
        
        summary_lines = [
            "# Task Summary",
            "",
            f"**Task:** {self.task}",
            f"**Status:** {'✅ Complete' if progress['is_complete'] else '⏳ In Progress'}",
            f"**Started:** {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        
        if self.end_time:
            summary_lines.append(f"**Completed:** {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            elapsed = self.end_time - self.start_time
            summary_lines.append(f"**Duration:** {elapsed}")
        
        summary_lines.extend([
            "",
            "## Progress",
            "",
            f"- Total Steps: {progress['total_steps']}",
            f"- Completed: {progress['completed']} ✅",
            f"- Failed: {progress['failed']} ❌",
            f"- Retried: {progress['retried']} 🔄",
            f"- Progress: {progress['progress_percent']:.1f}%",
            ""
        ])
        
        if self.completed_steps:
            summary_lines.extend([
                "## Completed Steps",
                ""
            ])
            for step in self.completed_steps:
                summary_lines.append(f"- ✅ Step {step['number']}: {step['description']}")
            summary_lines.append("")
        
        if self.failed_steps:
            summary_lines.extend([
                "## Failed Steps",
                ""
            ])
            for step in self.failed_steps:
                error_text = f" - {step['error']}" if step['error'] else ""
                summary_lines.append(f"- ❌ Step {step['number']}: {step['description']}{error_text}")
            summary_lines.append("")
        
        if self.retried_steps:
            summary_lines.extend([
                "## Retried Steps",
                ""
            ])
            for step in self.retried_steps:
                summary_lines.append(f"- 🔄 Step {step['number']}: {step['description']} (retried {step['retry_count']} times)")
            summary_lines.append("")
        
        if self.results:
            summary_lines.extend([
                "## Results",
                ""
            ])
            for result in self.results:
                icon = {
                    'success': '✅',
                    'error': '❌',
                    'warning': '⚠️',
                    'info': 'ℹ️'
                }.get(result['type'], '•')
                summary_lines.append(f"{icon} {result['text']}")
            summary_lines.append("")
        
        return "\n".join(summary_lines)
    
    def finish(self):
        """Mark task as finished"""
        self.end_time = datetime.now()
        logger.info(f"Task finished: {self.task}")
