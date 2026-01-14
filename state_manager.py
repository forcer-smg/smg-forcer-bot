# -*- coding: utf-8 -*-
"""
State Manager - Cursor-style working memory and state tracking
Tracks files read/modified, decisions made, errors encountered, and context persistence
"""

import logging
import threading
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


class StateManager:
    """Manages working memory and state tracking (Cursor-style)"""
    
    def __init__(self, user_id: int, task_id: Optional[str] = None):
        """
        Initialize State Manager
        
        Args:
            user_id: User ID for state isolation
            task_id: Optional task ID for task-specific state
        """
        self.user_id = user_id
        self.task_id = task_id
        self._lock = threading.Lock()
        
        # Working memory structure
        self.working_memory = {
            'files_read': [],  # List of files that have been read
            'files_modified': [],  # List of files that have been modified
            'files_created': [],  # List of files that have been created
            'decisions': [],  # List of decisions made with rationale
            'errors': [],  # List of errors encountered
            'tool_calls': [],  # List of tool calls made
            'execution_results': [],  # List of execution results
            'context': {},  # Additional context data
            'start_time': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat()
        }
        
        logger.info(f"StateManager initialized for user {user_id}, task {task_id}")
    
    def track_file_read(self, file_path: str, content_preview: Optional[str] = None):
        """Track that a file has been read"""
        with self._lock:
            file_entry = {
                'path': str(file_path),
                'timestamp': datetime.now().isoformat(),
                'content_preview': content_preview[:200] if content_preview else None
            }
            # Avoid duplicates
            if not any(f['path'] == str(file_path) for f in self.working_memory['files_read']):
                self.working_memory['files_read'].append(file_entry)
                self.working_memory['last_updated'] = datetime.now().isoformat()
                logger.debug(f"Tracked file read: {file_path}")
    
    def track_file_modified(self, file_path: str, change_type: str = 'modified', diff_preview: Optional[str] = None):
        """Track that a file has been modified"""
        with self._lock:
            file_entry = {
                'path': str(file_path),
                'change_type': change_type,  # 'modified', 'created', 'deleted'
                'timestamp': datetime.now().isoformat(),
                'diff_preview': diff_preview[:200] if diff_preview else None
            }
            # Avoid duplicates (update if exists)
            existing = next((f for f in self.working_memory['files_modified'] if f['path'] == str(file_path)), None)
            if existing:
                existing.update(file_entry)
            else:
                self.working_memory['files_modified'].append(file_entry)
            
            if change_type == 'created':
                self.working_memory['files_created'].append(file_entry)
            
            self.working_memory['last_updated'] = datetime.now().isoformat()
            logger.debug(f"Tracked file {change_type}: {file_path}")
    
    def track_decision(self, decision: str, rationale: str, context: Optional[Dict] = None):
        """Track a decision made during execution"""
        with self._lock:
            decision_entry = {
                'decision': decision,
                'rationale': rationale,
                'timestamp': datetime.now().isoformat(),
                'context': context or {}
            }
            self.working_memory['decisions'].append(decision_entry)
            self.working_memory['last_updated'] = datetime.now().isoformat()
            logger.debug(f"Tracked decision: {decision[:50]}...")
    
    def track_error(self, error: str, error_type: str = 'error', context: Optional[Dict] = None):
        """Track an error encountered during execution"""
        with self._lock:
            error_entry = {
                'error': error,
                'error_type': error_type,  # 'error', 'warning', 'failure'
                'timestamp': datetime.now().isoformat(),
                'context': context or {}
            }
            self.working_memory['errors'].append(error_entry)
            self.working_memory['last_updated'] = datetime.now().isoformat()
            logger.debug(f"Tracked error: {error[:50]}...")
    
    def track_tool_call(self, tool_name: str, arguments: Dict, result: Optional[Any] = None, success: bool = True):
        """Track a tool call made during execution"""
        with self._lock:
            tool_call_entry = {
                'tool': tool_name,
                'arguments': arguments,
                'result': str(result)[:500] if result else None,  # Truncate long results
                'success': success,
                'timestamp': datetime.now().isoformat()
            }
            self.working_memory['tool_calls'].append(tool_call_entry)
            self.working_memory['last_updated'] = datetime.now().isoformat()
            logger.debug(f"Tracked tool call: {tool_name}")
    
    def track_execution_result(self, result: Dict):
        """Track an execution result"""
        with self._lock:
            result_entry = {
                'result': result,
                'timestamp': datetime.now().isoformat()
            }
            self.working_memory['execution_results'].append(result_entry)
            self.working_memory['last_updated'] = datetime.now().isoformat()
            logger.debug(f"Tracked execution result")
    
    def get_working_memory_summary(self) -> str:
        """Get a summary of working memory for context"""
        with self._lock:
            summary_parts = []
            
            if self.working_memory['files_read']:
                summary_parts.append(f"Files Read: {len(self.working_memory['files_read'])}")
                for f in self.working_memory['files_read'][-5:]:  # Last 5
                    summary_parts.append(f"  - {f['path']}")
            
            if self.working_memory['files_modified']:
                summary_parts.append(f"\nFiles Modified: {len(self.working_memory['files_modified'])}")
                for f in self.working_memory['files_modified'][-5:]:  # Last 5
                    summary_parts.append(f"  - {f['path']} ({f['change_type']})")
            
            if self.working_memory['decisions']:
                summary_parts.append(f"\nRecent Decisions: {len(self.working_memory['decisions'])}")
                for d in self.working_memory['decisions'][-3:]:  # Last 3
                    summary_parts.append(f"  - {d['decision'][:50]}...")
            
            if self.working_memory['errors']:
                summary_parts.append(f"\nErrors Encountered: {len(self.working_memory['errors'])}")
                for e in self.working_memory['errors'][-3:]:  # Last 3
                    summary_parts.append(f"  - {e['error_type']}: {e['error'][:50]}...")
            
            return "\n".join(summary_parts) if summary_parts else "No state tracked yet"
    
    def get_context_for_ai(self) -> str:
        """Get formatted context for AI (Cursor-style)"""
        with self._lock:
            context_parts = ["[WORKING MEMORY]"]
            
            # Files read
            if self.working_memory['files_read']:
                context_parts.append("\nFiles Read:")
                for f in self.working_memory['files_read'][-10:]:  # Last 10
                    context_parts.append(f"  - {f['path']}")
            
            # Files modified
            if self.working_memory['files_modified']:
                context_parts.append("\nFiles Modified:")
                for f in self.working_memory['files_modified'][-10:]:  # Last 10
                    context_parts.append(f"  - {f['path']} ({f['change_type']})")
            
            # Recent decisions
            if self.working_memory['decisions']:
                context_parts.append("\nRecent Decisions:")
                for d in self.working_memory['decisions'][-5:]:  # Last 5
                    context_parts.append(f"  - {d['decision']}")
                    if d['rationale']:
                        context_parts.append(f"    Reason: {d['rationale'][:100]}")
            
            # Recent errors
            if self.working_memory['errors']:
                context_parts.append("\nRecent Errors:")
                for e in self.working_memory['errors'][-5:]:  # Last 5
                    context_parts.append(f"  - {e['error_type']}: {e['error']}")
            
            return "\n".join(context_parts)
    
    def get_state(self) -> Dict[str, Any]:
        """Get full state dictionary"""
        with self._lock:
            return self.working_memory.copy()
    
    def update_context(self, key: str, value: Any):
        """Update additional context data"""
        with self._lock:
            self.working_memory['context'][key] = value
            self.working_memory['last_updated'] = datetime.now().isoformat()
    
    def get_context(self, key: str, default: Any = None) -> Any:
        """Get context value"""
        with self._lock:
            return self.working_memory['context'].get(key, default)
    
    def clear_state(self):
        """Clear all state (use with caution)"""
        with self._lock:
            self.working_memory = {
                'files_read': [],
                'files_modified': [],
                'files_created': [],
                'decisions': [],
                'errors': [],
                'tool_calls': [],
                'execution_results': [],
                'context': {},
                'start_time': datetime.now().isoformat(),
                'last_updated': datetime.now().isoformat()
            }
            logger.info("State cleared")
