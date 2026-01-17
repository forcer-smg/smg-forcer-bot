# -*- coding: utf-8 -*-
"""
RAG (Retrieval Augmented Generation) System for Continuous Learning
Stores successful task executions, solutions, and patterns for future reference
"""

import os
import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import re

logger = logging.getLogger(__name__)


class RAGSystem:
    """Retrieval Augmented Generation system for continuous learning"""
    
    def __init__(self, base_dir: str = "/app/rag_knowledge_base"):
        """
        Initialize RAG system
        
        Args:
            base_dir: Base directory for storing knowledge base
        """
        self.base_dir = Path(base_dir)
        self.knowledge_dir = self.base_dir / "knowledge"
        self.solutions_dir = self.base_dir / "solutions"
        self.patterns_dir = self.base_dir / "patterns"
        self.index_file = self.base_dir / "index.json"
        
        # Create directories
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.solutions_dir.mkdir(parents=True, exist_ok=True)
        self.patterns_dir.mkdir(parents=True, exist_ok=True)
        
        # Load index
        self.index = self._load_index()
    
    def _load_index(self) -> Dict:
        """Load knowledge base index"""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading RAG index: {e}")
                return {"knowledge": [], "solutions": [], "patterns": []}
        return {"knowledge": [], "solutions": [], "patterns": []}
    
    def _save_index(self):
        """Save knowledge base index"""
        try:
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(self.index, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving RAG index: {e}")
    
    def store_successful_task(self, 
                             task_description: str,
                             solution: str,
                             commands_executed: List[str],
                             files_generated: List[str],
                             execution_results: List[str],
                             metadata: Optional[Dict] = None) -> str:
        """
        Store a successful task execution for future reference
        
        Args:
            task_description: Original task description
            solution: Solution/approach used
            commands_executed: List of commands that were executed
            files_generated: List of files that were generated
            execution_results: Execution results/outputs
            metadata: Additional metadata (user_id, timestamp, etc.)
        
        Returns:
            Knowledge entry ID
        """
        # Generate unique ID
        task_hash = hashlib.md5(task_description.encode()).hexdigest()[:12]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        entry_id = f"{task_hash}_{timestamp}"
        
        # Create knowledge entry
        entry = {
            "id": entry_id,
            "task_description": task_description,
            "solution": solution,
            "commands_executed": commands_executed,
            "files_generated": files_generated,
            "execution_results": execution_results,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat(),
            "success": True
        }
        
        # Save to file
        entry_file = self.knowledge_dir / f"{entry_id}.json"
        try:
            with open(entry_file, 'w', encoding='utf-8') as f:
                json.dump(entry, f, indent=2, ensure_ascii=False)
            
            # Update index
            self.index["knowledge"].append({
                "id": entry_id,
                "task_description": task_description[:200],  # Truncate for index
                "timestamp": entry["timestamp"],
                "tags": self._extract_tags(task_description)
            })
            self._save_index()
            
            logger.info(f"Stored successful task in RAG: {entry_id}")
            return entry_id
        except Exception as e:
            logger.error(f"Error storing task in RAG: {e}")
            return ""
    
    def store_solution_pattern(self,
                              problem_type: str,
                              solution_pattern: str,
                              commands: List[str],
                              context: Optional[Dict] = None) -> str:
        """
        Store a solution pattern for common problems
        
        Args:
            problem_type: Type of problem (e.g., "package_not_found", "git_clone_failed")
            solution_pattern: Pattern/solution for this problem
            commands: Commands that solve this problem
            context: Additional context
        
        Returns:
            Pattern ID
        """
        pattern_id = hashlib.md5(f"{problem_type}_{solution_pattern}".encode()).hexdigest()[:12]
        
        pattern = {
            "id": pattern_id,
            "problem_type": problem_type,
            "solution_pattern": solution_pattern,
            "commands": commands,
            "context": context or {},
            "timestamp": datetime.now().isoformat(),
            "usage_count": 0
        }
        
        # Save pattern
        pattern_file = self.patterns_dir / f"{pattern_id}.json"
        try:
            with open(pattern_file, 'w', encoding='utf-8') as f:
                json.dump(pattern, f, indent=2, ensure_ascii=False)
            
            # Update index
            self.index["patterns"].append({
                "id": pattern_id,
                "problem_type": problem_type,
                "timestamp": pattern["timestamp"]
            })
            self._save_index()
            
            logger.info(f"Stored solution pattern in RAG: {pattern_id}")
            return pattern_id
        except Exception as e:
            logger.error(f"Error storing pattern in RAG: {e}")
            return ""
    
    def retrieve_relevant_knowledge(self, 
                                   query: str,
                                   max_results: int = 5,
                                   min_similarity: float = 0.3) -> List[Dict]:
        """
        Retrieve relevant knowledge entries for a given query
        
        Args:
            query: Search query
            max_results: Maximum number of results to return
            min_similarity: Minimum similarity threshold
        
        Returns:
            List of relevant knowledge entries
        """
        query_lower = query.lower()
        query_words = set(re.findall(r'\w+', query_lower))
        
        results = []
        
        # Search through knowledge entries
        for entry_info in self.index.get("knowledge", []):
            entry_id = entry_info["id"]
            entry_file = self.knowledge_dir / f"{entry_id}.json"
            
            if not entry_file.exists():
                continue
            
            try:
                with open(entry_file, 'r', encoding='utf-8') as f:
                    entry = json.load(f)
                
                # Calculate similarity
                task_desc = entry.get("task_description", "").lower()
                task_words = set(re.findall(r'\w+', task_desc))
                
                # Simple word overlap similarity
                if query_words:
                    overlap = len(query_words & task_words) / len(query_words)
                else:
                    overlap = 0
                
                if overlap >= min_similarity:
                    results.append({
                        "entry": entry,
                        "similarity": overlap,
                        "type": "knowledge"
                    })
            except Exception as e:
                logger.warning(f"Error reading knowledge entry {entry_id}: {e}")
        
        # Search through solution patterns
        for pattern_info in self.index.get("patterns", []):
            pattern_id = pattern_info["id"]
            pattern_file = self.patterns_dir / f"{pattern_id}.json"
            
            if not pattern_file.exists():
                continue
            
            try:
                with open(pattern_file, 'r', encoding='utf-8') as f:
                    pattern = json.load(f)
                
                # Check if query matches problem type
                problem_type = pattern.get("problem_type", "").lower()
                if problem_type in query_lower or any(word in problem_type for word in query_words):
                    results.append({
                        "entry": pattern,
                        "similarity": 0.8,  # High similarity for pattern matches
                        "type": "pattern"
                    })
            except Exception as e:
                logger.warning(f"Error reading pattern {pattern_id}: {e}")
        
        # Sort by similarity and return top results
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:max_results]
    
    def get_solution_for_error(self, error_message: str) -> Optional[Dict]:
        """
        Get solution pattern for a specific error
        
        Args:
            error_message: Error message to find solution for
        
        Returns:
            Solution pattern if found, None otherwise
        """
        error_lower = error_message.lower()
        
        # Common error patterns
        error_patterns = {
            "package.*not.*available|has no installation candidate": {
                "problem_type": "package_not_found",
                "solution": "Try alternative package name or version",
                "commands": ["apt-cache search <package>", "apt-get install <alternative>"]
            },
            "module not found|no module named": {
                "problem_type": "module_not_found",
                "solution": "Install missing Python module",
                "commands": ["pip install <module>"]
            },
            "git clone.*fatal": {
                "problem_type": "git_clone_failed",
                "solution": "Check repository URL or use alternative method",
                "commands": ["git clone <url>", "wget <url>/archive/refs/heads/main.zip"]
            },
            "file not found|no such file": {
                "problem_type": "file_not_found",
                "solution": "Check file path or create file",
                "commands": ["ls -la <path>", "mkdir -p <dir>"]
            }
        }
        
        # Check if error matches any pattern
        for pattern, solution in error_patterns.items():
            if re.search(pattern, error_lower):
                return solution
        
        # Search in stored patterns
        for pattern_info in self.index.get("patterns", []):
            pattern_id = pattern_info["id"]
            pattern_file = self.patterns_dir / f"{pattern_id}.json"
            
            if pattern_file.exists():
                try:
                    with open(pattern_file, 'r', encoding='utf-8') as f:
                        pattern = json.load(f)
                    
                    problem_type = pattern.get("problem_type", "").lower()
                    if problem_type in error_lower:
                        return {
                            "problem_type": pattern.get("problem_type"),
                            "solution": pattern.get("solution_pattern"),
                            "commands": pattern.get("commands", [])
                        }
                except Exception as e:
                    logger.warning(f"Error reading pattern {pattern_id}: {e}")
        
        return None
    
    def _extract_tags(self, text: str) -> List[str]:
        """Extract tags from text for indexing"""
        # Simple tag extraction - can be improved
        tags = []
        text_lower = text.lower()
        
        # Common tags
        common_tags = {
            "install": ["install", "setup", "configure"],
            "scan": ["scan", "recon", "enumeration"],
            "exploit": ["exploit", "vulnerability", "attack"],
            "code": ["code", "script", "generate"],
            "error": ["error", "fix", "debug"]
        }
        
        for tag, keywords in common_tags.items():
            if any(keyword in text_lower for keyword in keywords):
                tags.append(tag)
        
        return tags
    
    def format_knowledge_for_prompt(self, knowledge_entries: List[Dict]) -> str:
        """
        Format retrieved knowledge for inclusion in AI prompt
        
        Args:
            knowledge_entries: List of knowledge entries from retrieve_relevant_knowledge
        
        Returns:
            Formatted string for prompt
        """
        if not knowledge_entries:
            return ""
        
        formatted = "\n\n## 📚 RELEVANT PAST SOLUTIONS (RAG):\n\n"
        
        for i, item in enumerate(knowledge_entries, 1):
            entry = item["entry"]
            entry_type = item["type"]
            similarity = item["similarity"]
            
            if entry_type == "knowledge":
                formatted += f"**Solution {i}** (Similarity: {similarity:.0%}):\n"
                formatted += f"- Task: {entry.get('task_description', '')[:150]}\n"
                formatted += f"- Solution: {entry.get('solution', '')[:200]}\n"
                
                # Include successful commands
                commands = entry.get('commands_executed', [])[:5]
                if commands:
                    formatted += f"- Successful Commands:\n"
                    for cmd in commands:
                        formatted += f"  - `{cmd[:100]}`\n"
            else:  # pattern
                formatted += f"**Pattern {i}** (Problem Type: {entry.get('problem_type', '')}):\n"
                formatted += f"- Solution: {entry.get('solution_pattern', '')}\n"
                commands = entry.get('commands', [])[:3]
                if commands:
                    formatted += f"- Commands:\n"
                    for cmd in commands:
                        formatted += f"  - `{cmd}`\n"
            
            formatted += "\n"
        
        formatted += "**Use these past solutions as reference, but adapt them to the current task.**\n"
        
        return formatted
