# -*- coding: utf-8 -*-
"""
User State Manager - Persist user work state across redeployments
Tracks what users are working on, current tasks, and pending results
"""

import os
import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Import database
try:
    from database_hybrid import Database
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    logger.warning("Database not available. State persistence will be limited.")


class UserStateManager:
    """Manage user work state persistence"""
    
    def __init__(self, db: Database = None):
        """
        Initialize user state manager
        
        Args:
            db: Database instance (auto-created if None)
        """
        if not DB_AVAILABLE:
            raise ImportError("Database module not available")
        
        self.db = db or Database()
        self._init_state_table()
        logger.info("User State Manager initialized")
    
    def _init_state_table(self):
        """Initialize user_state table in database"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_state (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    state_key TEXT NOT NULL,
                    state_value JSONB,
                    workspace_path TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, state_key)
                )
            """)
            
            # Create index for faster lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_state_user_id 
                ON user_state(user_id)
            """)
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info("User state table initialized")
        except Exception as e:
            logger.error(f"Error initializing user state table: {e}", exc_info=True)
    
    def save_state(self, user_id: int, state_key: str, state_value: Dict, workspace_path: str = None) -> bool:
        """
        Save user state to database
        
        Args:
            user_id: User ID
            state_key: State key (e.g., 'current_project', 'pending_task', 'last_photo')
            state_value: State value (dict)
            workspace_path: Optional workspace path
        
        Returns:
            True if saved successfully
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO user_state (user_id, state_key, state_value, workspace_path)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, state_key)
                DO UPDATE SET 
                    state_value = EXCLUDED.state_value,
                    workspace_path = EXCLUDED.workspace_path,
                    last_updated = CURRENT_TIMESTAMP
            """, (user_id, state_key, json.dumps(state_value), workspace_path))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"State saved: user={user_id}, key={state_key}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving state: {e}", exc_info=True)
            if 'conn' in locals():
                conn.rollback()
                cursor.close()
                conn.close()
            return False
    
    def get_state(self, user_id: int, state_key: str) -> Optional[Dict]:
        """
        Get user state from database
        
        Args:
            user_id: User ID
            state_key: State key
        
        Returns:
            State value dict or None if not found
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT state_value, workspace_path, last_updated
                FROM user_state
                WHERE user_id = %s AND state_key = %s
            """, (user_id, state_key))
            
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if row and row[0]:
                state_value = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                return {
                    'value': state_value,
                    'workspace_path': row[1],
                    'last_updated': row[2].isoformat() if row[2] else None
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting state: {e}", exc_info=True)
            return None
    
    def get_all_user_state(self, user_id: int) -> Dict[str, Any]:
        """
        Get all state for a user
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary of all state keys and values
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT state_key, state_value, workspace_path, last_updated
                FROM user_state
                WHERE user_id = %s
                ORDER BY last_updated DESC
            """, (user_id,))
            
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            state = {}
            for row in rows:
                state_key = row[0]
                state_value = json.loads(row[1]) if isinstance(row[1], str) else row[1]
                state[state_key] = {
                    'value': state_value,
                    'workspace_path': row[2],
                    'last_updated': row[3].isoformat() if row[3] else None
                }
            
            return state
            
        except Exception as e:
            logger.error(f"Error getting all user state: {e}", exc_info=True)
            return {}
    
    def delete_state(self, user_id: int, state_key: str) -> bool:
        """
        Delete user state
        
        Args:
            user_id: User ID
            state_key: State key to delete
        
        Returns:
            True if deleted successfully
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM user_state
                WHERE user_id = %s AND state_key = %s
            """, (user_id, state_key))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"State deleted: user={user_id}, key={state_key}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting state: {e}", exc_info=True)
            if 'conn' in locals():
                conn.rollback()
                cursor.close()
                conn.close()
            return False
    
    def save_current_project(self, user_id: int, project_name: str, project_type: str, workspace_path: str, metadata: Dict = None) -> bool:
        """Save current project state"""
        state_value = {
            'project_name': project_name,
            'project_type': project_type,
            'metadata': metadata or {},
            'saved_at': datetime.now().isoformat()
        }
        return self.save_state(user_id, 'current_project', state_value, workspace_path)
    
    def get_current_project(self, user_id: int) -> Optional[Dict]:
        """Get current project state"""
        state = self.get_state(user_id, 'current_project')
        return state['value'] if state else None
    
    def save_pending_task(self, user_id: int, task_description: str, task_type: str, expected_results: List[str], workspace_path: str = None) -> bool:
        """Save pending task that needs completion"""
        state_value = {
            'task_description': task_description,
            'task_type': task_type,
            'expected_results': expected_results,
            'status': 'pending',
            'created_at': datetime.now().isoformat(),
            'results_delivered': []
        }
        return self.save_state(user_id, 'pending_task', state_value, workspace_path)
    
    def get_pending_task(self, user_id: int) -> Optional[Dict]:
        """Get pending task"""
        state = self.get_state(user_id, 'pending_task')
        return state['value'] if state else None
    
    def mark_result_delivered(self, user_id: int, result_type: str, result_path: str = None) -> bool:
        """Mark a result as delivered"""
        task = self.get_pending_task(user_id)
        if task:
            if 'results_delivered' not in task:
                task['results_delivered'] = []
            task['results_delivered'].append({
                'type': result_type,
                'path': result_path,
                'delivered_at': datetime.now().isoformat()
            })
            return self.save_state(user_id, 'pending_task', task, task.get('workspace_path'))
        return False
    
    def clear_pending_task(self, user_id: int) -> bool:
        """Clear pending task after completion"""
        return self.delete_state(user_id, 'pending_task')


# Global instance
_user_state_manager_instance = None

def get_user_state_manager(db: Database = None) -> UserStateManager:
    """Get or create global user state manager instance"""
    global _user_state_manager_instance
    if _user_state_manager_instance is None:
        _user_state_manager_instance = UserStateManager(db)
    return _user_state_manager_instance
