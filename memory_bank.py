# -*- coding: utf-8 -*-
"""
Memory Bank - Cursor-style external memory for maintaining task context
Stores structured notes, decisions, and summaries to keep focus on tasks
"""

import os
import json
import logging
import time
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class MemoryBank:
    """Cursor-style memory bank for task context and focus"""
    
    def __init__(self, workspace_path: str, user_id: int):
        """Initialize memory bank for user workspace"""
        self.workspace_path = Path(workspace_path)
        self.user_id = user_id
        self.memory_dir = self.workspace_path / ".context"
        self.memory_dir.mkdir(exist_ok=True)
        
        # Memory files
        self.task_memory_file = self.memory_dir / "task_memory.json"
        self.decisions_file = self.memory_dir / "decisions.json"
        self.summaries_file = self.memory_dir / "summaries.json"
        self.notes_file = self.memory_dir / "notes.md"
        
        # In-memory cache
        self._task_memory = self._load_json(self.task_memory_file, {})
        self._decisions = self._load_json(self.decisions_file, [])
        self._summaries = self._load_json(self.summaries_file, {})
        
    def _load_json(self, file_path: Path, default: Any) -> Any:
        """Load JSON file or return default"""
        try:
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"[MEMORY-BANK] Error loading {file_path}: {e}")
        return default
    
    def _save_json(self, file_path: Path, data: Any):
        """Save JSON file"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[MEMORY-BANK] Error saving {file_path}: {e}")
    
    def store_task_context(self, task_description: str, current_step: str, 
                          completed_steps: List[str], next_steps: List[str],
                          important_files: List[str] = None):
        """Store current task context (like Cursor's context building)"""
        self._task_memory = {
            'task_description': task_description,
            'current_step': current_step,
            'completed_steps': completed_steps,
            'next_steps': next_steps,
            'important_files': important_files or [],
            'last_updated': datetime.now().isoformat(),
            'timestamp': time.time()
        }
        self._save_json(self.task_memory_file, self._task_memory)
        logger.info(f"[MEMORY-BANK] Stored task context: {current_step}")
    
    def store_decision(self, decision: str, reasoning: str, context: str = None):
        """Store a decision made during task execution"""
        decision_entry = {
            'decision': decision,
            'reasoning': reasoning,
            'context': context,
            'timestamp': time.time(),
            'datetime': datetime.now().isoformat()
        }
        self._decisions.append(decision_entry)
        # Keep only last 50 decisions
        if len(self._decisions) > 50:
            self._decisions = self._decisions[-50:]
        self._save_json(self.decisions_file, self._decisions)
        logger.info(f"[MEMORY-BANK] Stored decision: {decision[:100]}")
    
    def store_summary(self, key: str, summary: str, metadata: Dict = None):
        """Store a summary (like Cursor's iterative summarization)"""
        self._summaries[key] = {
            'summary': summary,
            'metadata': metadata or {},
            'timestamp': time.time(),
            'datetime': datetime.now().isoformat()
        }
        self._save_json(self.summaries_file, self._summaries)
        logger.debug(f"[MEMORY-BANK] Stored summary: {key}")
    
    def get_task_context(self) -> Dict:
        """Get current task context"""
        return self._task_memory.copy()
    
    def get_recent_decisions(self, limit: int = 10) -> List[Dict]:
        """Get recent decisions (for plan → act loop)"""
        return self._decisions[-limit:]
    
    def get_summaries(self, keys: List[str] = None) -> Dict:
        """Get summaries (for context building)"""
        if keys:
            return {k: self._summaries.get(k) for k in keys if k in self._summaries}
        return self._summaries.copy()
    
    def add_note(self, note: str, category: str = "general"):
        """Add a note to the notes file (like .notes or README)"""
        try:
            note_entry = f"\n## [{category}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{note}\n"
            with open(self.notes_file, 'a', encoding='utf-8') as f:
                f.write(note_entry)
            logger.info(f"[MEMORY-BANK] Added note: {category}")
        except Exception as e:
            logger.error(f"[MEMORY-BANK] Error adding note: {e}")
    
    def get_context_for_ai(self, max_tokens: int = 2000) -> str:
        """
        Build context string for AI (like Cursor's context building)
        Trims and summarizes to stay within limits
        """
        context_parts = []
        
        # Task context
        if self._task_memory:
            task_desc = self._task_memory.get('task_description', '')
            current_step = self._task_memory.get('current_step', '')
            completed = self._task_memory.get('completed_steps', [])
            next_steps = self._task_memory.get('next_steps', [])
            
            context_parts.append(f"**Current Task:** {task_desc}")
            context_parts.append(f"**Current Step:** {current_step}")
            if completed:
                context_parts.append(f"**Completed Steps:** {', '.join(completed[-5:])}")
            if next_steps:
                context_parts.append(f"**Next Steps:** {', '.join(next_steps[:5])}")
        
        # Recent decisions (plan → act loop)
        recent_decisions = self.get_recent_decisions(5)
        if recent_decisions:
            context_parts.append("\n**Recent Decisions:**")
            for decision in recent_decisions:
                context_parts.append(f"- {decision['decision']}: {decision['reasoning'][:100]}")
        
        # Important summaries
        summaries = self.get_summaries()
        if summaries:
            context_parts.append("\n**Key Summaries:**")
            for key, summary_data in list(summaries.items())[-3:]:
                context_parts.append(f"- {key}: {summary_data['summary'][:150]}")
        
        # Important files
        if self._task_memory.get('important_files'):
            context_parts.append(f"\n**Important Files:** {', '.join(self._task_memory['important_files'][:5])}")
        
        context_str = "\n".join(context_parts)
        
        # Trim if too long (approximate token count: 1 token ≈ 4 chars)
        if len(context_str) > max_tokens * 4:
            # Keep first part and last part
            half = max_tokens * 2
            context_str = context_str[:half] + "\n... [context trimmed] ...\n" + context_str[-half:]
            logger.debug(f"[MEMORY-BANK] Trimmed context from {len(context_str)} to fit {max_tokens} tokens")
        
        return context_str
    
    def update_task_progress(self, step: str, status: str = "in_progress"):
        """Update task progress (like Cursor tracking task state)"""
        if not self._task_memory:
            return
        
        completed = self._task_memory.get('completed_steps', [])
        if status == "completed" and step not in completed:
            completed.append(step)
            self._task_memory['completed_steps'] = completed
        
        if status == "in_progress":
            self._task_memory['current_step'] = step
        
        self._task_memory['last_updated'] = datetime.now().isoformat()
        self._task_memory['timestamp'] = time.time()
        self._save_json(self.task_memory_file, self._task_memory)
        logger.info(f"[MEMORY-BANK] Updated progress: {step} - {status}")
    
    def mark_task_complete(self, final_summary: str = None):
        """Mark task as complete"""
        if self._task_memory:
            self._task_memory['status'] = 'complete'
            self._task_memory['completed_at'] = datetime.now().isoformat()
            if final_summary:
                self.store_summary('final_result', final_summary)
            self._save_json(self.task_memory_file, self._task_memory)
            logger.info(f"[MEMORY-BANK] Task marked complete")


# Global instances per user/workspace
_memory_banks: Dict[tuple, MemoryBank] = {}

def get_memory_bank(workspace_path: str, user_id: int) -> MemoryBank:
    """Get or create memory bank for user workspace"""
    key = (workspace_path, user_id)
    if key not in _memory_banks:
        _memory_banks[key] = MemoryBank(workspace_path, user_id)
    return _memory_banks[key]
