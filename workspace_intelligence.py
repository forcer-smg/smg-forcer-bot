# -*- coding: utf-8 -*-
"""
Workspace Intelligence - Auto-detect existing projects and files before generation
Provides similarity detection, file existence checking, and project analysis
"""

import os
import re
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


def similarity_score(a: str, b: str) -> float:
    """Calculate similarity score between two strings (0.0 to 1.0)"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


class WorkspaceIntelligence:
    """Intelligent workspace scanning and project detection"""
    
    def __init__(self, workspace_root: str = None):
        """
        Initialize workspace intelligence
        
        Args:
            workspace_root: Root directory to scan (default: current directory)
        """
        self.workspace_root = Path(workspace_root) if workspace_root else Path.cwd()
        self.logger = logger
    
    def scan_workspace(self, workspace_path: str = None) -> Dict:
        """
        Scan workspace and return project structure
        
        Args:
            workspace_path: Path to scan (default: self.workspace_root)
        
        Returns:
            Dict with project structure information
        """
        scan_path = Path(workspace_path) if workspace_path else self.workspace_root
        
        if not scan_path.exists():
            return {
                'exists': False,
                'projects': [],
                'files': [],
                'total_size': 0
            }
        
        structure = {
            'exists': True,
            'path': str(scan_path),
            'projects': [],
            'files': [],
            'total_size': 0,
            'project_types': {}
        }
        
        try:
            # Scan for projects
            for item in scan_path.iterdir():
                if item.is_dir():
                    project_info = self._analyze_directory(item)
                    if project_info:
                        structure['projects'].append(project_info)
                        project_type = project_info.get('type', 'unknown')
                        structure['project_types'][project_type] = structure['project_types'].get(project_type, 0) + 1
                elif item.is_file():
                    file_info = {
                        'name': item.name,
                        'path': str(item),
                        'size': item.stat().st_size,
                        'type': self._detect_file_type(item)
                    }
                    structure['files'].append(file_info)
                    structure['total_size'] += file_info['size']
        except Exception as e:
            self.logger.error(f"Error scanning workspace {scan_path}: {e}")
        
        return structure
    
    def find_similar_projects(self, project_name: str, workspace_path: str = None, threshold: float = 0.6) -> List[Dict]:
        """
        Find similar projects by name/content
        
        Args:
            project_name: Name of project to search for
            workspace_path: Path to search (default: self.workspace_root)
            threshold: Similarity threshold (0.0 to 1.0)
        
        Returns:
            List of similar projects with similarity scores
        """
        scan_path = Path(workspace_path) if workspace_path else self.workspace_root
        
        if not scan_path.exists():
            return []
        
        similar_projects = []
        project_name_lower = project_name.lower()
        
        try:
            for item in scan_path.iterdir():
                if item.is_dir():
                    # Check directory name similarity
                    dir_name = item.name.lower()
                    name_score = similarity_score(project_name_lower, dir_name)
                    
                    # Check for README or main files that might indicate project type
                    readme_score = 0.0
                    main_file_score = 0.0
                    
                    for file in item.iterdir():
                        if file.is_file():
                            file_name_lower = file.name.lower()
                            if 'readme' in file_name_lower:
                                try:
                                    content = file.read_text(errors='ignore')[:500].lower()
                                    readme_score = similarity_score(project_name_lower, content)
                                except:
                                    pass
                            elif file.name in ['main.go', 'main.py', 'package.json', 'Cargo.toml', 'pom.xml']:
                                try:
                                    content = file.read_text(errors='ignore')[:500].lower()
                                    main_file_score = similarity_score(project_name_lower, content)
                                except:
                                    pass
                    
                    # Calculate overall similarity
                    overall_score = max(name_score, readme_score * 0.7, main_file_score * 0.7)
                    
                    if overall_score >= threshold:
                        project_info = self._analyze_directory(item)
                        if project_info:
                            project_info['similarity_score'] = overall_score
                            project_info['name_score'] = name_score
                            similar_projects.append(project_info)
        except Exception as e:
            self.logger.error(f"Error finding similar projects: {e}")
        
        # Sort by similarity score (highest first)
        similar_projects.sort(key=lambda x: x.get('similarity_score', 0), reverse=True)
        
        return similar_projects
    
    def check_file_exists(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Check if file exists and return content if available
        
        Args:
            file_path: Path to file (can be relative or absolute)
        
        Returns:
            Tuple of (exists: bool, content: Optional[str])
        """
        # Resolve path relative to workspace root if not absolute
        if not Path(file_path).is_absolute():
            file_path = self.workspace_root / file_path
        
        file_path = Path(file_path)
        
        if not file_path.exists() or not file_path.is_file():
            return False, None
        
        try:
            # Read file content (limit to first 10KB for large files)
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            if len(content) > 10000:
                content = content[:10000] + "\n... (truncated)"
            return True, content
        except Exception as e:
            self.logger.warning(f"Could not read file {file_path}: {e}")
            return True, None  # File exists but couldn't read
    
    def analyze_project_type(self, workspace_path: str = None) -> str:
        """
        Detect project type (Python, Go, Node.js, etc.)
        
        Args:
            workspace_path: Path to analyze (default: self.workspace_root)
        
        Returns:
            Project type string
        """
        scan_path = Path(workspace_path) if workspace_path else self.workspace_root
        
        if not scan_path.exists():
            return 'unknown'
        
        # Check for common project files
        indicators = {
            'python': ['requirements.txt', 'setup.py', 'pyproject.toml', 'Pipfile', 'main.py', '__init__.py'],
            'go': ['go.mod', 'go.sum', 'main.go', 'Gopkg.toml'],
            'nodejs': ['package.json', 'package-lock.json', 'yarn.lock', 'node_modules'],
            'rust': ['Cargo.toml', 'Cargo.lock', 'main.rs'],
            'java': ['pom.xml', 'build.gradle', 'build.xml', '.java'],
            'php': ['composer.json', 'composer.lock', 'index.php'],
            'ruby': ['Gemfile', 'Gemfile.lock', 'Rakefile'],
            'c': ['Makefile', 'CMakeLists.txt', '.c', '.h'],
            'cpp': ['CMakeLists.txt', '.cpp', '.hpp'],
        }
        
        found_types = {}
        
        try:
            for item in scan_path.rglob('*'):
                if item.is_file():
                    file_name = item.name.lower()
                    for lang, files in indicators.items():
                        if any(indicator in file_name or file_name.endswith(indicator) for indicator in files):
                            found_types[lang] = found_types.get(lang, 0) + 1
        except Exception as e:
            self.logger.debug(f"Error analyzing project type: {e}")
        
        if found_types:
            # Return most common type
            return max(found_types.items(), key=lambda x: x[1])[0]
        
        return 'unknown'
    
    def _analyze_directory(self, directory: Path) -> Optional[Dict]:
        """Analyze a directory to determine if it's a project"""
        if not directory.is_dir():
            return None
        
        project_info = {
            'name': directory.name,
            'path': str(directory),
            'type': 'unknown',
            'files': [],
            'size': 0
        }
        
        try:
            # Detect project type
            project_info['type'] = self.analyze_project_type(str(directory))
            
            # Count files and calculate size
            file_count = 0
            for item in directory.rglob('*'):
                if item.is_file():
                    file_count += 1
                    try:
                        project_info['size'] += item.stat().st_size
                    except:
                        pass
            
            project_info['file_count'] = file_count
            
            # Check for common project files
            common_files = ['README.md', 'LICENSE', '.git', 'Dockerfile', 'docker-compose.yml']
            for common_file in common_files:
                if (directory / common_file).exists() or (directory / f".{common_file}").exists():
                    project_info.setdefault('has_common_files', []).append(common_file)
            
        except Exception as e:
            self.logger.debug(f"Error analyzing directory {directory}: {e}")
        
        return project_info
    
    def _detect_file_type(self, file_path: Path) -> str:
        """Detect file type from extension"""
        ext = file_path.suffix.lower()
        
        type_map = {
            '.py': 'python',
            '.go': 'go',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.java': 'java',
            '.rs': 'rust',
            '.php': 'php',
            '.rb': 'ruby',
            '.c': 'c',
            '.cpp': 'cpp',
            '.h': 'header',
            '.hpp': 'header',
            '.md': 'markdown',
            '.txt': 'text',
            '.json': 'json',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.xml': 'xml',
            '.html': 'html',
            '.css': 'css',
            '.sh': 'bash',
            '.bat': 'batch',
            '.ps1': 'powershell',
        }
        
        return type_map.get(ext, 'unknown')


# Global instance
_workspace_intelligence_instance = None

def get_workspace_intelligence(workspace_root: str = None) -> WorkspaceIntelligence:
    """Get or create global workspace intelligence instance"""
    global _workspace_intelligence_instance
    if _workspace_intelligence_instance is None or workspace_root:
        _workspace_intelligence_instance = WorkspaceIntelligence(workspace_root)
    return _workspace_intelligence_instance
