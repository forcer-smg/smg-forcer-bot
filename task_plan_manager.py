# -*- coding: utf-8 -*-
"""
Task Plan Manager - Cursor-style task tracking with .md plan files
Manages persistent plan files with checkbox tracking and summary generation
"""

import os
import re
import json
import logging
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from urllib.parse import quote

logger = logging.getLogger(__name__)


class TaskPlanManager:
    """Manages task plans as .md files with checkbox tracking"""
    
    def __init__(self, workspace_root: Optional[Path] = None):
        """
        Initialize Task Plan Manager
        
        Args:
            workspace_root: Base workspace directory (defaults to current directory)
        """
        if workspace_root:
            self.workspace_root = Path(workspace_root)
        else:
            self.workspace_root = Path(os.getcwd())
        
        # Thread safety for concurrent access
        self._locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()
        
        logger.info(f"TaskPlanManager initialized with workspace: {self.workspace_root}")
    
    def _get_plan_dir(self, user_id: int) -> Path:
        """Get or create plans directory for user"""
        plans_dir = self.workspace_root / f"user_{user_id}" / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        return plans_dir
    
    def _get_lock(self, task_id: str) -> threading.Lock:
        """Get thread lock for a specific task"""
        with self._global_lock:
            if task_id not in self._locks:
                self._locks[task_id] = threading.Lock()
            return self._locks[task_id]
    
    def create_plan(self, task_id: str, user_id: int, plan_data: Dict) -> str:
        """
        Create a new plan .md file with checkboxes
        
        Args:
            task_id: Unique task identifier
            user_id: Telegram user ID
            plan_data: Plan data dictionary containing:
                - title: Task title
                - description: Task description
                - steps: List of step dictionaries with 'action', 'tool', 'command', etc.
                - complexity: Task complexity (low/medium/high)
                - estimated_time: Estimated time in minutes
                - risk_level: Risk level (low/medium/high)
        
        Returns:
            Path to created plan file
        """
        plans_dir = self._get_plan_dir(user_id)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        plan_file = plans_dir / f"{task_id}_{timestamp}.md"
        
        # Build plan content
        plan_content = []
        plan_content.append(f"# Task Plan: {plan_data.get('title', 'Untitled Task')}\n")
        plan_content.append(f"**Task ID:** `{task_id}`\n")
        plan_content.append(f"**Created:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        plan_content.append(f"**User:** {user_id}\n")
        plan_content.append(f"**Status:** 🔄 In Progress\n\n")
        
        # Task description
        description = plan_data.get('description', plan_data.get('title', 'No description'))
        plan_content.append(f"## Task Description\n\n{description}\n\n")
        
        # Task metadata
        complexity = plan_data.get('complexity', 'medium')
        estimated_time = plan_data.get('estimated_time', 'Unknown')
        risk_level = plan_data.get('risk_level', 'medium')
        
        plan_content.append("## Task Metadata\n\n")
        plan_content.append(f"- **Complexity:** {complexity}")
        plan_content.append(f"- **Estimated Time:** {estimated_time} minutes")
        plan_content.append(f"- **Risk Level:** {risk_level}\n\n")
        
        # Execution steps with checkboxes
        steps = plan_data.get('steps', [])
        if steps:
            plan_content.append("## Execution Steps\n\n")
            for i, step in enumerate(steps, 1):
                action = step.get('action', step.get('description', f'Step {i}'))
                tool = step.get('tool', 'standard command')
                command = step.get('command', '')
                dependencies = step.get('dependencies', [])
                expected = step.get('expected', '')
                
                plan_content.append(f"### Step {i}: {action}\n")
                plan_content.append(f"- [ ] **Status:** Pending\n")
                plan_content.append(f"- **Tool:** {tool}\n")
                if command:
                    plan_content.append(f"- **Command:**\n```bash\n{command}\n```\n")
                if dependencies:
                    plan_content.append(f"- **Dependencies:** {', '.join(dependencies)}\n")
                if expected:
                    plan_content.append(f"- **Expected:** {expected}\n")
                plan_content.append("\n")
        else:
            plan_content.append("## Execution Steps\n\n")
            plan_content.append("- [ ] Task execution steps will be added here\n\n")
        
        # Progress tracking section
        plan_content.append("## Progress\n\n")
        plan_content.append(f"- **Total Steps:** {len(steps)}\n")
        plan_content.append(f"- **Completed Steps:** 0\n")
        plan_content.append(f"- **Progress:** 0%\n")
        plan_content.append(f"- **Started:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        plan_content.append(f"- **Completed:** -\n\n")
        
        # Write plan file
        try:
            with open(plan_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(plan_content))
            logger.info(f"Created plan file: {plan_file}")
            return str(plan_file)
        except Exception as e:
            logger.error(f"Error creating plan file: {e}")
            raise
    
    def update_step_status(self, task_id: str, user_id: int, step_number: int, 
                          completed: bool = True, notes: Optional[str] = None) -> bool:
        """
        Update step status in plan file (checkbox [ ] → [x])
        
        Args:
            task_id: Task identifier
            user_id: Telegram user ID
            step_number: Step number (1-indexed)
            completed: Whether step is completed
            notes: Optional completion notes
        
        Returns:
            True if update successful, False otherwise
        """
        plans_dir = self._get_plan_dir(user_id)
        
        # Find plan file for this task
        plan_files = list(plans_dir.glob(f"{task_id}_*.md"))
        if not plan_files:
            logger.warning(f"No plan file found for task {task_id}")
            return False
        
        # Use most recent plan file
        plan_file = max(plan_files, key=lambda p: p.stat().st_mtime)
        
        lock = self._get_lock(task_id)
        with lock:
            try:
                # Read current content
                with open(plan_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Update step checkbox
                step_pattern = rf"(### Step {step_number}:.*?\n)(- \[ \] \*\*Status:\*\* Pending)"
                replacement = r"\1- [x] **Status:** Completed"
                if completed:
                    new_content = re.sub(step_pattern, replacement, content, flags=re.DOTALL)
                else:
                    # Revert to pending
                    step_pattern = rf"(### Step {step_number}:.*?\n)(- \[x\] \*\*Status:\*\* Completed)"
                    replacement = r"\1- [ ] **Status:** Pending"
                    new_content = re.sub(step_pattern, replacement, content, flags=re.DOTALL)
                
                # Add completion timestamp and notes if provided
                if completed and notes:
                    # Find the step section and add notes
                    step_section_pattern = rf"(### Step {step_number}:.*?\n- \[x\] \*\*Status:\*\* Completed\n)"
                    notes_text = f"\\1- **Completed:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    if notes:
                        notes_text += f"- **Notes:** {notes}\n"
                    new_content = re.sub(step_section_pattern, notes_text, new_content, flags=re.DOTALL)
                elif completed:
                    # Just add timestamp
                    step_section_pattern = rf"(### Step {step_number}:.*?\n- \[x\] \*\*Status:\*\* Completed\n)"
                    notes_text = f"\\1- **Completed:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    new_content = re.sub(step_section_pattern, notes_text, new_content, flags=re.DOTALL)
                
                # Update progress section
                new_content = self._update_progress_section(new_content, plan_file)
                
                # Write updated content
                with open(plan_file, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                
                logger.info(f"Updated step {step_number} status in plan {plan_file}")
                return True
                
            except Exception as e:
                logger.error(f"Error updating step status: {e}")
                return False
    
    def _update_progress_section(self, content: str, plan_file: Path) -> str:
        """Update progress section in plan file"""
        # Count completed steps
        completed_matches = re.findall(r'- \[x\] \*\*Status:\*\* Completed', content)
        completed_count = len(completed_matches)
        
        # Count total steps
        total_matches = re.findall(r'### Step \d+:', content)
        total_count = len(total_matches)
        
        # Calculate progress percentage
        progress_pct = int((completed_count / total_count * 100)) if total_count > 0 else 0
        
        # Update progress section
        progress_pattern = r'(## Progress\n\n)(.*?)(\n\n)'
        progress_content = (
            f"- **Total Steps:** {total_count}\n"
            f"- **Completed Steps:** {completed_count}\n"
            f"- **Progress:** {progress_pct}%\n"
        )
        
        # Find started time (keep it)
        started_match = re.search(r'- \*\*Started:\*\* (.+?)\n', content)
        if started_match:
            progress_content += f"- **Started:** {started_match.group(1)}\n"
        else:
            progress_content += f"- **Started:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        # Update completed time
        if completed_count == total_count and total_count > 0:
            progress_content += f"- **Completed:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            # Update status to completed
            content = re.sub(r'\*\*Status:\*\* 🔄 In Progress', '**Status:** ✅ Completed', content)
        else:
            progress_content += "- **Completed:** -\n"
        
        new_content = re.sub(progress_pattern, f'\\1{progress_content}\\3', content, flags=re.DOTALL)
        return new_content
    
    def get_plan_progress(self, task_id: str, user_id: int) -> Dict:
        """
        Get current progress of a task plan
        
        Returns:
            Dictionary with progress information
        """
        plans_dir = self._get_plan_dir(user_id)
        plan_files = list(plans_dir.glob(f"{task_id}_*.md"))
        
        if not plan_files:
            return {
                'found': False,
                'total_steps': 0,
                'completed_steps': 0,
                'progress_percentage': 0
            }
        
        plan_file = max(plan_files, key=lambda p: p.stat().st_mtime)
        
        try:
            with open(plan_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract progress info
            total_match = re.search(r'- \*\*Total Steps:\*\* (\d+)', content)
            completed_match = re.search(r'- \*\*Completed Steps:\*\* (\d+)', content)
            progress_match = re.search(r'- \*\*Progress:\*\* (\d+)%', content)
            
            total_steps = int(total_match.group(1)) if total_match else 0
            completed_steps = int(completed_match.group(1)) if completed_match else 0
            progress_pct = int(progress_match.group(1)) if progress_match else 0
            
            return {
                'found': True,
                'plan_file': str(plan_file),
                'total_steps': total_steps,
                'completed_steps': completed_steps,
                'progress_percentage': progress_pct,
                'is_complete': completed_steps == total_steps and total_steps > 0
            }
        except Exception as e:
            logger.error(f"Error reading plan progress: {e}")
            return {
                'found': False,
                'error': str(e)
            }
    
    def generate_final_summary(self, task_id: str, user_id: int, original_message: str,
                               plan: Optional[Dict], execution_results: List[str],
                               generated_files: List[str], full_response: str,
                               start_time: Optional[float] = None) -> str:
        """
        Generate final summary .md document
        
        Args:
            task_id: Task identifier
            user_id: Telegram user ID
            original_message: Original user request
            plan: Plan data dictionary
            execution_results: List of execution result strings
            generated_files: List of generated file paths
            full_response: Full AI response text
            start_time: Task start timestamp (for duration calculation)
        
        Returns:
            Path to generated summary file
        """
        plans_dir = self._get_plan_dir(user_id)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_file = plans_dir / f"{task_id}_{timestamp}_summary.md"
        
        # Calculate duration
        duration_text = "Unknown"
        if start_time:
            duration_seconds = time.time() - start_time
            if duration_seconds < 60:
                duration_text = f"{int(duration_seconds)} seconds"
            else:
                duration_text = f"{int(duration_seconds / 60)} minutes {int(duration_seconds % 60)} seconds"
        
        # Build summary content
        summary_content = []
        summary_content.append(f"# Task Summary: {plan.get('title', original_message[:100]) if plan else original_message[:100]}\n\n")
        summary_content.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        summary_content.append(f"**User:** {user_id}\n")
        summary_content.append(f"**Task ID:** `{task_id}`\n")
        summary_content.append(f"**Status:** ✅ Completed\n\n")
        
        # Task Overview
        summary_content.append("## Task Overview\n\n")
        summary_content.append(f"{original_message}\n\n")
        
        # Execution Summary
        summary_content.append("## Execution Summary\n\n")
        if plan:
            total_steps = len(plan.get('steps', []))
            executed_count = len([r for r in execution_results if '✅' in r or 'Executed' in r])
            summary_content.append(f"- **Total Steps:** {total_steps}\n")
            summary_content.append(f"- **Completed Steps:** {executed_count}\n")
            success_rate = int((executed_count / total_steps * 100)) if total_steps > 0 else 100
            summary_content.append(f"- **Success Rate:** {success_rate}%\n")
        else:
            summary_content.append(f"- **Commands Executed:** {len(execution_results)}\n")
        
        summary_content.append(f"- **Duration:** {duration_text}\n")
        summary_content.append(f"- **Files Generated:** {len(generated_files)}\n\n")
        
        # Files Created/Modified
        if generated_files:
            summary_content.append("## Files Created/Modified\n\n")
            for file_path in generated_files[:20]:  # Limit to first 20 files
                file_name = os.path.basename(file_path) if os.path.sep in file_path else file_path
                # Check if file exists to get description
                if os.path.exists(file_path):
                    try:
                        file_size = os.path.getsize(file_path)
                        summary_content.append(f"- `{file_name}` ({file_size} bytes)\n")
                    except:
                        summary_content.append(f"- `{file_name}`\n")
                else:
                    summary_content.append(f"- `{file_name}` (not found)\n")
            if len(generated_files) > 20:
                summary_content.append(f"\n*... and {len(generated_files) - 20} more files*\n")
            summary_content.append("\n")
        
        # Key Results
        if execution_results:
            summary_content.append("## Key Results\n\n")
            # Show last 10 results
            for i, result in enumerate(execution_results[-10:], 1):
                result_preview = result[:300].replace('\n', ' ').strip()
                summary_content.append(f"{i}. {result_preview}...\n")
            summary_content.append("\n")
        
        # Code Changes (if applicable)
        code_blocks = re.findall(r'```(?:python|javascript|typescript|bash|sh|cmd|powershell)?\s*\n(.*?)\n```', 
                                full_response, re.DOTALL | re.IGNORECASE)
        if code_blocks:
            summary_content.append("## Code Changes\n\n")
            summary_content.append("Key code changes were made during execution:\n\n")
            for i, code_block in enumerate(code_blocks[:5], 1):  # First 5 code blocks
                summary_content.append(f"### Code Block {i}\n\n")
                summary_content.append(f"```\n{code_block[:500]}\n```\n\n")
            if len(code_blocks) > 5:
                summary_content.append(f"*... and {len(code_blocks) - 5} more code blocks*\n\n")
        
        # Next Steps / Recommendations
        summary_content.append("## Next Steps\n\n")
        if plan and plan.get('steps'):
            remaining = [s for s in plan.get('steps', []) if s.get('action')]
            if remaining:
                summary_content.append("Consider the following:\n\n")
                for step in remaining[:5]:
                    summary_content.append(f"- {step.get('action', 'Continue task')}\n")
            else:
                summary_content.append("✅ All planned steps have been completed.\n")
        else:
            summary_content.append("Task completed successfully. Review the results and files generated.\n")
        summary_content.append("\n")
        
        # Usage Instructions (if code was generated)
        if generated_files and any(f.endswith(('.py', '.js', '.ts', '.sh', '.bat', '.ps1')) for f in generated_files):
            summary_content.append("## Usage Instructions\n\n")
            summary_content.append("To use the generated code:\n\n")
            script_files = [f for f in generated_files if f.endswith(('.py', '.js', '.ts', '.sh', '.bat', '.ps1'))]
            for script_file in script_files[:5]:
                file_name = os.path.basename(script_file)
                if script_file.endswith('.py'):
                    summary_content.append(f"**{file_name}:**\n```bash\npython {file_name}\n```\n\n")
                elif script_file.endswith('.sh'):
                    summary_content.append(f"**{file_name}:**\n```bash\nchmod +x {file_name}\n./{file_name}\n```\n\n")
                elif script_file.endswith('.bat'):
                    summary_content.append(f"**{file_name}:**\n```cmd\n{file_name}\n```\n\n")
            summary_content.append("\n")
        
        # Write summary file
        try:
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(summary_content))
            logger.info(f"Generated summary file: {summary_file}")
            return str(summary_file)
        except Exception as e:
            logger.error(f"Error generating summary file: {e}")
            raise
