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
            
            code_blocks.append({
                'language': language.lower(),
                'content': content,
                'start_pos': match.start(),
                'end_pos': match.end()
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
        
        if language in ['bash', 'sh', 'shell', 'zsh']:
            # For shell scripts, split by newlines and filter
            lines = code_content.split('\n')
            for line in lines:
                line = line.strip()
                # Skip comments and empty lines
                if line and not line.startswith('#'):
                    # Handle multi-line commands (ending with \)
                    if line.endswith('\\'):
                        # Combine with next line
                        continue
                    commands.append(line)
        
        elif language == 'python':
            # For Python, execute as a script file (not line by line)
            # Python code blocks should be executed as complete scripts
            if code_content.strip():
                # Write to temp file and execute it
                import tempfile
                import os
                temp_file = None
                try:
                    # Create temp file in workspace or system temp
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                        f.write(code_content)
                        temp_file = f.name
                    # Execute the temp file
                    commands.append(f"python3 {temp_file}")
                    # Store temp file path for cleanup (will be handled by command executor)
                except Exception as e:
                    logger.warning(f"Error creating temp file for Python code: {e}")
                    # Fallback: try python -c with proper escaping
                    escaped = code_content.replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')
                    # Use triple quotes for multi-line
                    commands.append(f'python3 -c """{escaped}"""')
        
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
