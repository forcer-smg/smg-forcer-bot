# -*- coding: utf-8 -*-
"""
File Detector - Detects generated files in workspace and sends them to Telegram
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class FileDetector:
    """Detect newly generated files in workspace"""
    
    def __init__(self, workspace_path: str):
        """
        Initialize file detector
        
        Args:
            workspace_path: Workspace root path
        """
        self.workspace_path = Path(workspace_path)
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"FileDetector initialized for workspace: {self.workspace_path}")
    
    def detect_generated_files(self, 
                               since_minutes: int = 10,
                               extensions: Optional[List[str]] = None,
                               exclude_patterns: Optional[List[str]] = None) -> List[Dict[str, str]]:
        """
        Detect files generated in the last N minutes
        
        Args:
            since_minutes: How many minutes back to look
            extensions: File extensions to include (None = all)
            exclude_patterns: Patterns to exclude (e.g., ['__pycache__', '.pyc'])
        
        Returns:
            List of file dicts with 'path', 'name', 'size', 'modified' keys
        """
        if extensions is None:
            extensions = ['.py', '.sh', '.js', '.ts', '.html', '.css', '.json', '.txt', 
                         '.md', '.yaml', '.yml', '.xml', '.sql', '.go', '.rs', '.java',
                         '.cpp', '.c', '.php', '.rb', '.ps1', '.bat', '.cmd']
        
        if exclude_patterns is None:
            exclude_patterns = ['__pycache__', '.pyc', '.pyo', '.pyd', '.so', '.dll',
                               '.git', '.env', '.venv', 'venv', 'node_modules']
        
        cutoff_time = datetime.now() - timedelta(minutes=since_minutes)
        generated_files = []
        
        try:
            # Walk workspace recursively
            for root, dirs, files in os.walk(self.workspace_path):
                # Skip excluded directories
                dirs[:] = [d for d in dirs if not any(pattern in d for pattern in exclude_patterns)]
                
                for file in files:
                    file_path = Path(root) / file
                    
                    # Check extension
                    if file_path.suffix.lower() not in extensions:
                        continue
                    
                    # Check if excluded
                    if any(pattern in str(file_path) for pattern in exclude_patterns):
                        continue
                    
                    # Check modification time
                    try:
                        mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                        if mtime >= cutoff_time:
                            generated_files.append({
                                'path': str(file_path),
                                'name': file_path.name,
                                'size': file_path.stat().st_size,
                                'modified': mtime.isoformat(),
                                'relative_path': str(file_path.relative_to(self.workspace_path))
                            })
                    except Exception as e:
                        logger.debug(f"Error checking file {file_path}: {e}")
                        continue
            
            # Sort by modification time (newest first)
            generated_files.sort(key=lambda x: x['modified'], reverse=True)
            
            logger.info(f"Detected {len(generated_files)} generated files in last {since_minutes} minutes")
            return generated_files
            
        except Exception as e:
            logger.error(f"Error detecting files: {e}", exc_info=True)
            return []
    
    def detect_code_files(self, since_minutes: int = 10) -> List[Dict[str, str]]:
        """Detect code files specifically"""
        code_extensions = ['.py', '.sh', '.js', '.ts', '.html', '.css', '.json', 
                          '.go', '.rs', '.java', '.cpp', '.c', '.php', '.rb', '.ps1']
        return self.detect_generated_files(since_minutes=since_minutes, 
                                         extensions=code_extensions)
    
    def detect_output_files(self, since_minutes: int = 10) -> List[Dict[str, str]]:
        """Detect output files (txt, json, log, csv, etc.)"""
        output_extensions = ['.txt', '.json', '.log', '.csv', '.xml', '.yaml', '.yml', '.md']
        return self.detect_generated_files(since_minutes=since_minutes,
                                         extensions=output_extensions)


# Global instance cache
_file_detector_cache = {}

def get_file_detector(workspace_path: str) -> FileDetector:
    """Get or create file detector for workspace"""
    if workspace_path not in _file_detector_cache:
        _file_detector_cache[workspace_path] = FileDetector(workspace_path)
    return _file_detector_cache[workspace_path]
