# -*- coding: utf-8 -*-
"""
Template Manager - Save, retrieve, and use document templates from database
Supports user-specific and global templates
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
    logger.warning("Database not available. Template management will be limited.")


class TemplateManager:
    """Manage document templates stored in database"""
    
    def __init__(self, db: Database = None):
        """
        Initialize template manager
        
        Args:
            db: Database instance (auto-created if None)
        """
        if not DB_AVAILABLE:
            raise ImportError("Database module not available")
        
        self.db = db or Database()
        logger.info("Template Manager initialized")
    
    def save_template(self,
                    user_id: int,
                    name: str,
                    template_type: str,
                    template_data: Dict,
                    category: str = None,
                    description: str = None,
                    is_global: bool = False,
                    source_url: str = None,
                    file_path: str = None) -> Optional[int]:
        """
        Save a document template to database
        
        Args:
            user_id: User ID (None for global templates)
            name: Template name
            template_type: 'pdf', 'docx', or 'xlsx'
            template_data: Template structure/content
            category: Template category (invoice, report, etc.)
            description: Template description
            is_global: Whether template is global (admin only)
        
        Returns:
            Template ID if successful, None otherwise
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # Check if template with same name exists for user
            if not is_global:
                cursor.execute("""
                    SELECT id FROM document_templates 
                    WHERE user_id = %s AND name = %s
                """, (user_id, name))
                existing = cursor.fetchone()
                
                if existing:
                    # Add source_url and file_path to template_data if provided
                    if source_url or file_path:
                        if not isinstance(template_data, dict):
                            template_data = {}
                        if source_url:
                            template_data['source_url'] = source_url
                        if file_path:
                            template_data['file_path'] = file_path
                    
                    # Update existing template
                    cursor.execute("""
                        UPDATE document_templates 
                        SET template_data = %s, type = %s, category = %s, 
                            description = %s, file_path = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (json.dumps(template_data), template_type, category, description, file_path, existing[0]))
                    template_id = existing[0]
                else:
                    # Insert new template
                    # Add source_url and file_path to template_data if provided
                    if source_url or file_path:
                        if not isinstance(template_data, dict):
                            template_data = {}
                        if source_url:
                            template_data['source_url'] = source_url
                        if file_path:
                            template_data['file_path'] = file_path
                    
                    cursor.execute("""
                        INSERT INTO document_templates 
                        (user_id, name, type, category, description, template_data, file_path, is_global)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (user_id, name, template_type, category, description, json.dumps(template_data), file_path, is_global))
                    template_id = cursor.fetchone()[0]
            else:
                # Global template
                cursor.execute("""
                    SELECT id FROM document_templates 
                    WHERE name = %s AND is_global = TRUE
                """, (name,))
                existing = cursor.fetchone()
                
                if existing:
                    # Add source_url and file_path to template_data if provided
                    if source_url or file_path:
                        if not isinstance(template_data, dict):
                            template_data = {}
                        if source_url:
                            template_data['source_url'] = source_url
                        if file_path:
                            template_data['file_path'] = file_path
                    
                    cursor.execute("""
                        UPDATE document_templates 
                        SET template_data = %s, type = %s, category = %s, 
                            description = %s, file_path = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (json.dumps(template_data), template_type, category, description, file_path, existing[0]))
                    template_id = existing[0]
                else:
                    # Add source_url and file_path to template_data if provided
                    if source_url or file_path:
                        if not isinstance(template_data, dict):
                            template_data = {}
                        if source_url:
                            template_data['source_url'] = source_url
                        if file_path:
                            template_data['file_path'] = file_path
                    
                    cursor.execute("""
                        INSERT INTO document_templates 
                        (user_id, name, type, category, description, template_data, file_path, is_global)
                        VALUES (NULL, %s, %s, %s, %s, %s, %s, TRUE)
                        RETURNING id
                    """, (name, template_type, category, description, json.dumps(template_data), file_path))
                    template_id = cursor.fetchone()[0]
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"Template saved: {name} (ID: {template_id})")
            return template_id
            
        except Exception as e:
            logger.error(f"Error saving template: {e}", exc_info=True)
            if 'conn' in locals():
                conn.rollback()
                cursor.close()
                conn.close()
            return None
    
    def get_template(self, template_id: int = None, name: str = None, user_id: int = None) -> Optional[Dict]:
        """
        Retrieve a template by ID or name
        
        Args:
            template_id: Template ID
            name: Template name
            user_id: User ID (for user-specific templates)
        
        Returns:
            Template dict or None if not found
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            if template_id:
                cursor.execute("""
                    SELECT * FROM document_templates WHERE id = %s
                """, (template_id,))
            elif name and user_id:
                # Get user template or global template
                cursor.execute("""
                    SELECT * FROM document_templates 
                    WHERE (user_id = %s AND name = %s) OR (is_global = TRUE AND name = %s)
                    ORDER BY is_global ASC
                    LIMIT 1
                """, (user_id, name, name))
            elif name:
                # Get global template by name
                cursor.execute("""
                    SELECT * FROM document_templates 
                    WHERE name = %s AND is_global = TRUE
                """, (name,))
            else:
                cursor.close()
                conn.close()
                return None
            
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if not row:
                return None
            
            # Convert to dict
            template = {
                'id': row[0],
                'user_id': row[1],
                'name': row[2],
                'type': row[3],
                'category': row[4],
                'description': row[5],
                'template_data': json.loads(row[6]) if row[6] else {},
                'file_path': row[7],
                'created_at': row[8].isoformat() if row[8] else None,
                'updated_at': row[9].isoformat() if row[9] else None,
                'is_global': row[10]
            }
            
            return template
            
        except Exception as e:
            logger.error(f"Error retrieving template: {e}", exc_info=True)
            return None
    
    def list_templates(self, 
                      user_id: int = None,
                      template_type: str = None,
                      category: str = None,
                      include_global: bool = True) -> List[Dict]:
        """
        List available templates
        
        Args:
            user_id: User ID (to get user-specific templates)
            template_type: Filter by type ('pdf', 'docx', 'xlsx')
            category: Filter by category
            include_global: Include global templates
        
        Returns:
            List of template dicts
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            query = "SELECT * FROM document_templates WHERE 1=1"
            params = []
            
            if user_id:
                query += " AND (user_id = %s OR is_global = TRUE)"
                params.append(user_id)
            elif not include_global:
                query += " AND is_global = FALSE"
            
            if template_type:
                query += " AND type = %s"
                params.append(template_type)
            
            if category:
                query += " AND category = %s"
                params.append(category)
            
            query += " ORDER BY is_global ASC, name ASC"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            templates = []
            for row in rows:
                template = {
                    'id': row[0],
                    'user_id': row[1],
                    'name': row[2],
                    'type': row[3],
                    'category': row[4],
                    'description': row[5],
                    'template_data': json.loads(row[6]) if row[6] else {},
                    'file_path': row[7],
                    'created_at': row[8].isoformat() if row[8] else None,
                    'updated_at': row[9].isoformat() if row[9] else None,
                    'is_global': row[10]
                }
                templates.append(template)
            
            return templates
            
        except Exception as e:
            logger.error(f"Error listing templates: {e}", exc_info=True)
            return []
    
    def delete_template(self, template_id: int, user_id: int = None) -> bool:
        """
        Delete a template
        
        Args:
            template_id: Template ID
            user_id: User ID (required for user templates, optional for global)
        
        Returns:
            True if deleted, False otherwise
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # Check if user owns the template or is admin
            cursor.execute("""
                SELECT user_id, is_global FROM document_templates WHERE id = %s
            """, (template_id,))
            result = cursor.fetchone()
            
            if not result:
                cursor.close()
                conn.close()
                return False
            
            template_user_id, is_global = result
            
            # Check permissions
            if is_global:
                # Only admins can delete global templates
                if user_id and not self.db.is_admin(user_id):
                    cursor.close()
                    conn.close()
                    return False
            else:
                # User can only delete their own templates
                if user_id != template_user_id:
                    cursor.close()
                    conn.close()
                    return False
            
            # Delete template
            cursor.execute("DELETE FROM document_templates WHERE id = %s", (template_id,))
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"Template deleted: ID {template_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting template: {e}", exc_info=True)
            if 'conn' in locals():
                conn.rollback()
                cursor.close()
                conn.close()
            return False
    
    def get_template_categories(self, user_id: int = None) -> List[str]:
        """Get list of all template categories"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            if user_id:
                cursor.execute("""
                    SELECT DISTINCT category FROM document_templates 
                    WHERE (user_id = %s OR is_global = TRUE) AND category IS NOT NULL
                    ORDER BY category
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT DISTINCT category FROM document_templates 
                    WHERE category IS NOT NULL
                    ORDER BY category
                """)
            
            categories = [row[0] for row in cursor.fetchall() if row[0]]
            cursor.close()
            conn.close()
            
            return categories
            
        except Exception as e:
            logger.error(f"Error getting categories: {e}", exc_info=True)
            return []


# Global instance
_template_manager_instance = None

def get_template_manager(db: Database = None) -> TemplateManager:
    """Get or create global template manager instance"""
    global _template_manager_instance
    if _template_manager_instance is None:
        _template_manager_instance = TemplateManager(db)
    return _template_manager_instance
