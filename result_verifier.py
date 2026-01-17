# -*- coding: utf-8 -*-
"""
Result Verifier - Execution verification and false positive detection
Ensures tools are actually executed and tasks completed accurately
"""

import os
import re
import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class ResultVerifier:
    """Verifies tool execution results and detects false positives"""
    
    def __init__(self, workspace_root: Optional[str] = None):
        """
        Initialize result verifier
        workspace_root: Workspace directory for verification logs
        """
        self.workspace_root = Path(workspace_root) if workspace_root else Path(os.getcwd())
        self.verification_logs = self.workspace_root / "verification_logs"
        self.verification_logs.mkdir(exist_ok=True)
        
        # False positive patterns
        self.false_positive_patterns = [
            r'^$',  # Empty output
            r'^\s*$',  # Whitespace only
            r'command not found',
            r'not found',
            r'no such file',
            r'permission denied',
            r'cannot execute',
            r'error.*occurred',
            r'failed.*to.*run',
            r'execution.*failed',
        ]
        
        # Success indicators
        self.success_indicators = [
            r'success',
            r'completed',
            r'done',
            r'finished',
            r'found.*result',
            r'vulnerability.*found',
            r'port.*open',
            r'connection.*established',
        ]
    
    def verify_execution(self, execution_result: Dict, expected_result: Optional[Dict] = None) -> Dict:
        """
        Verify tool execution result
        Returns verification result with confidence score
        """
        verification = {
            'verified': False,
            'confidence': 0.0,
            'is_false_positive': False,
            'issues': [],
            'warnings': [],
            'execution_valid': False,
            'output_valid': False,
            'task_completed': False
        }
        
        # 1. Verify execution actually happened
        execution_valid = self._verify_execution_occurred(execution_result)
        verification['execution_valid'] = execution_valid
        
        if not execution_valid:
            verification['is_false_positive'] = True
            verification['issues'].append("Tool execution did not occur")
            return verification
        
        # 2. Verify output
        output_valid = self._verify_output(execution_result)
        verification['output_valid'] = output_valid
        
        if not output_valid:
            verification['is_false_positive'] = True
            verification['issues'].append("Output validation failed")
        
        # 3. Check for false positives
        is_false_positive = self._detect_false_positive(execution_result)
        verification['is_false_positive'] = is_false_positive
        
        if is_false_positive:
            verification['issues'].append("False positive detected")
        
        # 4. Verify task completion
        if expected_result:
            task_completed = self._verify_task_completion(execution_result, expected_result)
            verification['task_completed'] = task_completed
            
            if not task_completed:
                verification['warnings'].append("Task objectives may not be fully met")
        
        # 5. Calculate confidence score
        confidence = self._calculate_confidence(verification, execution_result)
        verification['confidence'] = confidence
        
        # 6. Overall verification
        verification['verified'] = (
            execution_valid and
            output_valid and
            not is_false_positive and
            confidence >= 0.7
        )
        
        return verification
    
    def _verify_execution_occurred(self, execution_result: Dict) -> bool:
        """Verify that tool execution actually occurred"""
        # Check exit code
        exit_code = execution_result.get('exit_code')
        if exit_code is not None:
            # Exit code exists - execution definitely occurred
            # Check if output exists
            output = execution_result.get('output', '')
            error = execution_result.get('error', '')
            output_length = execution_result.get('output_length', 0)
            stdout_len = execution_result.get('stdout_len', 0)
            stderr_len = execution_result.get('stderr_len', 0)
            
            # If we have output (any form), execution occurred
            if output or error or output_length > 0 or stdout_len > 0 or stderr_len > 0:
                return True
            
            # If exit code is non-zero, execution occurred (even if no output)
            if exit_code != 0:
                return True
        
        # Check execution time (too short might indicate didn't run, but only if no other indicators)
        execution_time = execution_result.get('execution_time', 0)
        if execution_time > 0:
            # Execution time > 0 means execution occurred
            if execution_time < 0.01:  # Less than 10ms is suspicious (but don't block if output exists)
                logger.warning(f"Suspiciously short execution time: {execution_time}s")
                # Don't return False here - check other indicators first
        
        # Check if output exists (from any source)
        output = execution_result.get('output', '')
        error = execution_result.get('error', '')
        output_length = execution_result.get('output_length', 0)
        
        # If we have output, execution occurred
        if output or error or output_length > 0:
            return True
        
        # Check for process indicators
        if 'process_id' in execution_result:
            # Process ID exists, execution occurred
            return True
        
        # If exit code exists and we have no output, still consider it executed
        # (some commands produce no output but still execute)
        if exit_code is not None:
            return True
        
        # No indicators of execution
        return False
    
    def _verify_output(self, execution_result: Dict) -> bool:
        """Verify output is valid"""
        output = execution_result.get('output', '')
        error = execution_result.get('error', '')
        exit_code = execution_result.get('exit_code', -1)
        
        # Empty output is invalid (unless error code indicates success with no output)
        if not output and not error:
            if exit_code == 0:
                # Success with no output might be valid for some tools
                return True
            return False
        
        # Check output length (too short might be invalid)
        if output and len(output.strip()) < 10:
            # Very short output might be invalid
            return False
        
        # Check for error patterns in output
        if error:
            error_lower = error.lower()
            if any(pattern in error_lower for pattern in ['fatal', 'critical', 'cannot', 'unable']):
                return False
        
        return True
    
    def _detect_false_positive(self, execution_result: Dict) -> bool:
        """Detect false positive (tool claims success but didn't actually work)"""
        output = execution_result.get('output', '').lower()
        error = execution_result.get('error', '').lower()
        exit_code = execution_result.get('exit_code', -1)
        
        # Check false positive patterns
        combined_text = output + ' ' + error
        
        # Pattern 1: Empty or whitespace-only output with success exit code
        if exit_code == 0 and not output.strip() and not error.strip():
            return True
        
        # Pattern 2: Error patterns in output despite success exit code
        if exit_code == 0:
            for pattern in self.false_positive_patterns:
                if re.search(pattern, combined_text, re.IGNORECASE):
                    return True
        
        # Pattern 3: "Command not found" or similar
        not_found_patterns = [
            r'command not found',
            r'not found',
            r'no such file',
            r'cannot find',
        ]
        for pattern in not_found_patterns:
            if re.search(pattern, combined_text, re.IGNORECASE):
                return True
        
        # Pattern 4: Permission denied
        if 'permission denied' in combined_text:
            return True
        
        # Pattern 5: Execution time too short (didn't actually run)
        execution_time = execution_result.get('execution_time', 0)
        if execution_time < 0.01:  # Less than 10ms
            return True
        
        return False
    
    def _verify_task_completion(self, execution_result: Dict, expected_result: Dict) -> bool:
        """Verify that task objectives were met"""
        output = execution_result.get('output', '').lower()
        expected_output = expected_result.get('expected_output', '').lower()
        expected_keywords = expected_result.get('expected_keywords', [])
        
        # Check for expected keywords
        if expected_keywords:
            found_keywords = sum(1 for kw in expected_keywords if kw.lower() in output)
            if found_keywords == 0:
                return False
            # At least 50% of keywords should be found
            if found_keywords < len(expected_keywords) * 0.5:
                return False
        
        # Check for expected output pattern
        if expected_output:
            if expected_output not in output:
                return False
        
        # Check for success indicators
        has_success_indicator = any(
            re.search(indicator, output, re.IGNORECASE)
            for indicator in self.success_indicators
        )
        
        return has_success_indicator
    
    def _calculate_confidence(self, verification: Dict, execution_result: Dict) -> float:
        """Calculate confidence score (0.0 to 1.0)"""
        confidence = 0.0
        
        # Execution occurred: +0.3
        if verification['execution_valid']:
            confidence += 0.3
        
        # Output is valid: +0.3
        if verification['output_valid']:
            confidence += 0.3
        
        # Not a false positive: +0.2
        if not verification['is_false_positive']:
            confidence += 0.2
        
        # Task completed: +0.2
        if verification.get('task_completed', False):
            confidence += 0.2
        elif not verification.get('task_completed') is False:
            # Task completion not checked, don't penalize
            confidence += 0.1
        
        # Exit code check
        exit_code = execution_result.get('exit_code', -1)
        if exit_code == 0:
            confidence += 0.1
        
        # Output length check (longer output often more reliable)
        output = execution_result.get('output', '')
        if len(output) > 100:
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def verify_side_effects(self, execution_result: Dict, expected_side_effects: List[str]) -> Dict:
        """
        Verify side effects of tool execution (files created, network changes, etc.)
        """
        verification = {
            'verified': True,
            'side_effects_found': [],
            'side_effects_missing': [],
            'issues': []
        }
        
        for side_effect in expected_side_effects:
            if side_effect.startswith('file:'):
                # Check for file creation
                file_path = Path(side_effect[5:])
                if file_path.exists():
                    verification['side_effects_found'].append(f"File created: {file_path}")
                else:
                    verification['side_effects_missing'].append(f"File not created: {file_path}")
                    verification['verified'] = False
        
        return verification
    
    def compare_results(self, actual_result: Dict, expected_result: Dict) -> Dict:
        """Compare actual result with expected result"""
        comparison = {
            'matches': False,
            'similarity_score': 0.0,
            'differences': [],
            'matches_expected': []
        }
        
        actual_output = actual_result.get('output', '').lower()
        expected_output = expected_result.get('expected_output', '').lower()
        
        # Simple similarity check
        if expected_output in actual_output:
            comparison['matches'] = True
            comparison['similarity_score'] = 1.0
            comparison['matches_expected'].append("Output contains expected content")
        else:
            # Calculate similarity
            similarity = self._calculate_similarity(actual_output, expected_output)
            comparison['similarity_score'] = similarity
            
            if similarity >= 0.7:
                comparison['matches'] = True
            else:
                comparison['differences'].append("Output does not match expected result")
        
        return comparison
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts (simple implementation)"""
        if not text1 or not text2:
            return 0.0
        
        # Simple word overlap
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        if not union:
            return 0.0
        
        return len(intersection) / len(union)
    
    def generate_verification_report(self, verification: Dict) -> str:
        """Generate human-readable verification report"""
        lines = []
        lines.append("=" * 60)
        lines.append("EXECUTION VERIFICATION REPORT")
        lines.append("=" * 60)
        
        status = "✅ VERIFIED" if verification['verified'] else "❌ FAILED"
        lines.append(f"\nStatus: {status}")
        lines.append(f"Confidence: {verification['confidence']:.2%}")
        
        lines.append("\nVerification Checks:")
        lines.append(f"  Execution Valid: {'✅' if verification['execution_valid'] else '❌'}")
        lines.append(f"  Output Valid: {'✅' if verification['output_valid'] else '❌'}")
        lines.append(f"  False Positive: {'❌ YES' if verification['is_false_positive'] else '✅ NO'}")
        if 'task_completed' in verification:
            lines.append(f"  Task Completed: {'✅' if verification['task_completed'] else '❌'}")
        
        if verification.get('issues'):
            lines.append("\nIssues:")
            for issue in verification['issues']:
                lines.append(f"  - {issue}")
        
        if verification.get('warnings'):
            lines.append("\nWarnings:")
            for warning in verification['warnings']:
                lines.append(f"  - {warning}")
        
        lines.append("\n" + "=" * 60)
        
        return "\n".join(lines)


# Global result verifier instance
_verifier_instance = None

def get_result_verifier(workspace_root: Optional[str] = None) -> ResultVerifier:
    """Get or create global result verifier instance"""
    global _verifier_instance
    if _verifier_instance is None:
        _verifier_instance = ResultVerifier(workspace_root)
    return _verifier_instance
