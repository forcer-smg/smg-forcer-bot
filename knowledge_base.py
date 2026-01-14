# -*- coding: utf-8 -*-
"""
Knowledge Base - Centralized framework/pattern database
Stores and retrieves structured information about languages, frameworks, patterns, and best practices
"""

import os
import json
import re
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """Centralized knowledge base for frameworks, patterns, and best practices"""
    
    def __init__(self, workspace_root: Optional[str] = None):
        """
        Initialize knowledge base
        workspace_root: Directory for knowledge base storage
        """
        self.workspace_root = Path(workspace_root) if workspace_root else Path(os.getcwd())
        self.kb_dir = self.workspace_root / "knowledge_base"
        self.kb_dir.mkdir(exist_ok=True)
        
        # Knowledge categories
        self.categories = {
            'languages': self.kb_dir / 'languages.json',
            'frameworks': self.kb_dir / 'frameworks.json',
            'patterns': self.kb_dir / 'patterns.json',
            'security': self.kb_dir / 'security.json',
            'redteam': self.kb_dir / 'redteam.json',
            'errors': self.kb_dir / 'errors.json',
            'best_practices': self.kb_dir / 'best_practices.json'
        }
        
        # In-memory cache
        self.cache: Dict[str, Dict] = {}
        
        # Initialize default knowledge if files don't exist
        self._initialize_default_knowledge()
    
    def _initialize_default_knowledge(self):
        """Initialize default knowledge base entries"""
        # Languages
        if not self.categories['languages'].exists():
            self._save_category('languages', {
                'python': {
                    'name': 'Python',
                    'description': 'High-level programming language',
                    'common_imports': ['os', 'sys', 'json', 'requests', 'subprocess'],
                    'best_practices': [
                        'Use virtual environments',
                        'Follow PEP 8 style guide',
                        'Use type hints',
                        'Handle exceptions properly'
                    ],
                    'common_patterns': ['context managers', 'decorators', 'generators']
                },
                'javascript': {
                    'name': 'JavaScript',
                    'description': 'Dynamic programming language',
                    'common_imports': ['fs', 'path', 'http', 'express'],
                    'best_practices': [
                        'Use const/let instead of var',
                        'Use async/await for async operations',
                        'Handle errors with try/catch'
                    ]
                }
            })
        
        # Frameworks
        if not self.categories['frameworks'].exists():
            self._save_category('frameworks', {
                'django': {
                    'name': 'Django',
                    'description': 'Python web framework',
                    'common_patterns': ['MVC', 'ORM', 'middleware'],
                    'best_practices': [
                        'Use Django ORM for database operations',
                        'Follow Django project structure',
                        'Use Django REST framework for APIs'
                    ]
                },
                'flask': {
                    'name': 'Flask',
                    'description': 'Lightweight Python web framework',
                    'common_patterns': ['blueprints', 'decorators', 'context'],
                    'best_practices': [
                        'Use blueprints for modular apps',
                        'Use Flask-SQLAlchemy for database',
                        'Implement proper error handling'
                    ]
                },
                'react': {
                    'name': 'React',
                    'description': 'JavaScript UI library',
                    'common_patterns': ['components', 'hooks', 'state management'],
                    'best_practices': [
                        'Use functional components',
                        'Manage state with hooks',
                        'Use React Router for navigation'
                    ]
                }
            })
        
        # Security
        if not self.categories['security'].exists():
            self._save_category('security', {
                'authentication': {
                    'name': 'Authentication',
                    'best_practices': [
                        'Use strong password hashing (bcrypt, argon2)',
                        'Implement rate limiting',
                        'Use HTTPS for all connections',
                        'Store tokens securely'
                    ]
                },
                'authorization': {
                    'name': 'Authorization',
                    'best_practices': [
                        'Principle of least privilege',
                        'Validate permissions on server side',
                        'Use RBAC or ABAC models'
                    ]
                }
            })
        
        # RedTeam Techniques
        if not self.categories['redteam'].exists():
            self._save_category('redteam', {
                'reconnaissance': {
                    'name': 'Reconnaissance',
                    'techniques': ['subdomain enumeration', 'port scanning', 'OSINT'],
                    'tools': ['nmap', 'subfinder', 'amass']
                },
                'exploitation': {
                    'name': 'Exploitation',
                    'techniques': ['SQL injection', 'XSS', 'command injection'],
                    'tools': ['metasploit', 'sqlmap', 'burpsuite']
                }
            })
        
        # Common Errors
        if not self.categories['errors'].exists():
            self._save_category('errors', {
                'python': {
                    'ModuleNotFoundError': {
                        'solution': 'Install missing module: pip install <module>',
                        'common_causes': ['Module not installed', 'Virtual environment not activated']
                    },
                    'IndentationError': {
                        'solution': 'Check indentation consistency (use 4 spaces)',
                        'common_causes': ['Mixed tabs and spaces', 'Incorrect indentation level']
                    }
                }
            })
    
    def _load_category(self, category: str) -> Dict:
        """Load knowledge category from file"""
        if category in self.cache:
            return self.cache[category]
        
        file_path = self.categories.get(category)
        if not file_path or not file_path.exists():
            return {}
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.cache[category] = data
                return data
        except Exception as e:
            logger.error(f"Error loading category {category}: {e}")
            return {}
    
    def _save_category(self, category: str, data: Dict):
        """Save knowledge category to file"""
        file_path = self.categories.get(category)
        if not file_path:
            return
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.cache[category] = data
        except Exception as e:
            logger.error(f"Error saving category {category}: {e}")
    
    def add_knowledge(self, category: str, key: str, knowledge: Dict):
        """Add or update knowledge entry"""
        category_data = self._load_category(category)
        category_data[key] = {
            **knowledge,
            'updated_at': datetime.now().isoformat()
        }
        self._save_category(category, category_data)
        logger.info(f"Added knowledge: {category}/{key}")
    
    def get_knowledge(self, category: str, key: Optional[str] = None) -> Dict:
        """Get knowledge entry or entire category"""
        category_data = self._load_category(category)
        
        if key:
            return category_data.get(key, {})
        return category_data
    
    def search_knowledge(self, query: str, categories: Optional[List[str]] = None) -> List[Dict]:
        """Search knowledge base for relevant entries"""
        if categories is None:
            categories = list(self.categories.keys())
        
        results = []
        query_lower = query.lower()
        
        for category in categories:
            category_data = self._load_category(category)
            for key, entry in category_data.items():
                # Search in name, description, and content
                searchable_text = f"{key} {entry.get('name', '')} {entry.get('description', '')} {json.dumps(entry)}"
                if query_lower in searchable_text.lower():
                    results.append({
                        'category': category,
                        'key': key,
                        'entry': entry,
                        'relevance': self._calculate_relevance(query_lower, searchable_text.lower())
                    })
        
        # Sort by relevance
        results.sort(key=lambda x: x['relevance'], reverse=True)
        return results
    
    def _calculate_relevance(self, query: str, text: str) -> int:
        """Calculate relevance score"""
        score = 0
        query_words = query.split()
        
        for word in query_words:
            if word in text:
                score += text.count(word)
        
        # Boost if query appears in key/name
        if query in text[:50]:  # First 50 chars (likely key/name)
            score += 10
        
        return score
    
    def get_context_for_project(self, project_path: Optional[str] = None, 
                                file_extensions: Optional[List[str]] = None,
                                imports: Optional[List[str]] = None) -> str:
        """Get relevant knowledge based on project context"""
        context_parts = []
        
        # Detect language from file extensions
        if file_extensions:
            for ext in file_extensions:
                if ext == '.py':
                    py_knowledge = self.get_knowledge('languages', 'python')
                    if py_knowledge:
                        context_parts.append(f"Python: {py_knowledge.get('description', '')}")
                        if py_knowledge.get('best_practices'):
                            context_parts.append(f"Best practices: {', '.join(py_knowledge['best_practices'][:3])}")
                elif ext in ['.js', '.jsx', '.ts', '.tsx']:
                    js_knowledge = self.get_knowledge('languages', 'javascript')
                    if js_knowledge:
                        context_parts.append(f"JavaScript: {js_knowledge.get('description', '')}")
        
        # Detect frameworks from imports
        if imports:
            for imp in imports:
                imp_lower = imp.lower()
                if 'django' in imp_lower:
                    django_knowledge = self.get_knowledge('frameworks', 'django')
                    if django_knowledge:
                        context_parts.append(f"Django framework: {django_knowledge.get('description', '')}")
                elif 'flask' in imp_lower:
                    flask_knowledge = self.get_knowledge('frameworks', 'flask')
                    if flask_knowledge:
                        context_parts.append(f"Flask framework: {flask_knowledge.get('description', '')}")
                elif 'react' in imp_lower:
                    react_knowledge = self.get_knowledge('frameworks', 'react')
                    if react_knowledge:
                        context_parts.append(f"React framework: {react_knowledge.get('description', '')}")
        
        return "\n".join(context_parts) if context_parts else ""
    
    def get_error_solution(self, error_type: str, language: str = 'python') -> Optional[Dict]:
        """Get solution for common error"""
        errors = self.get_knowledge('errors', language)
        return errors.get(error_type)
    
    def get_security_best_practices(self, topic: str) -> List[str]:
        """Get security best practices for topic"""
        security = self.get_knowledge('security', topic)
        return security.get('best_practices', [])
    
    def get_redteam_techniques(self, category: str) -> Dict:
        """Get RedTeam techniques and tools"""
        return self.get_knowledge('redteam', category)
    
    def format_knowledge_for_prompt(self, knowledge_items: List[Dict], max_items: int = 5) -> str:
        """Format knowledge items for AI prompt injection"""
        if not knowledge_items:
            return ""
        
        formatted = ["[KNOWLEDGE BASE CONTEXT]"]
        
        for item in knowledge_items[:max_items]:
            category = item.get('category', '')
            key = item.get('key', '')
            entry = item.get('entry', {})
            
            formatted.append(f"\n{category.upper()}: {key}")
            if entry.get('description'):
                formatted.append(f"  Description: {entry['description']}")
            if entry.get('best_practices'):
                formatted.append(f"  Best Practices: {', '.join(entry['best_practices'][:3])}")
            if entry.get('tools'):
                formatted.append(f"  Tools: {', '.join(entry['tools'][:3])}")
        
        return "\n".join(formatted)
    
    def update_from_feedback(self, category: str, key: str, feedback: str):
        """Update knowledge based on user feedback"""
        entry = self.get_knowledge(category, key)
        if entry:
            if 'feedback' not in entry:
                entry['feedback'] = []
            entry['feedback'].append({
                'text': feedback,
                'timestamp': datetime.now().isoformat()
            })
            self.add_knowledge(category, key, entry)


# Global knowledge base instance
_kb_instance = None

def get_knowledge_base(workspace_root: Optional[str] = None) -> KnowledgeBase:
    """Get or create global knowledge base instance"""
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = KnowledgeBase(workspace_root)
    return _kb_instance
