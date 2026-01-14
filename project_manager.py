# -*- coding: utf-8 -*-
"""
Project Manager - Detects existing projects, builds upon them, and maintains context
Creates Cursor-style PROJECT_CONTEXT.md files for each project
"""

import os
import re
import json
import logging
import threading
import time
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import hashlib

logger = logging.getLogger(__name__)


class ProjectManager:
    """Manages user projects with detection, context building, and retention"""
    
    def __init__(self, workspace_root: Optional[Path] = None, secure_memory=None, vector_memory=None):
        """
        Initialize Project Manager
        
        Args:
            workspace_root: Base workspace directory
            secure_memory: Secure memory manager instance (for 3-day retention)
            vector_memory: Vector memory manager instance (for semantic search)
        """
        if workspace_root:
            self.workspace_root = Path(workspace_root)
        else:
            self.workspace_root = Path(os.getcwd())
        
        self.secure_memory = secure_memory
        self.vector_memory = vector_memory
        
        # Thread safety
        self._locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()
        
        # Project cache (user_id -> project_name -> project_info)
        self._project_cache: Dict[int, Dict[str, Dict]] = {}
        
        logger.info(f"ProjectManager initialized with workspace: {self.workspace_root}")
    
    def _get_lock(self, key: str) -> threading.Lock:
        """Get thread lock for a specific key"""
        with self._global_lock:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            return self._locks[key]
    
    def _get_projects_dir(self, user_id: int) -> Path:
        """Get projects directory for user"""
        return self.workspace_root / f"user_{user_id}" / "projects"
    
    def _get_projects_index_path(self, user_id: int) -> Path:
        """Get path to projects index file"""
        return self._get_projects_dir(user_id) / ".projects_index.json"
    
    def _load_projects_index(self, user_id: int) -> Dict:
        """Load projects index for user"""
        index_path = self._get_projects_index_path(user_id)
        if index_path.exists():
            try:
                with open(index_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading projects index for user {user_id}: {e}")
        return {}
    
    def _save_projects_index(self, user_id: int, index: Dict):
        """Save projects index for user"""
        index_path = self._get_projects_index_path(user_id)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(index, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving projects index for user {user_id}: {e}")
    
    def detect_existing_projects(self, user_id: int) -> List[Dict]:
        """
        Scan workspace for existing projects
        
        Returns:
            List of project info dictionaries
        """
        projects_dir = self._get_projects_dir(user_id)
        projects = []
        
        if not projects_dir.exists():
            return projects
        
        # Load index
        index = self._load_projects_index(user_id)
        
        # Scan directories
        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir() or project_dir.name.startswith('.'):
                continue
            
            project_name = project_dir.name
            context_file = project_dir / "PROJECT_CONTEXT.md"
            
            # Get metadata from index or directory
            project_info = index.get(project_name, {})
            
            # Get last modified time
            if context_file.exists():
                last_modified = datetime.fromtimestamp(context_file.stat().st_mtime)
            else:
                last_modified = datetime.fromtimestamp(project_dir.stat().st_mtime)
            
            projects.append({
                'name': project_name,
                'path': str(project_dir),
                'created_at': project_info.get('created_at', last_modified.isoformat()),
                'last_accessed': project_info.get('last_accessed', last_modified.isoformat()),
                'description': project_info.get('description', ''),
                'has_context': context_file.exists()
            })
        
        return projects
    
    def auto_detect_project_name(self, task_description: str) -> str:
        """
        Extract project name from task description
        
        Args:
            task_description: User's task description
            
        Returns:
            Sanitized project name
        """
        # Remove common prefixes
        description = task_description.lower().strip()
        prefixes = ['generate', 'create', 'build', 'make', 'develop', 'write', 'code']
        for prefix in prefixes:
            if description.startswith(prefix):
                description = description[len(prefix):].strip()
        
        # Extract key phrases (nouns/noun phrases)
        # Look for patterns like "python code checker", "account checker", etc.
        words = re.findall(r'\b[a-z]+\b', description)
        
        # Filter out common stop words
        stop_words = {'a', 'an', 'the', 'for', 'on', 'in', 'at', 'to', 'with', 'that', 'this', 'is', 'can', 'will'}
        meaningful_words = [w for w in words if w not in stop_words and len(w) > 2]
        
        # Take first 2-3 meaningful words as project name
        if meaningful_words:
            project_name = '_'.join(meaningful_words[:3])
        else:
            # Fallback: use first few words
            project_name = '_'.join(words[:3]) if words else 'project'
        
        # Sanitize for directory name
        project_name = re.sub(r'[^a-z0-9_]', '', project_name)
        project_name = re.sub(r'_+', '_', project_name).strip('_')
        
        # Ensure minimum length
        if len(project_name) < 3:
            project_name = 'project_' + project_name
        
        # Limit length
        if len(project_name) > 50:
            project_name = project_name[:50]
        
        return project_name
    
    def find_matching_project(self, user_id: int, task_description: str) -> Optional[Dict]:
        """
        Find existing project that matches task description
        
        Args:
            user_id: User ID
            task_description: Task description to match
            
        Returns:
            Matching project info or None
        """
        existing_projects = self.detect_existing_projects(user_id)
        if not existing_projects:
            return None
        
        # Simple keyword matching (can be enhanced with semantic search)
        task_lower = task_description.lower()
        task_keywords = set(re.findall(r'\b[a-z]{3,}\b', task_lower))
        
        best_match = None
        best_score = 0
        
        for project in existing_projects:
            # Check project name
            name_lower = project['name'].lower().replace('_', ' ')
            name_keywords = set(re.findall(r'\b[a-z]{3,}\b', name_lower))
            
            # Check description
            desc_lower = project.get('description', '').lower()
            desc_keywords = set(re.findall(r'\b[a-z]{3,}\b', desc_lower))
            
            # Calculate match score
            name_match = len(task_keywords & name_keywords)
            desc_match = len(task_keywords & desc_keywords)
            score = name_match * 2 + desc_match  # Name matches are weighted higher
            
            if score > best_score and score > 0:
                best_score = score
                best_match = project
        
        return best_match
    
    def create_or_get_project(self, user_id: int, task_description: str, 
                             project_name: Optional[str] = None) -> Tuple[str, Path, bool]:
        """
        Create new project or get existing matching project
        
        Args:
            user_id: User ID
            task_description: Task description
            project_name: Optional explicit project name
            
        Returns:
            Tuple of (project_name, project_path, is_new)
        """
        lock = self._get_lock(f"project_{user_id}")
        
        with lock:
            # Try to find matching project
            if not project_name:
                matching_project = self.find_matching_project(user_id, task_description)
                if matching_project:
                    project_name = matching_project['name']
                    project_path = Path(matching_project['path'])
                    is_new = False
                    
                    # Update last accessed
                    self._update_project_metadata(user_id, project_name, last_accessed=datetime.now().isoformat())
                    
                    logger.info(f"Found existing project '{project_name}' for user {user_id}")
                    return project_name, project_path, is_new
            
            # Auto-detect project name if not provided
            if not project_name:
                project_name = self.auto_detect_project_name(task_description)
            
            # Check if project already exists
            projects_dir = self._get_projects_dir(user_id)
            project_path = projects_dir / project_name
            
            if project_path.exists():
                is_new = False
                # Update last accessed
                self._update_project_metadata(user_id, project_name, last_accessed=datetime.now().isoformat())
                logger.info(f"Using existing project '{project_name}' for user {user_id}")
            else:
                # Create new project
                project_path.mkdir(parents=True, exist_ok=True)
                
                # Create subdirectories
                (project_path / "files").mkdir(exist_ok=True)
                (project_path / "tasks").mkdir(exist_ok=True)
                
                # Initialize PROJECT_CONTEXT.md
                self._initialize_project_context(project_path, project_name, task_description)
                
                # Update index
                self._update_project_metadata(user_id, project_name, 
                                             created_at=datetime.now().isoformat(),
                                             last_accessed=datetime.now().isoformat(),
                                             description=task_description[:200])
                
                is_new = True
                logger.info(f"Created new project '{project_name}' for user {user_id}")
            
            return project_name, project_path, is_new
    
    def _update_project_metadata(self, user_id: int, project_name: str, **updates):
        """Update project metadata in index"""
        index = self._load_projects_index(user_id)
        
        if project_name not in index:
            index[project_name] = {}
        
        index[project_name].update(updates)
        self._save_projects_index(user_id, index)
    
    def _initialize_project_context(self, project_path: Path, project_name: str, 
                                   initial_description: str):
        """Initialize PROJECT_CONTEXT.md file"""
        context_file = project_path / "PROJECT_CONTEXT.md"
        
        # Format project name for display
        display_name = project_name.replace('_', ' ').title()
        
        content = f"""# Project: {display_name}

**Created:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Project Description

{initial_description}

## Project Goals

- {initial_description}

## Files in Project

_No files yet. Files will be added as the project develops._

## Task History

_No tasks yet. Task history will be added here._

## Code Architecture

_Code architecture will be documented as the project develops._

## Dependencies

_No dependencies yet. Dependencies will be added as needed._

## Next Steps

- Continue development based on project goals
"""
        
        try:
            with open(context_file, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Initialized PROJECT_CONTEXT.md for project '{project_name}'")
        except Exception as e:
            logger.error(f"Error initializing project context: {e}")
    
    def get_project_context(self, project_path: Path) -> Optional[str]:
        """Read existing PROJECT_CONTEXT.md"""
        context_file = project_path / "PROJECT_CONTEXT.md"
        if context_file.exists():
            try:
                with open(context_file, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Error reading project context: {e}")
        return None
    
    def update_project_context(self, project_path: Path, task_id: str, user_message: str,
                              generated_files: List[str], execution_results: List[str],
                              code_snippets: Optional[List[str]] = None,
                              key_decisions: Optional[List[str]] = None):
        """
        Update PROJECT_CONTEXT.md with new task information
        
        Args:
            project_path: Path to project directory
            task_id: Task identifier
            user_message: Original user message
            generated_files: List of generated file paths
            execution_results: List of execution result strings
            code_snippets: Optional list of code snippets to add
            key_decisions: Optional list of key decisions made
        """
        context_file = project_path / "PROJECT_CONTEXT.md"
        
        if not context_file.exists():
            # Initialize if doesn't exist
            project_name = project_path.name
            self._initialize_project_context(project_path, project_name, user_message)
        
        try:
            # Read existing context
            with open(context_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Update last updated timestamp
            content = re.sub(
                r'\*\*Last Updated:\*\* .+',
                f'**Last Updated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                content
            )
            
            # Add new task to Task History
            task_section = self._format_task_entry(task_id, user_message, generated_files, 
                                                   execution_results, code_snippets, key_decisions)
            
            # Find Task History section and append
            if "## Task History" in content:
                # Append after Task History header
                content = re.sub(
                    r'(## Task History\n)',
                    r'\1' + task_section + '\n',
                    content
                )
            else:
                # Add Task History section before Code Architecture
                task_history_section = f"\n## Task History\n\n{task_section}\n"
                if "## Code Architecture" in content:
                    content = content.replace("## Code Architecture", task_history_section + "\n## Code Architecture")
                else:
                    content += task_history_section
            
            # Update Files in Project section
            if generated_files:
                files_section = self._update_files_section(content, generated_files, project_path)
                if files_section:
                    # Replace Files in Project section
                    files_pattern = r'(## Files in Project\n)(.*?)(\n## )'
                    if re.search(files_pattern, content, re.DOTALL):
                        content = re.sub(files_pattern, r'\1' + files_section + r'\n\3', content, flags=re.DOTALL)
                    else:
                        # Insert before Task History
                        if "## Task History" in content:
                            content = content.replace("## Task History", 
                                                     f"## Files in Project\n\n{files_section}\n\n## Task History")
            
            # Update Code Architecture if code snippets provided
            if code_snippets:
                architecture_section = self._update_architecture_section(content, code_snippets)
                if architecture_section:
                    if "## Code Architecture" in content:
                        content = re.sub(
                            r'(## Code Architecture\n)(.*?)(\n## )',
                            r'\1' + architecture_section + r'\n\3',
                            content,
                            flags=re.DOTALL
                        )
                    else:
                        # Add before Dependencies
                        if "## Dependencies" in content:
                            content = content.replace("## Dependencies", 
                                                     f"## Code Architecture\n\n{architecture_section}\n\n## Dependencies")
                        else:
                            content += f"\n## Code Architecture\n\n{architecture_section}\n"
            
            # Update Dependencies if found in code
            if code_snippets:
                dependencies = self._extract_dependencies(code_snippets)
                if dependencies:
                    deps_section = self._update_dependencies_section(content, dependencies)
                    if deps_section:
                        if "## Dependencies" in content:
                            content = re.sub(
                                r'(## Dependencies\n)(.*?)(\n## |$)',
                                r'\1' + deps_section + r'\n\3',
                                content,
                                flags=re.DOTALL
                            )
                        else:
                            # Add before Next Steps
                            if "## Next Steps" in content:
                                content = content.replace("## Next Steps", 
                                                         f"## Dependencies\n\n{deps_section}\n\n## Next Steps")
                            else:
                                content += f"\n## Dependencies\n\n{deps_section}\n"
            
            # Write updated context
            with open(context_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"Updated PROJECT_CONTEXT.md for project '{project_path.name}'")
            
        except Exception as e:
            logger.error(f"Error updating project context: {e}", exc_info=True)
    
    def _format_task_entry(self, task_id: str, user_message: str, generated_files: List[str],
                          execution_results: List[str], code_snippets: Optional[List[str]],
                          key_decisions: Optional[List[str]]) -> str:
        """Format task entry for Task History section"""
        entry = f"### Task {task_id} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        entry += f"- **Request**: {user_message[:200]}\n"
        entry += f"- **Status**: ✅ Completed\n"
        
        if generated_files:
            file_names = [os.path.basename(f) for f in generated_files[:10]]
            entry += f"- **Files Created**: {', '.join(file_names)}\n"
            if len(generated_files) > 10:
                entry += f"  _(and {len(generated_files) - 10} more files)_\n"
        
        if key_decisions:
            entry += f"- **Key Decisions**:\n"
            for decision in key_decisions:
                entry += f"  - {decision}\n"
        
        if code_snippets:
            entry += f"- **Code Snippets**:\n"
            for i, snippet in enumerate(code_snippets[:3], 1):
                snippet_preview = snippet[:200].replace('\n', ' ')
                entry += f"  {i}. `{snippet_preview}...`\n"
        
        if execution_results:
            success_count = len([r for r in execution_results if '✅' in r or 'success' in r.lower()])
            entry += f"- **Execution Results**: {success_count}/{len(execution_results)} successful\n"
        
        return entry
    
    def _update_files_section(self, content: str, generated_files: List[str], 
                              project_path: Path) -> str:
        """Update Files in Project section"""
        files_section = ""
        
        for file_path in generated_files[:20]:  # Limit to 20 files
            file_name = os.path.basename(file_path)
            file_ext = Path(file_path).suffix.lower()
            
            # Determine file type
            file_type = "code"
            if file_ext == '.py':
                file_type = "Python"
            elif file_ext in ['.js', '.ts']:
                file_type = "JavaScript/TypeScript"
            elif file_ext in ['.md', '.txt']:
                file_type = "Documentation"
            elif file_ext in ['.json', '.yaml', '.yml']:
                file_type = "Configuration"
            
            # Get file size if exists
            if os.path.exists(file_path):
                try:
                    file_size = os.path.getsize(file_path)
                    size_str = f"{file_size} bytes"
                except:
                    size_str = "unknown size"
            else:
                size_str = "not found"
            
            files_section += f"### {file_name}\n"
            files_section += f"- **Type**: {file_type}\n"
            files_section += f"- **Size**: {size_str}\n"
            files_section += f"- **Last Modified**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        if len(generated_files) > 20:
            files_section += f"_... and {len(generated_files) - 20} more files_\n\n"
        
        return files_section
    
    def _update_architecture_section(self, content: str, code_snippets: List[str]) -> str:
        """Update Code Architecture section"""
        architecture = "### Key Components\n\n"
        
        # Extract class and function names
        classes = []
        functions = []
        
        for snippet in code_snippets:
            # Find classes
            class_matches = re.findall(r'class\s+(\w+)', snippet)
            classes.extend(class_matches)
            
            # Find functions
            func_matches = re.findall(r'def\s+(\w+)', snippet)
            functions.extend(func_matches)
        
        if classes:
            architecture += "**Classes:**\n"
            for cls in set(classes)[:10]:
                architecture += f"- `{cls}`\n"
            architecture += "\n"
        
        if functions:
            architecture += "**Functions:**\n"
            for func in set(functions)[:15]:
                architecture += f"- `{func}()`\n"
            architecture += "\n"
        
        return architecture
    
    def _extract_dependencies(self, code_snippets: List[str]) -> List[str]:
        """Extract dependencies from code snippets"""
        dependencies = set()
        
        for snippet in code_snippets:
            # Find import statements
            import_matches = re.findall(r'(?:from|import)\s+([\w.]+)', snippet)
            for imp in import_matches:
                # Filter out standard library
                if '.' not in imp or not imp.startswith(('os', 'sys', 'json', 're', 'datetime', 'pathlib')):
                    dependencies.add(imp.split('.')[0])
        
        return sorted(list(dependencies))
    
    def _update_dependencies_section(self, content: str, dependencies: List[str]) -> str:
        """Update Dependencies section"""
        deps_section = "### Python Packages\n\n"
        
        for dep in dependencies[:20]:
            deps_section += f"- `{dep}`\n"
        
        if len(dependencies) > 20:
            deps_section += f"\n_... and {len(dependencies) - 20} more_\n"
        
        return deps_section
    
    def cleanup_old_projects(self, user_id: int, retention_days: int = 3):
        """
        Remove projects older than retention_days
        
        Args:
            user_id: User ID
            retention_days: Number of days to retain projects (default: 3)
        """
        lock = self._get_lock(f"cleanup_{user_id}")
        
        with lock:
            projects_dir = self._get_projects_dir(user_id)
            if not projects_dir.exists():
                return
            
            index = self._load_projects_index(user_id)
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            projects_to_remove = []
            
            for project_name, project_info in list(index.items()):
                last_accessed_str = project_info.get('last_accessed', '')
                if last_accessed_str:
                    try:
                        last_accessed = datetime.fromisoformat(last_accessed_str)
                        if last_accessed < cutoff_date:
                            projects_to_remove.append(project_name)
                    except:
                        # If can't parse date, check directory modification time
                        project_path = projects_dir / project_name
                        if project_path.exists():
                            mod_time = datetime.fromtimestamp(project_path.stat().st_mtime)
                            if mod_time < cutoff_date:
                                projects_to_remove.append(project_name)
            
            # Remove old projects
            for project_name in projects_to_remove:
                project_path = projects_dir / project_name
                if project_path.exists():
                    try:
                        shutil.rmtree(project_path)
                        logger.info(f"Removed old project '{project_name}' for user {user_id}")
                    except Exception as e:
                        logger.error(f"Error removing project '{project_name}': {e}")
                
                # Remove from index
                if project_name in index:
                    del index[project_name]
                
                # Remove from memory systems
                if self.secure_memory:
                    try:
                        # Remove project memory if exists
                        pass  # Secure memory cleanup handled by its own retention
                    except:
                        pass
            
            # Save updated index
            self._save_projects_index(user_id, index)
            
            logger.info(f"Cleanup completed for user {user_id}: removed {len(projects_to_remove)} old projects")
    
    def store_project_memory(self, user_id: int, project_name: str, context: Dict):
        """Store project in memory systems"""
        if self.secure_memory:
            try:
                # Store project metadata
                self.secure_memory.store_context(user_id, {
                    'project_name': project_name,
                    'project_context': context,
                    'type': 'project'
                })
            except Exception as e:
                logger.warning(f"Error storing project memory: {e}")
        
        if self.vector_memory:
            try:
                # Store project context for semantic search
                context_text = json.dumps(context, ensure_ascii=False)
                self.vector_memory.store_memory(
                    user_id,
                    f"project:{project_name}",
                    context_text,
                    metadata={'project_name': project_name, 'type': 'project'}
                )
            except Exception as e:
                logger.warning(f"Error storing project in vector memory: {e}")
    
    def retrieve_project_memory(self, user_id: int, project_name: str) -> Optional[Dict]:
        """Retrieve project from memory systems"""
        if self.secure_memory:
            try:
                context = self.secure_memory.get_context(user_id)
                if context and context.get('project_name') == project_name:
                    return context.get('project_context')
            except Exception as e:
                logger.warning(f"Error retrieving project memory: {e}")
        
        return None
