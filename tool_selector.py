# -*- coding: utf-8 -*-
"""
Tool Selector - Enhanced intelligent tool selection with verification
Selects best tool based on relevance, success rate, verification confidence, and execution reliability
"""

import os
import json
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class ToolSelector:
    """Enhanced tool selection with verification and success tracking"""
    
    def __init__(self, workspace_root: Optional[str] = None):
        """
        Initialize tool selector
        workspace_root: Workspace directory for tool metrics storage
        """
        self.workspace_root = Path(workspace_root) if workspace_root else Path(os.getcwd())
        self.metrics_dir = self.workspace_root / "tool_metrics"
        self.metrics_dir.mkdir(exist_ok=True)
        
        self.metrics_file = self.metrics_dir / "tool_metrics.json"
        self.tool_metrics: Dict[str, Dict] = {}
        
        self._load_metrics()
    
    def _load_metrics(self):
        """Load tool metrics from file"""
        if self.metrics_file.exists():
            try:
                with open(self.metrics_file, 'r') as f:
                    self.tool_metrics = json.load(f)
            except Exception as e:
                logger.error(f"Error loading tool metrics: {e}")
                self.tool_metrics = {}
    
    def _save_metrics(self):
        """Save tool metrics to file"""
        try:
            with open(self.metrics_file, 'w') as f:
                json.dump(self.tool_metrics, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving tool metrics: {e}")
    
    def update_tool_metrics(self, tool_name: str, execution_result: Dict, verification: Dict):
        """Update metrics for a tool based on execution and verification"""
        if tool_name not in self.tool_metrics:
            self.tool_metrics[tool_name] = {
                'total_executions': 0,
                'successful_executions': 0,
                'failed_executions': 0,
                'verified_executions': 0,
                'false_positives': 0,
                'total_confidence': 0.0,
                'average_execution_time': 0.0,
                'last_execution': None
            }
        
        metrics = self.tool_metrics[tool_name]
        metrics['total_executions'] += 1
        metrics['last_execution'] = datetime.now().isoformat()
        
        # Update success/failure counts
        if execution_result.get('exit_code') == 0:
            metrics['successful_executions'] += 1
        else:
            metrics['failed_executions'] += 1
        
        # Update verification metrics
        if verification.get('verified'):
            metrics['verified_executions'] += 1
        
        if verification.get('is_false_positive'):
            metrics['false_positives'] += 1
        
        # Update confidence average
        confidence = verification.get('confidence', 0.0)
        total_confidence = metrics['total_confidence']
        total_executions = metrics['total_executions']
        metrics['total_confidence'] = (total_confidence * (total_executions - 1) + confidence) / total_executions
        
        # Update execution time average
        exec_time = execution_result.get('execution_time', 0)
        avg_time = metrics['average_execution_time']
        metrics['average_execution_time'] = (avg_time * (total_executions - 1) + exec_time) / total_executions
        
        self._save_metrics()
    
    def get_tool_metrics(self, tool_name: str) -> Dict:
        """Get metrics for a tool"""
        return self.tool_metrics.get(tool_name, {
            'total_executions': 0,
            'successful_executions': 0,
            'failed_executions': 0,
            'verified_executions': 0,
            'false_positives': 0,
            'total_confidence': 0.0,
            'average_execution_time': 0.0
        })
    
    def calculate_tool_score(self, tool: Dict, task: str, execution_monitor=None) -> float:
        """
        Calculate score for a tool based on multiple factors
        Returns score from 0.0 to 1.0
        """
        # 1. Relevance score (0.4 weight)
        relevance_score = self._calculate_relevance_score(tool, task)
        
        # 2. Success rate (0.3 weight)
        success_rate = self._calculate_success_rate(tool, execution_monitor)
        
        # 3. Verification confidence (0.2 weight)
        verification_confidence = self._calculate_verification_confidence(tool)
        
        # 4. Execution reliability (0.1 weight)
        execution_reliability = self._calculate_execution_reliability(tool, execution_monitor)
        
        # Combined score
        tool_score = (
            relevance_score * 0.4 +
            success_rate * 0.3 +
            verification_confidence * 0.2 +
            execution_reliability * 0.1
        )
        
        return tool_score
    
    def _calculate_relevance_score(self, tool: Dict, task: str) -> float:
        """Calculate how relevant tool is to task (0.0 to 1.0)"""
        task_lower = task.lower()
        tool_name = tool.get('name', '').lower()
        tool_desc = tool.get('description', '').lower()
        tool_category = tool.get('category', '').lower()
        
        score = 0.0
        
        # Exact name match
        if tool_name in task_lower or task_lower in tool_name:
            score = 1.0
            return score
        
        # Name word match
        tool_words = tool_name.split()
        task_words = task_lower.split()
        matching_words = sum(1 for word in tool_words if word in task_words and len(word) > 3)
        if tool_words:
            score += (matching_words / len(tool_words)) * 0.5
        
        # Description match
        desc_words = tool_desc.split()
        matching_desc_words = sum(1 for word in desc_words if word in task_lower and len(word) > 3)
        if desc_words:
            score += (matching_desc_words / len(desc_words)) * 0.3
        
        # Category match
        category_keywords = {
            'reconnaissance': ['scan', 'recon', 'discover', 'enumerate', 'find', 'subdomain'],
            'exploitation': ['exploit', 'attack', 'breach', 'hack', 'vulnerability'],
            'web_testing': ['web', 'website', 'http', 'browser', 'xss', 'sql', 'csrf'],
            'credential_access': ['password', 'hash', 'crack', 'brute', 'login'],
            'vulnerability_scanning': ['vulnerability', 'vuln', 'cve', 'scan', 'test']
        }
        
        if tool_category in category_keywords:
            for keyword in category_keywords[tool_category]:
                if keyword in task_lower:
                    score += 0.2
                    break
        
        return min(score, 1.0)
    
    def _calculate_success_rate(self, tool: Dict, execution_monitor=None) -> float:
        """Calculate historical success rate (0.0 to 1.0)"""
        tool_name = tool.get('name', '')
        
        # Get metrics from our tracking
        metrics = self.get_tool_metrics(tool_name)
        if metrics['total_executions'] > 0:
            success_rate = metrics['successful_executions'] / metrics['total_executions']
            return success_rate
        
        # Try execution monitor if available
        if execution_monitor:
            try:
                success_rate = execution_monitor.get_tool_success_rate(tool_name)
                return success_rate
            except Exception as e:
                logger.warning(f"Error getting success rate from monitor: {e}")
        
        # Default: assume 0.5 (unknown)
        return 0.5
    
    def _calculate_verification_confidence(self, tool: Dict) -> float:
        """Calculate verification confidence based on historical data (0.0 to 1.0)"""
        tool_name = tool.get('name', '')
        metrics = self.get_tool_metrics(tool_name)
        
        if metrics['total_executions'] == 0:
            return 0.5  # Unknown
        
        # Calculate confidence from metrics
        verified_rate = 0.0
        if metrics['total_executions'] > 0:
            verified_rate = metrics['verified_executions'] / metrics['total_executions']
        
        false_positive_rate = 0.0
        if metrics['total_executions'] > 0:
            false_positive_rate = metrics['false_positives'] / metrics['total_executions']
        
        # Confidence is high verified rate and low false positive rate
        confidence = verified_rate * (1.0 - false_positive_rate)
        
        # Also factor in average confidence
        avg_confidence = metrics.get('total_confidence', 0.5)
        confidence = (confidence + avg_confidence) / 2
        
        return confidence
    
    def _calculate_execution_reliability(self, tool: Dict, execution_monitor=None) -> float:
        """Calculate execution reliability (0.0 to 1.0)"""
        tool_name = tool.get('name', '')
        
        # Get metrics
        metrics = self.get_tool_metrics(tool_name)
        
        if metrics['total_executions'] == 0:
            return 0.5  # Unknown
        
        # Reliability based on execution success and consistency
        success_rate = metrics['successful_executions'] / metrics['total_executions']
        
        # Factor in execution time consistency (lower variance = more reliable)
        # For now, just use success rate
        reliability = success_rate
        
        return reliability
    
    def select_best_tool(self, tools: List[Dict], task: str, 
                        execution_monitor=None, limit: int = 3) -> List[Tuple[float, Dict]]:
        """
        Select best tools for a task
        Returns list of (score, tool) tuples sorted by score
        """
        scored_tools = []
        
        for tool in tools:
            score = self.calculate_tool_score(tool, task, execution_monitor)
            scored_tools.append((score, tool))
        
        # Sort by score (descending)
        scored_tools.sort(key=lambda x: x[0], reverse=True)
        
        # Return top tools
        return scored_tools[:limit]
    
    def verify_tool_executable(self, tool: Dict) -> Tuple[bool, Optional[str]]:
        """Verify that tool is actually executable"""
        tool_name = tool.get('name', '')
        tool_path = tool.get('path')
        command = tool.get('command')
        
        # Check if tool has a path
        if tool_path:
            path = Path(tool_path)
            if path.exists():
                if path.is_file() and os.access(path, os.X_OK):
                    return True, None
                elif path.is_dir():
                    # Look for executable in directory
                    for item in path.iterdir():
                        if item.is_file() and os.access(item, os.X_OK):
                            return True, None
                    return False, f"Directory {path} contains no executable files"
                else:
                    return False, f"Path {path} is not executable"
            else:
                return False, f"Path {path} does not exist"
        
        # Check if tool name is in PATH
        import shutil
        if shutil.which(tool_name):
            return True, None
        
        # Check if command exists
        if command:
            # Try to verify command (basic check)
            cmd_parts = command.split()
            if cmd_parts:
                if shutil.which(cmd_parts[0]):
                    return True, None
        
        return False, f"Tool {tool_name} not found or not executable"
    
    def select_and_verify_tool(self, tools: List[Dict], task: str,
                              execution_monitor=None) -> Optional[Dict]:
        """
        Select best tool and verify it's executable
        Returns best verified tool or None
        """
        # Get top candidates
        scored_tools = self.select_best_tool(tools, task, execution_monitor, limit=5)
        
        # Try each tool until we find one that's executable
        for score, tool in scored_tools:
            is_executable, error = self.verify_tool_executable(tool)
            if is_executable:
                logger.info(f"Selected tool: {tool.get('name')} (score: {score:.2f})")
                return tool
            else:
                logger.debug(f"Tool {tool.get('name')} not executable: {error}")
        
        # No executable tool found
        logger.warning("No executable tool found from candidates")
        return None


# Global tool selector instance
_selector_instance = None

def get_tool_selector(workspace_root: Optional[str] = None) -> ToolSelector:
    """Get or create global tool selector instance"""
    global _selector_instance
    if _selector_instance is None:
        _selector_instance = ToolSelector(workspace_root)
    return _selector_instance
