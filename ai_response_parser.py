# -*- coding: utf-8 -*-
"""
AI Response Parser - Parse AI responses and extract commands, detect task completion
"""

import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class AIResponseParser:
    """Parse AI responses to extract commands and detect task status"""
    
    def __init__(self):
        """Initialize AI response parser"""
        logger.info("AI Response Parser initialized")
    
    def parse_ai_response(self, response_text: str) -> Dict[str, Any]:
        """
        Parse AI response into structured components
        
        Args:
            response_text: Full AI response text
        
        Returns:
            Dictionary with:
            - 'thinking': Explanation/thinking text
            - 'code_blocks': List of code blocks
            - 'commands': List of extracted commands
            - 'expected_results': Expected results mentioned
            - 'is_complete': Whether task is marked complete
            - 'is_long_running': Whether task is long-running
        """
        parsed = {
            'thinking': '',
            'code_blocks': [],
            'commands': [],
            'expected_results': [],
            'is_complete': False,
            'is_long_running': False
        }
        
        # Detect task completion
        parsed['is_complete'] = self.detect_task_completion(response_text)
        
        # Detect long-running task
        parsed['is_long_running'] = self.detect_long_running_task(response_text)
        
        # Extract code blocks
        code_blocks = self._extract_code_blocks(response_text)
        parsed['code_blocks'] = code_blocks
        
        # Extract commands from code blocks
        for block in code_blocks:
            # If block has heredoc, treat as single shell command (don't parse Python inside)
            if block.get('has_heredoc', False):
                # Extract the shell command line (before << EOF)
                heredoc_match = re.search(r'^(.*?)\s*<<\s*[\'"]?EOF', block['content'], re.DOTALL | re.IGNORECASE)
                if heredoc_match:
                    shell_command = heredoc_match.group(1).strip()
                    # Get everything from start to EOF (including heredoc content)
                    full_heredoc_match = re.search(r'(.*?<<\s*[\'"]?EOF.*?EOF)', block['content'], re.DOTALL | re.IGNORECASE)
                    if full_heredoc_match:
                        # Treat entire heredoc as single command
                        parsed['commands'].append(full_heredoc_match.group(1).strip())
                    else:
                        parsed['commands'].append(block['content'])
                else:
                    parsed['commands'].append(block['content'])
            else:
                commands = self.extract_commands(block['content'], block['language'])
                parsed['commands'].extend(commands)
        
        # Extract thinking/explanation (text outside code blocks)
        parsed['thinking'] = self._extract_thinking_text(response_text, code_blocks)
        
        # Extract expected results
        parsed['expected_results'] = self._extract_expected_results(response_text)
        
        logger.debug(f"Parsed response: {len(parsed['commands'])} commands, "
                    f"complete: {parsed['is_complete']}, "
                    f"long_running: {parsed['is_long_running']}")
        
        return parsed
    
    def _extract_code_blocks(self, text: str) -> List[Dict[str, Any]]:
        """Extract all code blocks from text"""
        code_blocks = []
        
        # Pattern to match markdown code blocks
        pattern = r'```(\w+)?\n(.*?)```'
        
        matches = re.finditer(pattern, text, re.DOTALL)
        
        for match in matches:
            language = match.group(1) or 'bash'
            content = match.group(2).strip()
            
            # Check if content contains heredoc (cat > file << 'EOF' or similar)
            # If so, treat entire block as shell command, don't extract Python from inside
            has_heredoc = bool(re.search(r'<<\s*[\'"]?EOF[\'"]?', content, re.IGNORECASE))
            if has_heredoc:
                # Force language to bash/shell for heredoc blocks
                language = 'bash'
            
            code_blocks.append({
                'language': language.lower(),
                'content': content,
                'start_pos': match.start(),
                'end_pos': match.end(),
                'has_heredoc': has_heredoc
            })
        
        return code_blocks
    
    def extract_commands(self, code_content: str, language: str = 'bash') -> List[str]:
        """
        Extract executable commands from code block content
        
        Args:
            code_content: Content of code block
            language: Language of code block (bash, python, etc.)
        
        Returns:
            List of executable commands
        """
        commands = []
        
        # Check if Python code block contains shell commands (like "cd /app && python -c")
        # If so, treat as shell command instead
        if language == 'python' and ('cd ' in code_content or 'python -c' in code_content or 'python3 -c' in code_content or '&&' in code_content):
            logger.info("Python code block contains shell commands, treating as shell")
            language = 'bash'
        
        if language in ['bash', 'sh', 'shell', 'zsh']:
            # For shell scripts, handle multi-line commands properly
            lines = code_content.split('\n')
            current_command = []
            
            for line in lines:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                
                # Handle multi-line commands (ending with \)
                if line.endswith('\\'):
                    current_command.append(line.rstrip('\\').strip())
                    continue
                
                # Handle python -c with multi-line strings
                if 'python' in line and '-c' in line and '"' in line:
                    # Extract Python code from python -c "..."
                    # This is a shell command that contains Python code
                    commands.append(line)
                    continue
                
                # Add to current command or start new one
                if current_command:
                    current_command.append(line)
                    commands.append(' '.join(current_command))
                    current_command = []
                else:
                    commands.append(line)
            
            # Add any remaining command
            if current_command:
                commands.append(' '.join(current_command))
        
        elif language == 'python':
            # For Python, execute as a script file (not line by line)
            # Python code blocks should be executed as complete scripts
            if code_content.strip():
                # Write to temp file and execute it
                import tempfile
                import os
                temp_file = None
                try:
                    # Create temp file in workspace or system temp (Linux compatible)
                    # Use /tmp on Linux, or system temp on Windows
                    import sys
                    if sys.platform == 'linux' or sys.platform.startswith('linux'):
                        temp_dir = '/tmp'
                    else:
                        temp_dir = tempfile.gettempdir()
                    
                    # Create temp file with proper permissions
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, dir=temp_dir) as f:
                        f.write(code_content)
                        temp_file = f.name
                        # Make executable on Linux
                        if sys.platform == 'linux' or sys.platform.startswith('linux'):
                            os.chmod(temp_file, 0o755)
                    
                    # Execute the temp file (use absolute path for Linux)
                    command = f"python3 {temp_file}"
                    commands.append(command)
                    logger.info(f"Created Python temp script: {temp_file} -> {command}")
                    # Store temp file path for cleanup (will be handled by command executor)
                except Exception as e:
                    logger.error(f"Error creating temp file for Python code: {e}", exc_info=True)
                    # Fallback: try python -c with proper escaping (single line only)
                    if code_content.strip():
                        logger.warning("Falling back to python -c (may fail for multi-line code)")
                        # Escape properly for shell
                        escaped = code_content.replace('"', '\\"').replace('$', '\\$').replace('`', '\\`').replace('\n', '; ')
                        commands.append(f'python3 -c "{escaped}"')
        
        else:
            # For other languages, treat as single command
            if code_content.strip():
                commands.append(code_content.strip())
        
        # Filter out empty commands
        commands = [cmd for cmd in commands if cmd.strip()]
        
        return commands
    
    def detect_task_completion(self, response_text: str) -> bool:
        """
        Detect if AI says task is complete
        
        Args:
            response_text: AI response text
        
        Returns:
            True if task appears complete
        """
        text_lower = response_text.lower()
        
        # Completion indicators
        completion_phrases = [
            'task complete',
            'task completed',
            'done',
            'finished',
            'completed successfully',
            'all done',
            'task is complete',
            'task finished',
            'successfully completed',
            'completed the task',
            'delivered',
            'results delivered',
            'final results',
            'here are the results',
            'task accomplished'
        ]
        
        # Check for completion phrases
        for phrase in completion_phrases:
            if phrase in text_lower:
                logger.debug(f"Task completion detected: '{phrase}'")
                return True
        
        # Check for "no more commands" indicators
        no_more_indicators = [
            'no more commands',
            'no further steps',
            'nothing else to do',
            'all steps complete',
            'all tasks done'
        ]
        
        for indicator in no_more_indicators:
            if indicator in text_lower:
                logger.debug(f"Task completion detected (no more steps): '{indicator}'")
                return True
        
        return False
    
    def detect_long_running_task(self, response_text: str) -> bool:
        """
        Detect if task is long-running (scans, etc.)
        
        Args:
            response_text: AI response text
        
        Returns:
            True if task appears to be long-running
        """
        text_lower = response_text.lower()
        
        # Long-running task indicators
        long_running_phrases = [
            'scan',
            'scanning',
            'may take',
            'will take',
            'estimated',
            'minutes',
            'hours',
            'long-running',
            'background',
            'nuclei',
            'sqlmap',
            'nikto',
            'gobuster',
            'ffuf',
            'amass',
            'subfinder',
            'reconnaissance',
            'enumeration',
            'brute force',
            'crawling',
            'fuzzing'
        ]
        
        # Check for long-running indicators
        for phrase in long_running_phrases:
            if phrase in text_lower:
                logger.debug(f"Long-running task detected: '{phrase}'")
                return True
        
        # Check for time estimates
        time_patterns = [
            r'\d+\s*(?:minutes?|mins?|hours?|hrs?)',
            r'take\s+\d+',
            r'estimated\s+\d+'
        ]
        
        for pattern in time_patterns:
            if re.search(pattern, text_lower):
                logger.debug(f"Long-running task detected (time estimate)")
                return True
        
        return False
    
    def _extract_thinking_text(self, response_text: str, code_blocks: List[Dict]) -> str:
        """Extract thinking/explanation text (outside code blocks)"""
        if not code_blocks:
            return response_text.strip()
        
        # Remove code blocks from text
        text = response_text
        # Sort code blocks by position (reverse to maintain indices)
        sorted_blocks = sorted(code_blocks, key=lambda x: x['start_pos'], reverse=True)
        
        for block in sorted_blocks:
            text = text[:block['start_pos']] + text[block['end_pos']:]
        
        return text.strip()
    
    def _extract_expected_results(self, response_text: str) -> List[str]:
        """Extract expected results mentioned in response"""
        results = []
        
        # Patterns for expected results
        patterns = [
            r'expected[:\s]+(.+?)(?:\.|$)',
            r'result[:\s]+(.+?)(?:\.|$)',
            r'output[:\s]+(.+?)(?:\.|$)',
            r'will generate[:\s]+(.+?)(?:\.|$)',
            r'will create[:\s]+(.+?)(?:\.|$)',
            r'will produce[:\s]+(.+?)(?:\.|$)'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, response_text, re.IGNORECASE)
            results.extend(matches)
        
        # Clean up results
        results = [r.strip() for r in results if r.strip()]
        
        return results


# Global instance
_ai_response_parser_instance = None

def get_ai_response_parser() -> AIResponseParser:
    """Get or create global AI response parser instance"""
    global _ai_response_parser_instance
    if _ai_response_parser_instance is None:
        _ai_response_parser_instance = AIResponseParser()
    return _ai_response_parser_instance
