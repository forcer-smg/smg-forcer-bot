# -*- coding: utf-8 -*-
"""
Code Validator - LSP-based code validation for multiple languages
Validates syntax, types, and code quality before execution
"""

import os
import json
import subprocess
import logging
import tempfile
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import re

logger = logging.getLogger(__name__)


class CodeValidator:
    """Validate code using Language Server Protocol (LSP)"""
    
    def __init__(self, config_path: str = None):
        """
        Initialize code validator
        
        Args:
            config_path: Path to LSP configuration file
        """
        self.config_path = config_path or os.path.join(os.path.dirname(__file__), 'lsp_config.json')
        self.config = self._load_config()
        self.lsp_clients = {}  # language -> LSP process
        self.lsp_available = {}  # language -> bool
        self._check_lsp_availability()
        
        logger.info(f"Code Validator initialized with {len([l for l, avail in self.lsp_available.items() if avail])} LSP servers available")
    
    def _load_config(self) -> Dict:
        """Load LSP configuration from JSON file"""
        default_config = {
            "languages": {
                "python": {
                    "lsp_server": "pylsp",
                    "command": ["pylsp"],
                    "enabled": True
                },
                "bash": {
                    "lsp_server": "bash-language-server",
                    "command": ["bash-language-server", "start"],
                    "enabled": True
                },
                "javascript": {
                    "lsp_server": "typescript-language-server",
                    "command": ["typescript-language-server", "--stdio"],
                    "enabled": True
                },
                "typescript": {
                    "lsp_server": "typescript-language-server",
                    "command": ["typescript-language-server", "--stdio"],
                    "enabled": True
                }
            },
            "validation": {
                "auto_fix": True,
                "max_fix_attempts": 3,
                "strict_mode": False
            },
            "testing": {
                "generate_tests": True,
                "run_tests": True,
                "fail_on_test_failure": False
            }
        }
        
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    user_config = json.load(f)
                    # Merge with defaults
                    default_config.update(user_config)
                    return default_config
            except Exception as e:
                logger.warning(f"Failed to load LSP config from {self.config_path}: {e}. Using defaults.")
        
        return default_config
    
    def _check_lsp_availability(self):
        """Check which LSP servers are available"""
        for lang, lang_config in self.config.get("languages", {}).items():
            if not lang_config.get("enabled", True):
                self.lsp_available[lang] = False
                continue
            
            command = lang_config.get("command", [])
            if not command:
                self.lsp_available[lang] = False
                continue
            
            # Check if command exists
            try:
                result = subprocess.run(
                    ["which", command[0]] if os.name != 'nt' else ["where", command[0]],
                    capture_output=True,
                    timeout=2
                )
                self.lsp_available[lang] = result.returncode == 0
            except Exception:
                # Try direct execution check
                try:
                    result = subprocess.run(
                        command + ["--version"] if "--version" not in command else command[:1] + ["--version"],
                        capture_output=True,
                        timeout=2
                    )
                    self.lsp_available[lang] = True
                except Exception:
                    self.lsp_available[lang] = False
        
        logger.info(f"LSP availability: {self.lsp_available}")
    
    def detect_language(self, code: str, hint: str = None) -> str:
        """
        Detect programming language from code or hint
        
        Args:
            code: Code content
            hint: Language hint (e.g., 'python', 'bash')
        
        Returns:
            Detected language
        """
        if hint:
            hint_lower = hint.lower()
            # Normalize language names
            lang_map = {
                'py': 'python',
                'python3': 'python',
                'sh': 'bash',
                'shell': 'bash',
                'zsh': 'bash',
                'js': 'javascript',
                'ts': 'typescript',
                'go': 'go',
                'rs': 'rust',
                'php': 'php',
                'rb': 'ruby',
                'sql': 'sql',
                'ps1': 'powershell',
                'cpp': 'cpp',
                'c': 'c'
            }
            if hint_lower in lang_map:
                return lang_map[hint_lower]
            if hint_lower in self.config.get("languages", {}):
                return hint_lower
        
        # Heuristic detection from code
        code_lower = code.lower().strip()
        
        # Python indicators
        if any(pattern in code for pattern in ['import ', 'from ', 'def ', 'class ', 'print(', '__main__']):
            if '#!/usr/bin/env python' in code or '#!/usr/bin/python' in code:
                return 'python'
            if re.search(r'\bdef\s+\w+\s*\(', code) or re.search(r'\bimport\s+\w+', code):
                return 'python'
        
        # Bash indicators
        if code.startswith('#!/bin/bash') or code.startswith('#!/bin/sh'):
            return 'bash'
        if any(pattern in code for pattern in ['$', 'echo ', 'if [', 'for ', 'while [']):
            if '#!/' in code[:20]:
                return 'bash'
        
        # JavaScript indicators
        if any(pattern in code for pattern in ['function ', 'const ', 'let ', 'var ', 'require(', 'module.exports']):
            return 'javascript'
        
        # Go indicators
        if 'package main' in code or 'func main()' in code:
            return 'go'
        
        # Rust indicators
        if 'fn main()' in code or 'use ' in code and '::' in code:
            return 'rust'
        
        # PHP indicators
        if code.startswith('<?php') or '<?=' in code:
            return 'php'
        
        # SQL indicators
        if any(pattern in code.upper() for pattern in ['SELECT ', 'INSERT ', 'UPDATE ', 'DELETE ', 'CREATE TABLE']):
            return 'sql'
        
        # Default to bash for shell-like code
        return 'bash'
    
    def validate_code(self, code: str, language: str = None) -> Dict[str, Any]:
        """
        Validate code using appropriate LSP server
        
        Args:
            code: Code to validate
            language: Language hint (auto-detected if not provided)
        
        Returns:
            Dictionary with validation results:
            - valid: bool
            - errors: List of error dictionaries
            - warnings: List of warning dictionaries
            - diagnostics: Full LSP diagnostics
        """
        if not language:
            language = self.detect_language(code)
        
        result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'diagnostics': [],
            'language': language,
            'lsp_available': self.lsp_available.get(language, False)
        }
        
        # If LSP not available, use basic validation
        if not result['lsp_available']:
            logger.debug(f"LSP not available for {language}, using basic validation")
            return self._basic_validation(code, language)
        
        # Use LSP for validation
        try:
            diagnostics = self._validate_with_lsp(code, language)
            result['diagnostics'] = diagnostics
            
            # Categorize diagnostics
            for diag in diagnostics:
                severity = diag.get('severity', 1)
                if severity == 1:  # Error
                    result['errors'].append(diag)
                    result['valid'] = False
                elif severity == 2:  # Warning
                    result['warnings'].append(diag)
            
        except Exception as e:
            logger.warning(f"LSP validation failed for {language}: {e}. Falling back to basic validation.")
            return self._basic_validation(code, language)
        
        return result
    
    def _basic_validation(self, code: str, language: str) -> Dict[str, Any]:
        """Basic validation without LSP (syntax checking)"""
        result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'diagnostics': [],
            'language': language,
            'lsp_available': False
        }
        
        if language == 'python':
            # Try Python syntax check
            try:
                compile(code, '<string>', 'exec')
            except SyntaxError as e:
                result['valid'] = False
                result['errors'].append({
                    'message': str(e),
                    'line': e.lineno or 0,
                    'column': e.offset or 0,
                    'severity': 1
                })
        
        elif language == 'bash':
            # Try bash syntax check
            try:
                result_check = subprocess.run(
                    ['bash', '-n'],
                    input=code,
                    text=True,
                    capture_output=True,
                    timeout=5
                )
                if result_check.returncode != 0:
                    result['valid'] = False
                    result['errors'].append({
                        'message': result_check.stderr,
                        'line': 0,
                        'column': 0,
                        'severity': 1
                    })
            except Exception as e:
                logger.debug(f"Bash syntax check failed: {e}")
        
        return result
    
    def _validate_with_lsp(self, code: str, language: str) -> List[Dict]:
        """
        Validate code using LSP server
        
        Args:
            code: Code to validate
            language: Language
        
        Returns:
            List of diagnostic dictionaries
        """
        # For now, use basic validation
        # Full LSP implementation would require LSP client library and proper protocol handling
        # This is a simplified version that can be enhanced later
        
        lang_config = self.config.get("languages", {}).get(language, {})
        if not lang_config.get("enabled", True):
            return []
        
        # Use basic validation as fallback
        # TODO: Implement full LSP client communication
        return self._basic_validation(code, language).get('errors', [])
    
    def auto_fix_code(self, code: str, language: str, diagnostics: List[Dict] = None) -> Tuple[str, bool]:
        """
        Attempt to auto-fix common errors
        
        Args:
            code: Code to fix
            language: Language
            diagnostics: LSP diagnostics (optional, will validate if not provided)
        
        Returns:
            Tuple of (fixed_code, was_fixed)
        """
        if diagnostics is None:
            validation_result = self.validate_code(code, language)
            diagnostics = validation_result.get('errors', [])
        
        if not diagnostics:
            return code, False
        
        fixed_code = code
        was_fixed = False
        
        # Auto-fix common errors
        for diag in diagnostics:
            message = diag.get('message', '').lower()
            line = diag.get('line', 0)
            
            # Python fixes
            if language == 'python':
                # Missing colon
                if 'expected \':\'' in message or 'invalid syntax' in message:
                    lines = fixed_code.split('\n')
                    if line < len(lines):
                        line_content = lines[line]
                        if line_content.strip() and not line_content.rstrip().endswith(':'):
                            if any(keyword in line_content for keyword in ['def ', 'class ', 'if ', 'for ', 'while ', 'elif ', 'else']):
                                lines[line] = line_content.rstrip() + ':'
                                fixed_code = '\n'.join(lines)
                                was_fixed = True
                
                # Missing import
                if 'undefined name' in message or 'name \'' in message and 'is not defined' in message:
                    # Extract undefined name
                    match = re.search(r"name '(\w+)'", message)
                    if match:
                        undefined_name = match.group(1)
                        # Try to add common imports
                        if undefined_name in ['os', 'sys', 'json', 'time', 'datetime']:
                            if f'import {undefined_name}' not in fixed_code:
                                fixed_code = f'import {undefined_name}\n' + fixed_code
                                was_fixed = True
            
            # Bash fixes
            elif language == 'bash':
                # Missing shebang
                if not fixed_code.startswith('#!/'):
                    fixed_code = '#!/bin/bash\n' + fixed_code
                    was_fixed = True
                
                # Unclosed quotes
                if 'unexpected end of file' in message or 'unterminated quoted string' in message:
                    quote_count = fixed_code.count('"') - fixed_code.count('\\"')
                    if quote_count % 2 != 0:
                        fixed_code = fixed_code.rstrip() + '"'
                        was_fixed = True
        
        return fixed_code, was_fixed
    
    def get_code_quality_metrics(self, code: str, language: str) -> Dict[str, Any]:
        """
        Get code quality metrics
        
        Args:
            code: Code to analyze
            language: Language
        
        Returns:
            Dictionary with quality metrics
        """
        metrics = {
            'lines_of_code': len(code.split('\n')),
            'complexity': 'low',  # TODO: Implement complexity analysis
            'security_issues': [],
            'performance_issues': [],
            'best_practices': []
        }
        
        # Basic security checks
        if language == 'python':
            # Check for dangerous patterns
            dangerous_patterns = [
                (r'eval\(', 'Use of eval() is dangerous'),
                (r'exec\(', 'Use of exec() is dangerous'),
                (r'__import__\(', 'Dynamic imports can be dangerous'),
                (r'subprocess\.call\(.*shell=True', 'Shell injection risk'),
            ]
            
            for pattern, message in dangerous_patterns:
                if re.search(pattern, code):
                    metrics['security_issues'].append({
                        'severity': 'high',
                        'message': message,
                        'pattern': pattern
                    })
        
        elif language == 'bash':
            # Check for unquoted variables
            if re.search(r'\$\w+[^"]', code):
                metrics['security_issues'].append({
                    'severity': 'medium',
                    'message': 'Unquoted variables can cause word splitting',
                    'pattern': r'\$\w+'
                })
        
        return metrics


# Global instance
_code_validator_instance = None

def get_code_validator(config_path: str = None) -> CodeValidator:
    """Get or create global code validator instance"""
    global _code_validator_instance
    if _code_validator_instance is None:
        _code_validator_instance = CodeValidator(config_path)
    return _code_validator_instance
