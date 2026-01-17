# -*- coding: utf-8 -*-
"""
Code Reviewer - Comprehensive code review and testing
Performs syntax validation, execution testing, output validation, and fix suggestions
"""

import os
import sys
import subprocess
import tempfile
import re
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import time

logger = logging.getLogger(__name__)

# Import command validator for syntax checking
try:
    from command_validator import get_validator, CommandValidator
    VALIDATOR_AVAILABLE = True
except ImportError:
    VALIDATOR_AVAILABLE = False
    logger.warning("command_validator not available")

# Import result verifier for execution verification
try:
    from result_verifier import get_result_verifier, ResultVerifier
    RESULT_VERIFIER_AVAILABLE = True
except ImportError:
    RESULT_VERIFIER_AVAILABLE = False
    logger.warning("result_verifier not available")


class CodeReviewer:
    """Comprehensive code review and testing system"""
    
    def __init__(self, workspace_root: Optional[str] = None, brain=None):
        """
        Initialize CodeReviewer
        workspace_root: Workspace directory for test execution
        brain: HacxBrain instance for AI-based fix suggestions
        """
        self.workspace_root = Path(workspace_root) if workspace_root else Path(tempfile.gettempdir())
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.brain = brain
        
        # Initialize validator
        self.validator = None
        if VALIDATOR_AVAILABLE:
            try:
                sandbox_enabled = os.getenv('SANDBOX_ENABLED', 'true').lower() == 'true'
                timeout = int(os.getenv('SANDBOX_TIMEOUT', '30'))
                self.validator = get_validator(sandbox_enabled=sandbox_enabled, timeout=timeout)
            except Exception as e:
                logger.warning(f"Could not initialize validator: {e}")
        
        # Initialize result verifier
        self.result_verifier = None
        if RESULT_VERIFIER_AVAILABLE:
            try:
                self.result_verifier = get_result_verifier(str(self.workspace_root))
            except Exception as e:
                logger.warning(f"Could not initialize result verifier: {e}")
        
        # Test execution directory
        self.test_dir = self.workspace_root / "test_executions"
        self.test_dir.mkdir(exist_ok=True)
    
    def review_code(self, code: str, language: str = 'python', filename: Optional[str] = None) -> Dict:
        """
        Perform full code review
        Returns comprehensive review results
        """
        review_results = {
            'syntax_valid': False,
            'syntax_errors': [],
            'execution_tested': False,
            'execution_result': None,
            'output_valid': False,
            'output_issues': [],
            'missing_imports': [],
            'fixes_suggested': [],
            'overall_status': 'unknown',
            'warnings': []
        }
        
        # 1. Syntax Validation
        syntax_result = self._validate_syntax(code, language)
        review_results['syntax_valid'] = syntax_result['valid']
        review_results['syntax_errors'] = syntax_result.get('errors', [])
        
        if not syntax_result['valid']:
            review_results['overall_status'] = 'fail'
            # Still try to suggest fixes
            review_results['fixes_suggested'] = self._suggest_syntax_fixes(code, syntax_result['errors'], language)
            return review_results
        
        # 2. Missing Imports Detection
        if language in ['python', 'py']:
            missing_imports = self._detect_missing_imports(code)
            review_results['missing_imports'] = missing_imports
            if missing_imports:
                # Filter out None values before joining
                missing_imports_clean = [str(m) for m in missing_imports if m is not None]
                if missing_imports_clean:
                    review_results['warnings'].append(f"Missing imports: {', '.join(missing_imports_clean)}")
        
        # 3. Execution Testing
        if syntax_result['valid']:
            execution_result = self._test_execution(code, language, filename)
            review_results['execution_tested'] = True
            review_results['execution_result'] = execution_result
            
            # Verify execution with result verifier
            if self.result_verifier and execution_result:
                verification = self.result_verifier.verify_execution(execution_result)
                review_results['verification'] = verification
                
                if verification.get('is_false_positive'):
                    review_results['output_issues'].append("False positive detected - execution may not have occurred")
                    review_results['warnings'].append("Code execution verification failed")
            
            if execution_result.get('success'):
                review_results['output_valid'] = self._validate_output(
                    execution_result.get('output', ''),
                    execution_result.get('expected_output', '')
                )
            else:
                review_results['output_issues'].append(execution_result.get('error', 'Execution failed'))
        
        # 4. Generate Fix Suggestions
        if review_results['syntax_errors'] or review_results['output_issues'] or review_results['missing_imports']:
            fixes = self._suggest_fixes(review_results, code, language)
            review_results['fixes_suggested'] = fixes
        
        # 5. Determine Overall Status
        if review_results['syntax_valid'] and review_results.get('execution_result', {}).get('success'):
            if review_results['output_valid']:
                review_results['overall_status'] = 'pass'
            else:
                review_results['overall_status'] = 'warning'
        elif review_results['syntax_valid']:
            review_results['overall_status'] = 'warning'
        else:
            review_results['overall_status'] = 'fail'
        
        return review_results
    
    def _validate_syntax(self, code: str, language: str) -> Dict:
        """Validate code syntax"""
        result = {'valid': False, 'errors': []}
        
        if language in ['python', 'py']:
            if self.validator:
                valid, error = self.validator.validate_python_code(code)
                result['valid'] = valid
                if error:
                    result['errors'].append(error)
            else:
                # Fallback: try compile
                try:
                    compile(code, '<string>', 'exec')
                    result['valid'] = True
                except SyntaxError as e:
                    result['errors'].append(f"Syntax error: {str(e)}")
                except Exception as e:
                    result['errors'].append(f"Validation error: {str(e)}")
        
        elif language in ['bash', 'sh', 'shell']:
            # Basic bash syntax check
            if self.validator:
                valid, error = self.validator.validate_syntax(code)
                result['valid'] = valid
                if error:
                    result['errors'].append(error)
            else:
                # Simple check for balanced quotes
                if code.count('"') % 2 == 0 and code.count("'") % 2 == 0:
                    result['valid'] = True
                else:
                    result['errors'].append("Unmatched quotes")
        
        else:
            # Unknown language, assume valid
            result['valid'] = True
        
        return result
    
    def _detect_missing_imports(self, code: str) -> List[str]:
        """Detect missing imports in Python code"""
        missing = []
        
        # Common modules that might be used
        common_modules = {
            'requests': ['requests', 'requests.get', 'requests.post'],
            'beautifulsoup4': ['BeautifulSoup', 'bs4'],
            'selenium': ['selenium', 'webdriver'],
            'numpy': ['numpy', 'np'],
            'pandas': ['pandas', 'pd'],
            'PIL': ['PIL', 'Image', 'ImageGrab'],
            'mss': ['mss', 'mss.mss'],
            'subprocess': ['subprocess'],  # Usually imported
            'os': ['os'],  # Usually imported
            'sys': ['sys'],  # Usually imported
            'json': ['json'],
            're': ['re'],
            'time': ['time'],
            'threading': ['threading', 'Thread'],
            'concurrent.futures': ['ThreadPoolExecutor', 'as_completed']
        }
        
        # Check for imports
        import_pattern = r'^(?:from\s+(\S+)\s+)?import\s+(\S+)'
        imported_modules = set()
        
        for line in code.split('\n'):
            match = re.match(import_pattern, line.strip())
            if match:
                if match.group(1):  # from X import Y
                    imported_modules.add(match.group(1).split('.')[0])
                if match.group(2):  # import X
                    imported_modules.add(match.group(2).split('.')[0].split(' as ')[0])
        
        # Check for usage without import
        for module, patterns in common_modules.items():
            if module not in imported_modules:
                # Check if module is used in code
                for pattern in patterns:
                    if re.search(rf'\b{pattern}\b', code):
                        if module not in missing:
                            missing.append(module)
                        break
        
        return missing
    
    def _test_execution(self, code: str, language: str, filename: Optional[str] = None) -> Dict:
        """
        Test code execution in sandbox
        Returns execution result dict
        """
        result = {
            'success': False,
            'output': '',
            'error': None,
            'exit_code': -1,
            'execution_time': 0
        }
        
        if not filename:
            filename = f"test_{int(time.time())}.{language if language != 'py' else 'py'}"
        
        test_file = self.test_dir / filename
        
        try:
            # Write code to test file
            test_file.write_text(code, encoding='utf-8')
            
            # Execute based on language
            start_time = time.time()
            
            if language in ['python', 'py']:
                # Test Python execution
                exec_result = subprocess.run(
                    [sys.executable, str(test_file)],
                    cwd=str(self.test_dir),
                    capture_output=True,
                    text=True,
                    timeout=30,
                    encoding='utf-8',
                    errors='replace'
                )
                result['exit_code'] = exec_result.returncode
                result['output'] = exec_result.stdout
                result['error'] = exec_result.stderr if exec_result.stderr else None
                result['success'] = exec_result.returncode == 0
            
            elif language in ['bash', 'sh', 'shell']:
                # Test bash execution
                exec_result = subprocess.run(
                    ['bash', str(test_file)],
                    cwd=str(self.test_dir),
                    capture_output=True,
                    text=True,
                    timeout=30,
                    encoding='utf-8',
                    errors='replace'
                )
                result['exit_code'] = exec_result.returncode
                result['output'] = exec_result.stdout
                result['error'] = exec_result.stderr if exec_result.stderr else None
                result['success'] = exec_result.returncode == 0
            
            result['execution_time'] = time.time() - start_time
            
            # Clean up test file
            if test_file.exists():
                test_file.unlink()
        
        except subprocess.TimeoutExpired:
            result['error'] = 'Execution timed out after 30 seconds'
            result['success'] = False
        except Exception as e:
            result['error'] = str(e)
            result['success'] = False
            logger.error(f"Execution test error: {e}")
        
        return result
    
    def _validate_output(self, actual_output: str, expected_output: str) -> bool:
        """
        Validate execution output
        Returns True if output is valid
        """
        if not expected_output:
            # No expected output, check for errors
            error_indicators = ['error', 'exception', 'traceback', 'failed', 'failure']
            actual_lower = actual_output.lower()
            return not any(indicator in actual_lower for indicator in error_indicators)
        
        # Simple validation: check if expected keywords are in output
        expected_lower = expected_output.lower()
        actual_lower = actual_output.lower()
        
        # Extract key words from expected output
        expected_words = [w for w in expected_lower.split() if len(w) > 3]
        
        if not expected_words:
            return True
        
        # Check if at least some expected words appear
        matches = sum(1 for word in expected_words if word in actual_lower)
        return matches >= len(expected_words) * 0.5  # At least 50% match
    
    def _suggest_syntax_fixes(self, code: str, errors: List[str], language: str) -> List[str]:
        """Suggest fixes for syntax errors"""
        fixes = []
        
        for error in errors:
            # Skip None or empty errors
            if not error or not isinstance(error, str):
                continue
            
            error_lower = error.lower()
            if 'SyntaxError' in error or 'syntax error' in error_lower:
                # Common syntax fixes
                if 'unexpected EOF' in error or 'unexpected end of file' in error:
                    fixes.append("Check for missing closing brackets, parentheses, or quotes")
                elif 'invalid syntax' in error_lower:
                    fixes.append("Review syntax around the error location")
                elif 'indentation' in error_lower:
                    fixes.append("Check indentation - Python requires consistent indentation")
                elif 'unexpected indent' in error_lower:
                    fixes.append("Remove unexpected indentation or add missing code")
                else:
                    fixes.append(f"Fix syntax error: {error}")
        
        return fixes
    
    def _suggest_fixes(self, review_results: Dict, code: str, language: str) -> List[str]:
        """Generate comprehensive fix suggestions"""
        fixes = []
        
        # Missing imports
        if review_results.get('missing_imports'):
            # Filter out None values before joining
            missing_imports = [str(m) for m in review_results['missing_imports'] if m is not None]
            if missing_imports:
                imports_str = ', '.join(missing_imports)
                fixes.append(f"Install missing modules: pip install {imports_str}")
                fixes.append(f"Add imports at top of file: import {', '.join(missing_imports)}")
        
        # Syntax errors
        if review_results.get('syntax_errors'):
            fixes.extend(self._suggest_syntax_fixes(code, review_results['syntax_errors'], language))
        
        # Execution errors
        execution_result = review_results.get('execution_result', {})
        if execution_result and not execution_result.get('success'):
            error = execution_result.get('error', '')
            if error:
                if 'ModuleNotFoundError' in error or 'No module named' in error:
                    module = re.search(r"No module named '(\S+)'", error)
                    if module:
                        fixes.append(f"Install missing module: pip install {module.group(1)}")
                elif 'ImportError' in error:
                    fixes.append("Check import statements and module availability")
                elif 'NameError' in error:
                    fixes.append("Check for undefined variables or functions")
                elif 'TypeError' in error:
                    fixes.append("Check data types and function arguments")
                else:
                    fixes.append(f"Fix execution error: {error[:100]}")
        
        # Use AI for complex fixes if brain available
        if self.brain and (review_results.get('syntax_errors') or review_results.get('output_issues')):
            try:
                ai_fixes = self._get_ai_fix_suggestions(code, review_results, language)
                fixes.extend(ai_fixes)
            except Exception as e:
                logger.warning(f"AI fix suggestions failed: {e}")
        
        return fixes
    
    def _get_ai_fix_suggestions(self, code: str, review_results: Dict, language: str) -> List[str]:
        """Get AI-based fix suggestions"""
        if not self.brain:
            return []
        
        issues_text = ""
        if review_results.get('syntax_errors'):
            # Filter out None values before joining
            syntax_errors = [str(e) for e in review_results['syntax_errors'] if e is not None]
            if syntax_errors:
                issues_text += f"Syntax Errors: {', '.join(syntax_errors)}\n"
        if review_results.get('missing_imports'):
            # Filter out None values before joining
            missing_imports = [str(m) for m in review_results['missing_imports'] if m is not None]
            if missing_imports:
                issues_text += f"Missing Imports: {', '.join(missing_imports)}\n"
        if review_results.get('output_issues'):
            # Filter out None values before joining
            output_issues = [str(o) for o in review_results['output_issues'] if o is not None]
            if output_issues:
                issues_text += f"Output Issues: {', '.join(output_issues)}\n"
        
        prompt = f"""Analyze this {language} code and suggest specific fixes:

CODE:
```{language}
{code}
```

ISSUES:
{issues_text}

Provide 2-3 specific, actionable fix suggestions. Be concise and direct."""

        suggestions = []
        try:
            response = ""
            for chunk in self.brain.chat(prompt):
                response += chunk
            
            # Extract suggestions (numbered list)
            suggestion_pattern = r'(?:\d+\.|[-*])\s*(.+)'
            matches = re.finditer(suggestion_pattern, response)
            for match in matches:
                suggestion = match.group(1).strip()
                if suggestion and len(suggestion) > 10:  # Filter out very short suggestions
                    suggestions.append(suggestion)
            
            # Limit to 3 suggestions
            suggestions = suggestions[:3]
        except Exception as e:
            logger.error(f"Error getting AI fix suggestions: {e}")
        
        return suggestions
    
    def _read_file(self, file_path: str) -> str:
        """Read file content"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return ""
    
    def _write_corrected_file(self, file_path: str, corrected_code: str) -> bool:
        """Write corrected code to file"""
        try:
            # Create backup
            backup_path = file_path + '.backup'
            if Path(file_path).exists():
                Path(file_path).rename(backup_path)
            
            # Write corrected code
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(corrected_code)
            
            logger.info(f"Corrected code written to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error writing corrected file {file_path}: {e}")
            return False
    
    def _fix_syntax_errors(self, file_path: str, syntax_errors: List[str]) -> Optional[str]:
        """Try to fix syntax errors automatically"""
        try:
            code = self._read_file(file_path)
            if not code:
                return None
            
            # Use AI to fix syntax errors if brain is available
            if self.brain:
                # Filter out None values before joining
                syntax_errors_clean = [str(e) for e in syntax_errors if e is not None]
                if not syntax_errors_clean:
                    return None
                
                fix_prompt = f"""
Fix the following Python code syntax errors:

Code:
```python
{code}
```

Errors:
{chr(10).join(f"- {err}" for err in syntax_errors_clean)}

Return the corrected code only, without explanations.
"""
                fixed_code = ""
                for chunk in self.brain.chat(fix_prompt):
                    fixed_code += chunk
                
                # Extract code from response if it's in a code block
                code_match = re.search(r'```(?:python)?\n(.*?)```', fixed_code, re.DOTALL)
                if code_match:
                    return code_match.group(1)
                elif fixed_code.strip():
                    return fixed_code.strip()
            
            return None
        except Exception as e:
            logger.warning(f"Error fixing syntax errors: {e}")
            return None
    
    def _add_missing_imports(self, code: str, missing_imports: List[str]) -> str:
        """Add missing imports to code"""
        if not missing_imports:
            return code
        
        # Find the last import statement
        import_pattern = r'^(?:from\s+\S+\s+)?import\s+\S+'
        lines = code.split('\n')
        last_import_line = -1
        
        for i, line in enumerate(lines):
            if re.match(import_pattern, line.strip()):
                last_import_line = i
        
        # Add missing imports
        new_imports = []
        for imp in missing_imports:
            # Check if already imported
            if not re.search(rf'^(?:from\s+{re.escape(imp)}|import\s+{re.escape(imp)})', code, re.MULTILINE):
                new_imports.append(f"import {imp}")
        
        if new_imports:
            # Insert after last import or at the beginning
            insert_pos = last_import_line + 1 if last_import_line >= 0 else 0
            lines.insert(insert_pos, '\n'.join(new_imports))
            if insert_pos > 0:
                lines.insert(insert_pos + len(new_imports), '')  # Add blank line after imports
        
        return '\n'.join(lines)
    
    def review_and_correct_code(self, file_path: str) -> Dict:
        """Review code and automatically correct issues"""
        # Read original code
        original_code = self._read_file(file_path)
        if not original_code:
            return {
                'review': {},
                'corrections': [],
                'corrected': False,
                'error': 'Could not read file'
            }
        
        # Review code
        language = 'python' if file_path.endswith('.py') else 'text'
        review = self.review_code(original_code, language=language, filename=Path(file_path).name)
        
        corrections = []
        corrected_code = None
        
        # Auto-fix common issues
        if review.get('syntax_errors'):
            # Try to fix syntax errors
            fixed_code = self._fix_syntax_errors(file_path, review['syntax_errors'])
            if fixed_code:
                corrected_code = fixed_code
                corrections.append("Fixed syntax errors")
        
        if review.get('missing_imports'):
            # Add missing imports
            code_to_fix = corrected_code if corrected_code else original_code
            corrected_code = self._add_missing_imports(code_to_fix, review['missing_imports'])
            if corrected_code != code_to_fix:
                # Filter out None values before joining
                missing_imports = [str(m) for m in review['missing_imports'] if m is not None]
                if missing_imports:
                    corrections.append(f"Added missing imports: {', '.join(missing_imports)}")
        
        # Apply corrections if safe
        if corrected_code and corrected_code != original_code:
            success = self._write_corrected_file(file_path, corrected_code)
            if success:
                # Re-review corrected code
                review = self.review_code(corrected_code, language=language, filename=Path(file_path).name)
        
        return {
            'review': review,
            'corrections': corrections,
            'corrected': corrected_code is not None and corrected_code != original_code
        }
    
    def generate_report(self, review_results: Dict, filename: Optional[str] = None) -> str:
        """Generate clean, concise formatted review report"""
        filename_str = filename or "code"
        
        # Determine overall status
        status_emoji = "✅" if review_results['overall_status'] == 'pass' else \
                      "⚠️" if review_results['overall_status'] == 'warning' else "❌"
        
        # Build concise report
        lines = []
        lines.append(f"📊 **Code Review: {filename_str}**")
        lines.append(f"\n**Status:** {status_emoji} {review_results['overall_status'].upper()}")
        
        # Collect issues
        issues = []
        
        # Syntax issues
        if not review_results['syntax_valid']:
            # Filter out None values
            syntax_errors = [str(e) for e in review_results.get('syntax_errors', []) if e is not None]
            for error in syntax_errors[:3]:  # Limit to 3 errors
                issues.append(f"❌ Syntax: {error[:100]}")
        
        # Missing imports
        if review_results.get('missing_imports'):
            # Filter out None values before joining
            missing_imports = [str(m) for m in review_results['missing_imports'] if m is not None]
            if missing_imports:
                imports_str = ', '.join(missing_imports)
                issues.append(f"⚠️ Missing imports: {imports_str}")
                issues.append(f"💡 Fix: `pip install {imports_str}`")
        
        # Execution issues
        if review_results.get('execution_tested'):
            exec_result = review_results.get('execution_result', {})
            if not exec_result.get('success'):
                error_msg = exec_result.get('error', 'Unknown error')[:150]
                issues.append(f"❌ Execution failed: {error_msg}")
            elif exec_result.get('success'):
                # Only mention if there are other issues
                pass
        
        # Output validation issues
        if review_results.get('execution_tested') and not review_results.get('output_valid'):
            for issue in review_results.get('output_issues', [])[:2]:  # Limit to 2 issues
                issues.append(f"⚠️ Output: {issue[:100]}")
        
        # Add issues if any
        if issues:
            lines.append("\n**Issues:**")
            for issue in issues:
                lines.append(f"• {issue}")
        else:
            lines.append("\n✅ **No issues found** - Code is ready to use")
        
        # Final status
        if review_results['overall_status'] == 'pass':
            lines.append("\n✅ **Ready to use**")
        elif review_results['overall_status'] == 'warning':
            lines.append("\n⚠️ **Needs fixes** - Review issues above")
        else:
            lines.append("\n❌ **Cannot use** - Fix errors first")
        
        return "\n".join(lines)
    
    def review_file(self, file_path: str) -> Dict:
        """Review a code file"""
        path = Path(file_path)
        if not path.exists():
            return {
                'overall_status': 'fail',
                'syntax_errors': [f"File not found: {file_path}"]
            }
        
        code = path.read_text(encoding='utf-8')
        language = self._detect_language(path.suffix)
        
        return self.review_code(code, language, filename=path.name)
    
    def _detect_language(self, extension: str) -> str:
        """Detect language from file extension"""
        lang_map = {
            '.py': 'python',
            '.sh': 'bash',
            '.bash': 'bash',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.go': 'go',
            '.rs': 'rust'
        }
        return lang_map.get(extension.lower(), 'python')


# Global reviewer instance
_reviewer_instance = None

def get_code_reviewer(workspace_root: Optional[str] = None, brain=None) -> CodeReviewer:
    """Get or create global code reviewer instance"""
    global _reviewer_instance
    if _reviewer_instance is None:
        _reviewer_instance = CodeReviewer(workspace_root, brain)
    return _reviewer_instance
