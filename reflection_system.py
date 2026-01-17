# -*- coding: utf-8 -*-
"""
Reflection & Self-Correction System
Enables AI to reflect on failures, identify root causes, and self-correct
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import re

logger = logging.getLogger(__name__)


class ReflectionSystem:
    """Reflection and self-correction system for agentic orchestration"""
    
    def __init__(self):
        """Initialize reflection system"""
        self.reflection_history = []
    
    def analyze_failure(self,
                       task_description: str,
                       error_messages: List[str],
                       execution_results: List[str],
                       commands_executed: List[str]) -> Dict[str, Any]:
        """
        Analyze a failure and identify root cause
        
        Args:
            task_description: Original task description
            error_messages: List of error messages encountered
            execution_results: Execution results/outputs
            commands_executed: Commands that were executed
        
        Returns:
            Analysis dictionary with root cause and suggested fixes
        """
        analysis = {
            "root_cause": "unknown",
            "error_types": [],
            "suggested_fixes": [],
            "confidence": 0.0,
            "reflection": ""
        }
        
        # Classify errors
        error_types = []
        for error in error_messages:
            error_type = self._classify_error(error)
            error_types.append(error_type)
        
        analysis["error_types"] = list(set(error_types))
        
        # Identify root cause
        root_cause = self._identify_root_cause(error_types, error_messages, execution_results)
        analysis["root_cause"] = root_cause
        
        # Generate suggested fixes
        suggested_fixes = self._generate_fixes(root_cause, error_messages, commands_executed)
        analysis["suggested_fixes"] = suggested_fixes
        
        # Calculate confidence
        analysis["confidence"] = self._calculate_confidence(error_types, root_cause)
        
        # Generate reflection
        analysis["reflection"] = self._generate_reflection(task_description, root_cause, error_messages, suggested_fixes)
        
        # Store reflection
        self.reflection_history.append({
            "timestamp": datetime.now().isoformat(),
            "task": task_description[:200],
            "analysis": analysis
        })
        
        logger.info(f"Reflection analysis: root_cause={root_cause}, confidence={analysis['confidence']:.2f}")
        
        return analysis
    
    def generate_correction_plan(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a correction plan based on failure analysis
        
        Args:
            analysis: Failure analysis from analyze_failure
        
        Returns:
            Correction plan with steps to fix the issue
        """
        root_cause = analysis["root_cause"]
        suggested_fixes = analysis["suggested_fixes"]
        
        plan = {
            "approach": "corrective",
            "steps": [],
            "estimated_iterations": 1,
            "risk_level": "low"
        }
        
        # Generate steps based on root cause
        if root_cause == "missing_dependency":
            plan["steps"] = [
                "1. Identify missing dependency from error message",
                "2. Install missing dependency using appropriate package manager",
                "3. Verify installation",
                "4. Retry original command"
            ]
            plan["estimated_iterations"] = 2
        elif root_cause == "file_path_error":
            plan["steps"] = [
                "1. Verify correct file path exists",
                "2. Check current working directory",
                "3. Create missing directories if needed",
                "4. Use absolute path or correct relative path",
                "5. Retry original command"
            ]
            plan["estimated_iterations"] = 2
        elif root_cause == "command_syntax_error":
            plan["steps"] = [
                "1. Review command syntax",
                "2. Check command flags and options",
                "3. Verify command exists and is available",
                "4. Use correct syntax based on tool version",
                "5. Retry with corrected command"
            ]
            plan["estimated_iterations"] = 2
        elif root_cause == "permission_error":
            plan["steps"] = [
                "1. Check file/directory permissions",
                "2. Verify user has required access",
                "3. Use appropriate permissions (chmod/chown) if needed",
                "4. Retry original command"
            ]
            plan["estimated_iterations"] = 2
        elif root_cause == "timeout":
            plan["steps"] = [
                "1. Increase timeout for long-running operations",
                "2. Break task into smaller steps",
                "3. Optimize command if possible",
                "4. Retry with increased timeout"
            ]
            plan["estimated_iterations"] = 2
            plan["risk_level"] = "medium"
        elif root_cause == "network_error":
            plan["steps"] = [
                "1. Check network connectivity",
                "2. Verify target is accessible",
                "3. Check firewall rules",
                "4. Retry with exponential backoff"
            ]
            plan["estimated_iterations"] = 3
            plan["risk_level"] = "medium"
        else:
            # Generic correction
            plan["steps"] = [
                "1. Review error messages carefully",
                "2. Identify specific issue",
                "3. Apply suggested fixes",
                "4. Retry with corrections"
            ]
            plan["estimated_iterations"] = 2
        
        # Add specific fixes from analysis
        if suggested_fixes:
            plan["specific_fixes"] = suggested_fixes
        
        return plan
    
    def _classify_error(self, error_message: str) -> str:
        """Classify error type"""
        error_lower = error_message.lower()
        
        if "module not found" in error_lower or "no module named" in error_lower:
            return "missing_dependency"
        elif "package" in error_lower and ("not available" in error_lower or "has no installation candidate" in error_lower):
            return "missing_dependency"
        elif "file not found" in error_lower or "no such file" in error_lower or "cannot access" in error_lower:
            return "file_path_error"
        elif "permission denied" in error_lower:
            return "permission_error"
        elif "timeout" in error_lower or "timed out" in error_lower:
            return "timeout"
        elif "syntax error" in error_lower or "invalid" in error_lower and "option" in error_lower:
            return "command_syntax_error"
        elif "connection" in error_lower and ("refused" in error_lower or "timeout" in error_lower):
            return "network_error"
        elif "git clone" in error_lower and "fatal" in error_lower:
            return "network_error"
        else:
            return "unknown_error"
    
    def _identify_root_cause(self, error_types: List[str], error_messages: List[str], execution_results: List[str]) -> str:
        """Identify root cause from errors"""
        # Count error type occurrences
        error_counts = {}
        for error_type in error_types:
            error_counts[error_type] = error_counts.get(error_type, 0) + 1
        
        # Most common error type is likely root cause
        if error_counts:
            most_common = max(error_counts.items(), key=lambda x: x[1])
            return most_common[0]
        
        # Check for specific patterns in error messages
        all_errors = " ".join(error_messages).lower()
        
        if "libpcre3-dev" in all_errors or "has no installation candidate" in all_errors:
            return "missing_dependency"
        elif "httpx" in all_errors and ("-s" in all_errors or "no such option" in all_errors):
            return "command_syntax_error"
        elif "can't open file" in all_errors:
            return "file_path_error"
        
        return "unknown_error"
    
    def _generate_fixes(self, root_cause: str, error_messages: List[str], commands_executed: List[str]) -> List[str]:
        """Generate specific fixes based on root cause"""
        fixes = []
        
        if root_cause == "missing_dependency":
            # Extract module/package name from errors
            for error in error_messages:
                module_match = re.search(r"no module named ['\"]([^'\"]+)['\"]", error.lower())
                if module_match:
                    fixes.append(f"pip install {module_match.group(1)}")
                
                package_match = re.search(r"package ['\"]([^'\"]+)['\"]", error.lower())
                if package_match:
                    package_name = package_match.group(1)
                    # Try alternative package names
                    if "libpcre3-dev" in error.lower():
                        fixes.append("apt-get install libpcre2-dev")
                        fixes.append("apt-get install libpcre-dev")
                    else:
                        fixes.append(f"apt-get install {package_name}")
        
        elif root_cause == "command_syntax_error":
            for error in error_messages:
                if "httpx" in error.lower() and "-s" in error.lower():
                    fixes.append("Use `httpx -silent` instead of `httpx -s`")
                    fixes.append("Or remove the `-s` flag entirely")
                elif "required arguments" in error.lower():
                    fixes.append("Check command syntax and provide all required arguments")
        
        elif root_cause == "file_path_error":
            fixes.append("Verify file path exists: `ls -la <path>`")
            fixes.append("Check current directory: `pwd`")
            fixes.append("Create missing directories: `mkdir -p <dir>`")
            fixes.append("Use absolute path if relative path fails")
        
        elif root_cause == "timeout":
            fixes.append("Increase timeout for long-running operations")
            fixes.append("Break task into smaller steps")
            fixes.append("Optimize command if possible")
        
        elif root_cause == "network_error":
            fixes.append("Check network connectivity")
            fixes.append("Verify target is accessible")
            fixes.append("Retry with exponential backoff")
            if any("git clone" in e.lower() for e in error_messages):
                fixes.append("Skip git clone or use alternative method (download zip)")
        
        return fixes
    
    def _calculate_confidence(self, error_types: List[str], root_cause: str) -> float:
        """Calculate confidence in root cause identification"""
        # Higher confidence if error types are consistent
        if len(set(error_types)) == 1:
            confidence = 0.9  # Single error type, high confidence
        elif len(set(error_types)) == 2:
            confidence = 0.7  # Two error types, medium confidence
        else:
            confidence = 0.5  # Multiple error types, lower confidence
        
        # Adjust based on root cause
        if root_cause == "unknown_error":
            confidence *= 0.5  # Lower confidence for unknown errors
        
        return confidence
    
    def _generate_reflection(self, task_description: str, root_cause: str, error_messages: List[str], suggested_fixes: List[str]) -> str:
        """Generate reflection text"""
        reflection = f"**Reflection on Task Failure:**\n\n"
        reflection += f"**Task:** {task_description[:200]}\n\n"
        reflection += f"**Root Cause Identified:** {root_cause}\n\n"
        
        if error_messages:
            reflection += f"**Errors Encountered:**\n"
            for i, error in enumerate(error_messages[:3], 1):
                error_preview = error[:300] + "..." if len(error) > 300 else error
                reflection += f"{i}. {error_preview}\n"
            reflection += "\n"
        
        if suggested_fixes:
            reflection += f"**Suggested Fixes:**\n"
            for i, fix in enumerate(suggested_fixes[:5], 1):
                reflection += f"{i}. {fix}\n"
            reflection += "\n"
        
        reflection += "**Next Steps:** Apply the suggested fixes and retry the task.\n"
        
        return reflection
    
    def format_reflection_for_prompt(self, analysis: Dict[str, Any]) -> str:
        """
        Format reflection analysis for inclusion in AI prompt
        
        Args:
            analysis: Failure analysis from analyze_failure
        
        Returns:
            Formatted string for prompt
        """
        formatted = "\n\n## 🔍 REFLECTION & SELF-CORRECTION:\n\n"
        formatted += analysis["reflection"]
        formatted += "\n**Confidence:** {:.0%}\n".format(analysis["confidence"])
        formatted += "\n**ACTION REQUIRED:** Use the suggested fixes above to correct the errors and retry.\n"
        
        return formatted
