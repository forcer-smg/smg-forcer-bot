# -*- coding: utf-8 -*-
"""
File Generator - Detects code blocks in AI responses and generates files
Sends files to Telegram instead of displaying code in chat
"""

import os
import re
import tempfile
import ast
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# File extension mapping based on language markers
LANGUAGE_EXTENSIONS = {
    'python': '.py',
    'py': '.py',
    'javascript': '.js',
    'js': '.js',
    'typescript': '.ts',
    'ts': '.ts',
    'html': '.html',
    'css': '.css',
    'json': '.json',
    'xml': '.xml',
    'yaml': '.yaml',
    'yml': '.yml',
    'markdown': '.md',
    'md': '.md',
    'bash': '.sh',
    'shell': '.sh',
    'sh': '.sh',
    'powershell': '.ps1',
    'ps1': '.ps1',
    'sql': '.sql',
    'java': '.java',
    'cpp': '.cpp',
    'c': '.c',
    'go': '.go',
    'rust': '.rs',
    'php': '.php',
    'ruby': '.rb',
    'txt': '.txt',
    'text': '.txt',
    'log': '.log',
    'ini': '.ini',
    'conf': '.conf',
    'config': '.config',
    'env': '.env',
    'dockerfile': 'Dockerfile',
    'makefile': 'Makefile',
}


class FileGenerator:
    """Generates files from code blocks in AI responses and documents"""
    
    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.temp_files = []  # Track generated files for cleanup
        
        # Document generator (lazy import)
        self._doc_gen = None
    
    def generate_advanced_code_prompt(self, task: str, language: str) -> str:
        """Generate prompt for advanced code generation"""
        return f"""
Generate ADVANCED, PRODUCTION-GRADE code for: {task}
Language: {language}

REQUIREMENTS (MANDATORY):
1. NO BASIC CODE - Use advanced patterns, design patterns, sophisticated algorithms
2. PRODUCTION READY - Error handling, logging, monitoring, scalability
3. OPTIMIZED - Performance, memory, efficiency considerations
4. SECURE - Input validation, sanitization, secure coding practices
5. MAINTAINABLE - Clean architecture, SOLID principles, documentation
6. ADVANCED FEATURES - Use language-specific advanced features

DO NOT:
- Use basic loops without optimization
- Skip error handling
- Use simple data structures when advanced ones are better
- Write code that looks like a tutorial
- Skip security considerations
- Use basic stdlib only (use advanced libraries)

DO:
- Use advanced algorithms (dynamic programming, graph theory, optimization)
- Implement proper design patterns (Factory, Strategy, Observer, etc.)
- Add comprehensive error handling with try/except/finally
- Use async/await, generators, decorators, context managers appropriately
- Implement proper logging and monitoring
- Add type hints, docstrings, comprehensive documentation
- Use advanced libraries and frameworks
- Implement proper security (input validation, sanitization)
- Add comprehensive tests if applicable
- Use advanced data structures (deque, defaultdict, Counter, etc.)
- Optimize for performance and memory efficiency
"""
    
    def validate_code_quality(self, code: str, language: str) -> Dict:
        """Validate that code is advanced, not basic"""
        quality_issues = []
        quality_score = 100
        
        code_lower = code.lower()
        
        # Check for basic patterns that indicate simple code
        basic_patterns = [
            (r'print\s*\(["\']hello', 'Basic hello world pattern'),
            (r'print\s*\(["\']world', 'Basic hello world pattern'),
            (r'def\s+\w+\s*\(\)\s*:\s*\n\s*pass', 'Empty function without implementation'),
            (r'for\s+\w+\s+in\s+range\s*\(\s*\d+\s*\)\s*:\s*\n\s*print', 'Basic loop without purpose'),
        ]
        
        for pattern, issue in basic_patterns:
            if re.search(pattern, code, re.IGNORECASE | re.MULTILINE):
                quality_issues.append(issue)
                quality_score -= 20
        
        # Check for advanced patterns (positive indicators)
        advanced_patterns = [
            (r'@\w+', 'Decorators used'),
            (r'async\s+def', 'Async/await used'),
            (r'yield', 'Generators used'),
            (r'class\s+\w+.*:', 'Classes defined'),
            (r'from\s+\w+\s+import', 'External libraries used'),
            (r'try:\s*\n.*except', 'Error handling present'),
            (r'logging\.', 'Logging used'),
            (r'type:\s*\w+', 'Type hints used'),
            (r'def\s+\w+.*->\s*\w+:', 'Return type hints'),
        ]
        
        advanced_count = sum(1 for pattern, _ in advanced_patterns if re.search(pattern, code, re.IGNORECASE | re.MULTILINE))
        
        # Require at least 3 advanced patterns
        if advanced_count < 3:
            quality_issues.append(f'Code lacks advanced patterns (found {advanced_count}, need at least 3)')
            quality_score -= (3 - advanced_count) * 10
        
        # Check for error handling
        if language.lower() in ['python', 'py']:
            if 'try:' not in code and 'except' not in code:
                if len(code.split('\n')) > 20:  # Only require for longer code
                    quality_issues.append('Missing error handling for production code')
                    quality_score -= 15
        
        # Check for documentation
        if '"""' not in code and "'''" not in code:
            if len(code.split('\n')) > 30:  # Only require for longer code
                quality_issues.append('Missing docstrings/documentation')
                quality_score -= 10
        
        return {
            'is_advanced': quality_score >= 70,
            'quality_score': quality_score,
            'issues': quality_issues,
            'advanced_patterns_found': advanced_count
        }
    
    def detect_code_blocks(self, text: str) -> List[Dict]:
        """
        Detect code blocks in text
        Returns list of dicts with: content, language, filename, extension
        Also handles bash heredoc commands that create files
        """
        code_blocks = []
        
        # Pattern for code blocks: ```language\ncode\n```
        code_block_pattern = r'```(?:(\w+))?\n(.*?)```'
        matches = re.finditer(code_block_pattern, text, re.DOTALL | re.IGNORECASE)
        
        for match in matches:
            language = match.group(1) or 'txt'
            content = match.group(2).strip()
            
            if not content:
                continue
            
            # Check if this is a bash heredoc creating a file (cat > file.py << 'EOF')
            # Extract the actual code from heredoc
            heredoc_pattern = r'cat\s+>\s+([^\s]+)\s+<<\s+[\'"]?EOF[\'"]?\s*\n(.*?)\nEOF'
            heredoc_match = re.search(heredoc_pattern, content, re.DOTALL | re.IGNORECASE)
            if heredoc_match:
                target_file = heredoc_match.group(1).strip()
                actual_code = heredoc_match.group(2).strip()
                
                # Determine language from file extension
                file_ext = Path(target_file).suffix.lower()
                if file_ext == '.py':
                    language = 'python'
                elif file_ext == '.js':
                    language = 'javascript'
                elif file_ext == '.ts':
                    language = 'typescript'
                else:
                    language = 'txt'
                
                # Use the target filename
                filename = os.path.basename(target_file)
                extension = file_ext or self._get_extension(language)
                
                code_blocks.append({
                    'content': actual_code,
                    'language': language.lower(),
                    'filename': filename,
                    'extension': extension,
                    'full_path': None
                })
                continue
            
            # Determine file extension
            extension = self._get_extension(language)
            
            # Generate filename
            filename = self._generate_filename(content, language, extension)
            
            code_blocks.append({
                'content': content,
                'language': language.lower(),
                'filename': filename,
                'extension': extension,
                'full_path': None  # Will be set when file is created
            })
        
        return code_blocks
    
    def _get_extension(self, language: str) -> str:
        """Get file extension from language marker"""
        lang_lower = language.lower() if language else 'txt'
        return LANGUAGE_EXTENSIONS.get(lang_lower, '.txt')
    
    def _generate_filename(self, content: str, language: str, extension: str) -> str:
        """Generate appropriate filename based on content"""
        # Try to extract filename from content (common patterns)
        # Pattern 1: # filename.py or # File: filename.py
        filename_patterns = [
            r'#\s*(?:file|filename|name):\s*([^\s]+)',
            r'//\s*(?:file|filename|name):\s*([^\s]+)',
            r'/\*\s*(?:file|filename|name):\s*([^\s]+)',
        ]
        
        for pattern in filename_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                suggested_name = match.group(1).strip()
                # Ensure it has proper extension
                if not suggested_name.endswith(extension):
                    suggested_name += extension
                return suggested_name
        
        # Pattern 2: Look for class/function names that might indicate filename
        if language in ['python', 'py']:
            class_match = re.search(r'class\s+(\w+)', content)
            if class_match:
                return f"{class_match.group(1).lower()}{extension}"
            
            func_match = re.search(r'def\s+(\w+)', content)
            if func_match:
                return f"{func_match.group(1).lower()}{extension}"
        
        # Pattern 3: Look for module/package names
        if 'package' in content.lower() or 'module' in content.lower():
            module_match = re.search(r'(?:package|module)\s+([\w.]+)', content, re.IGNORECASE)
            if module_match:
                return f"{module_match.group(1).split('.')[-1]}{extension}"
        
        # Default: Generate based on language and timestamp
        import time
        timestamp = int(time.time())
        return f"generated_{language}_{timestamp}{extension}"
    
    def validate_code(self, code: str, language: str) -> Dict:
        """
        Validate code for syntax errors and missing imports
        Returns dict with: valid, errors, warnings, missing_imports
        """
        validation_result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'missing_imports': []
        }
        
        # Python validation
        if language in ['python', 'py']:
            try:
                # Syntax validation
                compile(code, '<string>', 'exec')
            except SyntaxError as e:
                validation_result['valid'] = False
                validation_result['errors'].append(f"Syntax error: {str(e)}")
            except Exception as e:
                validation_result['warnings'].append(f"Compilation warning: {str(e)}")
            
            # Check for missing imports (basic check)
            import re
            import_pattern = r'^(?:from\s+(\S+)\s+)?import\s+(\S+)'
            used_modules = set()
            
            # Find all imports
            imports = re.findall(import_pattern, code, re.MULTILINE)
            for module in imports:
                if module[0]:  # from X import Y
                    used_modules.add(module[0])
                if module[1]:  # import X
                    used_modules.add(module[1].split('.')[0])
            
            # Check for common modules that might be missing
            common_modules = ['requests', 'beautifulsoup4', 'selenium', 'playwright', 'numpy', 'pandas', 'pytorch', 'tensorflow']
            for module in common_modules:
                if module in code.lower() and module not in used_modules:
                    # Check if it's actually used (not just in comments)
                    if re.search(rf'\b{module}\b', code, re.IGNORECASE):
                        # Check if imported
                        if not re.search(rf'^(?:from\s+{module}|import\s+{module})', code, re.MULTILINE | re.IGNORECASE):
                            validation_result['missing_imports'].append(module)
        
        return validation_result
    
    def generate_files(self, code_blocks: List[Dict], subdirectory: Optional[str] = None, validate: bool = True) -> List[Dict]:
        """
        Generate actual files from code blocks
        validate: If True, validate code for errors before generating
        Returns list of dicts with file paths and metadata
        """
        generated_files = []
        base_dir = self.workspace_root
        
        if subdirectory:
            base_dir = base_dir / subdirectory
            base_dir.mkdir(parents=True, exist_ok=True)
        
        for block in code_blocks:
            try:
                # Validate code before generating file
                validation_result = None
                quality_result = None
                if validate:
                    validation_result = self.validate_code(block['content'], block['language'])
                    block['validation'] = validation_result
                    
                    # Also validate code quality (advanced vs basic)
                    quality_result = self.validate_code_quality(block['content'], block['language'])
                    block['quality'] = quality_result
                    
                    if not validation_result['valid']:
                        logger.warning(f"Code validation failed for {block['filename']}: {validation_result['errors']}")
                    if validation_result['missing_imports']:
                        logger.info(f"Missing imports detected in {block['filename']}: {validation_result['missing_imports']}")
                    
                    # Warn if code is too basic
                    if quality_result and not quality_result['is_advanced']:
                        logger.warning(f"Code quality check: {block['filename']} may be too basic. Quality score: {quality_result['quality_score']}/100. Issues: {quality_result['issues']}")
                        block['quality_warning'] = f"Code may be too basic. Quality score: {quality_result['quality_score']}/100"
                
                file_path = base_dir / block['filename']
                
                # Handle special cases (Dockerfile, Makefile have no extension)
                if block['extension'] in ['Dockerfile', 'Makefile']:
                    file_path = base_dir / block['extension']
                
                # Write file
                file_path.write_text(block['content'], encoding='utf-8')
                
                block['full_path'] = str(file_path)
                generated_files.append(block)
                
                logger.info(f"Generated file: {file_path}")
                
            except Exception as e:
                logger.error(f"Failed to generate file {block['filename']}: {e}")
                block['error'] = str(e)
        
        # Track for cleanup
        self.temp_files.extend([f['full_path'] for f in generated_files if f.get('full_path')])
        
        return generated_files
    
    def detect_document_request(self, text: str, user_message: str = "") -> Optional[Dict]:
        """
        Detect if user wants a document (PDF, Word, Excel) instead of code
        
        Args:
            text: AI response text
            user_message: Original user message
        
        Returns:
            Dict with document type and content, or None if not a document request
        """
        combined_text = (user_message + " " + text).lower()
        
        # Document keywords
        doc_keywords = {
            'pdf': ['pdf', 'document pdf', 'generate pdf', 'create pdf', 'pdf file', 'pdf document'],
            'word': ['word', 'docx', 'document word', 'generate word', 'create word', 'word file', 'word document', '.docx'],
            'excel': ['excel', 'xlsx', 'spreadsheet', 'generate excel', 'create excel', 'excel file', '.xlsx', 'table data']
        }
        
        # Check for document requests
        for doc_type, keywords in doc_keywords.items():
            if any(keyword in combined_text for keyword in keywords):
                # Extract content (everything after document type mention or from AI response)
                content = text
                
                # Try to extract structured content from markdown
                if '```' in text:
                    # Has code blocks - might be structured data
                    pass
                
                return {
                    'type': doc_type,
                    'content': content,
                    'title': self._extract_title(user_message, text)
                }
        
        return None
    
    def generate_document(self, doc_request: Dict, filename: str = None) -> Optional[str]:
        """
        Generate document from request
        
        Args:
            doc_request: Dict with 'type', 'content', 'title'
            filename: Optional filename
        
        Returns:
            Path to generated document or None
        """
        try:
            if not self._doc_gen:
                from document_generator import get_document_generator
                self._doc_gen = get_document_generator(str(self.workspace_root / "documents"))
            
            doc_type = doc_request['type']
            content = doc_request['content']
            title = doc_request.get('title')
            
            if doc_type == 'pdf':
                return self._doc_gen.generate_pdf(content, filename=filename, title=title)
            elif doc_type == 'word':
                return self._doc_gen.generate_word(content, filename=filename, title=title)
            elif doc_type == 'excel':
                # Convert content to table format
                rows = self._content_to_table(content)
                return self._doc_gen.generate_excel(rows, filename=filename)
            else:
                logger.warning(f"Unknown document type: {doc_type}")
                return None
                
        except Exception as e:
            logger.error(f"Error generating document: {e}", exc_info=True)
            return None
    
    def _extract_title(self, user_message: str, text: str) -> Optional[str]:
        """Extract document title from user message or text"""
        # Look for title patterns
        title_patterns = [
            r'title[:\s]+([^\n]+)',
            r'create\s+(?:a\s+)?(?:pdf|word|excel|document)\s+(?:called|named|titled)?\s+["\']?([^"\'\n]+)["\']?',
            r'generate\s+(?:a\s+)?(?:pdf|word|excel|document)\s+(?:called|named|titled)?\s+["\']?([^"\'\n]+)["\']?'
        ]
        
        for pattern in title_patterns:
            match = re.search(pattern, user_message, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # Default title
        return "Generated Document"
    
    def _content_to_table(self, content: str) -> List[List[str]]:
        """Convert text content to table format for Excel"""
        rows = []
        
        # Try to detect table structure
        if '|' in content:
            # Markdown table
            lines = content.split('\n')
            for line in lines:
                if '|' in line and not line.strip().startswith('|---'):
                    cells = [cell.strip() for cell in line.split('|') if cell.strip()]
                    if cells:
                        rows.append(cells)
        elif '\t' in content:
            # Tab-separated
            for line in content.split('\n'):
                if line.strip():
                    rows.append(line.split('\t'))
        elif ',' in content:
            # CSV-like
            for line in content.split('\n'):
                if line.strip():
                    rows.append([cell.strip() for cell in line.split(',')])
        else:
            # One column per line
            for line in content.split('\n'):
                if line.strip():
                    rows.append([line.strip()])
        
        return rows if rows else [['No data']]
    
    def format_validation_report(self, generated_files: List[Dict]) -> str:
        """Format validation results as a readable report"""
        if not generated_files:
            return ""
        
        report_lines = []
        has_issues = False
        
        for file_info in generated_files:
            filename = file_info.get('filename', 'unknown')
            validation = file_info.get('validation')
            
            if not validation:
                continue
            
            if not validation['valid'] or validation['errors'] or validation['missing_imports']:
                has_issues = True
                report_lines.append(f"\n📄 **{filename}:**")
                
                if validation['errors']:
                    for error in validation['errors']:
                        report_lines.append(f"  ❌ {error}")
                
                if validation['missing_imports']:
                    imports_str = ', '.join(validation['missing_imports'])
                    report_lines.append(f"  ⚠️ Missing imports: {imports_str}")
                    report_lines.append(f"  💡 Install with: `pip install {imports_str}`")
        
        if has_issues:
            return "\n".join(report_lines)
        return ""
    
    def remove_code_blocks_from_text(self, text: str, code_blocks: List[Dict]) -> str:
        """Remove code blocks from text, replacing with file references"""
        result = text
        
        for block in code_blocks:
            # Skip if this is a plan file (doesn't have language/content)
            if block.get('type') == 'plan':
                continue
            
            # Get language - handle both code blocks and file info dicts
            language = block.get('language', 'code')
            content = block.get('content', '')
            
            # If no content, this is a file info dict, not a code block - skip replacement
            if not content:
                continue
            
            # Escape special regex characters
            escaped_content = re.escape(content)
            
            # Pattern to match the exact code block
            pattern = rf'```{re.escape(language)}\n{escaped_content}\n```'
            
            # Replace with clean file reference
            filename = block.get('filename', 'unknown')
            file_size = len(content)
            size_kb = file_size / 1024
            
            # Get validation status if available
            validation = block.get('validation', {})
            status_icon = "✅" if validation.get('valid', True) and not validation.get('errors') else "⚠️"
            
            replacement = f"📄 **{filename}** {status_icon}\n   Language: {language} | Size: {size_kb:.1f}KB\n"
            
            result = re.sub(pattern, replacement, result, flags=re.DOTALL)
        
        return result
    
    def cleanup_files(self, file_paths: Optional[List[str]] = None):
        """Clean up generated files"""
        files_to_remove = file_paths or self.temp_files
        
        for file_path in files_to_remove:
            try:
                path = Path(file_path)
                if path.exists():
                    path.unlink()
                    logger.info(f"Cleaned up file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup file {file_path}: {e}")
        
        if not file_paths:
            self.temp_files.clear()
    
    def is_command_file(self, code_block: Dict) -> bool:
        """Check if code block is just commands, not actual code to save"""
        content = code_block.get('content', '')
        language = code_block.get('language', '').lower()
        filename = code_block.get('filename', '').lower()
        
        # .sh files that are just command sequences
        if language in ['bash', 'sh', 'shell']:
            # Check if filename suggests it's a generated wrapper script
            if 'generated' in filename and ('bash' in filename or 'sh' in filename):
                # Check if it contains heredoc with Python code (wrapper script)
                heredoc_pattern = r'cat\s+>\s+[^\s]+\.py\s+<<\s+[\'"]?EOF'
                if re.search(heredoc_pattern, content, re.IGNORECASE):
                    # This is a bash wrapper for Python code - filter it out
                    logger.info(f"Filtering bash wrapper script: {filename} (contains Python heredoc)")
                    return True
            
            # Check if it's mostly commands (cd, git, pip, etc.) vs actual script
            command_patterns = [
                r'^cd\s+', r'^git\s+', r'^pip\s+', r'^npm\s+', 
                r'^python\s+', r'^\./', r'^echo\s+', r'^ls\s+',
                r'^cat\s+', r'^curl\s+', r'^wget\s+', r'^mkdir\s+',
                r'^rm\s+', r'^mv\s+', r'^cp\s+', r'^chmod\s+',
                r'^export\s+', r'^source\s+', r'^\.\s+', r'^bash\s+',
                r'^chmod\s+\+x', r'^\.\/', r'^exec\s+', r'^eval\s+'
            ]
            
            lines = content.split('\n')
            command_lines = 0
            total_non_comment_lines = 0
            python_code_lines = 0  # Count lines that look like Python code
            
            for line in lines:
                line_stripped = line.strip()
                if not line_stripped or line_stripped.startswith('#'):
                    continue
                total_non_comment_lines += 1
                
                # Check if line is a command
                if any(re.match(pattern, line_stripped) for pattern in command_patterns):
                    command_lines += 1
                
                # Check if line looks like Python code (indented, has Python keywords)
                python_keywords = ['def ', 'class ', 'import ', 'from ', 'if ', 'for ', 'while ', 'try:', 'except', 'return ', 'print(']
                if any(keyword in line_stripped for keyword in python_keywords):
                    python_code_lines += 1
            
            # If >70% of non-comment lines are commands, it's a command file
            if total_non_comment_lines > 0:
                command_ratio = command_lines / total_non_comment_lines
                python_ratio = python_code_lines / total_non_comment_lines if total_non_comment_lines > 0 else 0
                
                # If it's mostly commands AND has little Python code, it's a command file
                if command_ratio > 0.7 and python_ratio < 0.2:
                    logger.info(f"Filtering command file: {filename} (command ratio: {command_ratio:.2f}, python ratio: {python_ratio:.2f})")
                    return True
        
        return False
    
    def filter_and_prioritize_blocks(self, code_blocks: List[Dict], user_message: str = "") -> List[Dict]:
        """
        Filter out command files and prioritize code blocks based on user request.
        If user asks for Python, filter out bash scripts and prioritize Python files.
        """
        # Detect if user explicitly asked for Python code
        user_wants_python = any(keyword in user_message.lower() for keyword in [
            'python', 'py ', '.py', 'python code', 'python script', 
            'python file', 'write python', 'create python', 'generate python'
        ])
        
        filtered_blocks = []
        python_files = []
        other_files = []
        
        for block in code_blocks:
            # Skip command files
            if self.is_command_file(block):
                logger.info(f"Skipping command file: {block.get('filename', 'unknown')}")
                continue
            
            # If user wants Python, prioritize Python files and filter bash scripts
            if user_wants_python:
                block_lang = block.get('language', '').lower()
                block_ext = block.get('extension', '').lower()
                
                # Filter out bash scripts when Python is requested
                if block_lang in ['bash', 'sh', 'shell'] or block_ext in ['.sh', '.bash']:
                    logger.info(f"Filtering bash script when Python requested: {block.get('filename', 'unknown')}")
                    continue
                
                # Prioritize Python files
                if block_lang in ['python', 'py'] or block_ext == '.py':
                    python_files.append(block)
                else:
                    other_files.append(block)
            else:
                # No specific request - include all non-command files
                filtered_blocks.append(block)
        
        # If user wants Python, prioritize Python files
        if user_wants_python:
            filtered_blocks = python_files + other_files
            if python_files:
                logger.info(f"Prioritizing {len(python_files)} Python file(s) for Python code request")
        
        return filtered_blocks
    
    def should_send_as_file(self, text: str, min_lines: int = 10) -> bool:
        """
        Determine if response should be sent as file instead of text
        Based on length and code block presence
        """
        # Check for code blocks
        code_blocks = self.detect_code_blocks(text)
        if code_blocks:
            # If any code block is substantial, send as file
            for block in code_blocks:
                if len(block['content'].split('\n')) >= min_lines:
                    return True
        
        # Check total text length
        if len(text) > 3000:  # Telegram message limit is 4096, but we want margin
            return True
        
        return False
    
    def format_file_list_message(self, files: List[Dict]) -> str:
        """Format a message listing generated files"""
        if not files:
            return ""
        
        message = "📁 **Generated Files:**\n\n"
        for i, file_info in enumerate(files, 1):
            filename = file_info.get('filename', 'unknown')
            language = file_info.get('language', 'text')
            message += f"{i}. `{filename}` ({language})\n"
        
        return message
    
    def _extract_imports(self, file_path: Path) -> List[str]:
        """Extract import statements from Python file using AST"""
        imports = set()
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse with AST
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.add(alias.name.split('.')[0])
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            imports.add(node.module.split('.')[0])
            except SyntaxError:
                # Fallback to regex if AST fails
                import_pattern = r'^(?:from\s+(\S+)\s+)?import\s+(\S+)'
                matches = re.findall(import_pattern, content, re.MULTILINE)
                for match in matches:
                    if match[0]:  # from X import Y
                        imports.add(match[0].split('.')[0])
                    if match[1]:  # import X
                        imports.add(match[1].split('.')[0])
        except Exception as e:
            logger.warning(f"Error extracting imports from {file_path}: {e}")
        
        return list(imports)
    
    def _filter_third_party_packages(self, imports: List[str]) -> List[str]:
        """Filter out standard library packages"""
        # Python standard library modules (common ones)
        stdlib_modules = {
            'os', 'sys', 're', 'json', 'datetime', 'time', 'random', 'math', 'collections',
            'itertools', 'functools', 'operator', 'string', 'textwrap', 'unicodedata',
            'stringprep', 'readline', 'rlcompleter', 'struct', 'codecs', 'types',
            'copy', 'pprint', 'reprlib', 'enum', 'numbers', 'cmath', 'decimal', 'fractions',
            'statistics', 'array', 'bisect', 'heapq', 'weakref', 'copyreg', 'pickle',
            'pickletools', 'shelve', 'marshal', 'dbm', 'sqlite3', 'zlib', 'gzip',
            'bz2', 'lzma', 'zipfile', 'tarfile', 'csv', 'configparser', 'netrc',
            'xdrlib', 'plistlib', 'hashlib', 'hmac', 'secrets', 'io', 'argparse',
            'getopt', 'logging', 'getpass', 'curses', 'platform', 'errno', 'ctypes',
            'threading', 'multiprocessing', 'concurrent', 'subprocess', 'sched',
            'queue', 'select', 'selectors', 'asyncio', 'socket', 'ssl', 'email',
            'json', 'mailcap', 'mailbox', 'mimetypes', 'base64', 'binhex', 'binascii',
            'quopri', 'uu', 'html', 'xml', 'urllib', 'http', 'ftplib', 'poplib',
            'imaplib', 'nntplib', 'smtplib', 'smtpd', 'telnetlib', 'uuid', 'socketserver',
            'xmlrpc', 'ipaddress', 'audioop', 'aifc', 'sunau', 'wave', 'chunk',
            'colorsys', 'imghdr', 'sndhdr', 'ossaudiodev', 'gettext', 'locale',
            'cmd', 'shlex', 'tkinter', 'turtle', 'pydoc', 'doctest', 'unittest',
            'test', 'lib2to3', 'typing', 'pydoc_data', 'distutils', 'ensurepip',
            'venv', 'zipapp', 'faulthandler', 'pdb', 'profile', 'pstats', 'timeit',
            'trace', 'tracemalloc', 'gc', 'inspect', 'site', 'fpectl', 'warnings',
            'contextlib', 'abc', 'atexit', 'traceback', 'future', 'builtins',
            'importlib', 'keyword', 'parser', 'ast', 'symtable', 'symbol', 'token',
            'tokenize', 'tabnanny', 'py_compile', 'compileall', 'dis', 'pickletools',
            'formatter', 'msilib', 'msvcrt', 'winreg', 'winsound', 'posix', 'pwd',
            'spwd', 'grp', 'crypt', 'termios', 'tty', 'pty', 'fcntl', 'pipes',
            'resource', 'nis', 'syslog', 'optparse', 'imp', 'code', 'codeop',
            'pyclbr', 'compileall', 'dis', 'pickletools', 'formatter', 'msilib',
            'msvcrt', 'winreg', 'winsound', 'posix', 'pwd', 'spwd', 'grp', 'crypt',
            'termios', 'tty', 'pty', 'fcntl', 'pipes', 'resource', 'nis', 'syslog'
        }
        
        third_party = []
        for imp in imports:
            # Skip standard library
            if imp not in stdlib_modules and not imp.startswith('_'):
                third_party.append(imp)
        
        return sorted(third_party)
    
    def generate_requirements_txt(self, generated_files: List[Dict]) -> Optional[str]:
        """Auto-generate requirements.txt from Python imports"""
        imports = set()
        
        for file_info in generated_files:
            if file_info.get('language', '').lower() in ['python', 'py']:
                file_path = file_info.get('full_path')
                if file_path and Path(file_path).exists():
                    # Parse file for imports
                    file_imports = self._extract_imports(Path(file_path))
                    imports.update(file_imports)
        
        if not imports:
            return None
        
        # Filter out standard library
        third_party = self._filter_third_party_packages(list(imports))
        
        if not third_party:
            return None
        
        # Generate requirements.txt content
        requirements_content = "\n".join(sorted(third_party))
        return requirements_content
    
    def generate_setup_instructions(self, generated_files: List[Dict], 
                                    requirements_txt: Optional[str] = None,
                                    requirements_file_path: Optional[str] = None) -> str:
        """Generate setup and usage instructions"""
        instructions = []
        instructions.append("# Setup Instructions\n")
        
        # Installation steps
        if requirements_txt or requirements_file_path:
            instructions.append("## Installation\n")
            instructions.append("```bash")
            if requirements_file_path:
                instructions.append(f"pip install -r {Path(requirements_file_path).name}")
            else:
                instructions.append("pip install -r requirements.txt")
            instructions.append("```\n")
        
        # Usage instructions
        instructions.append("## Usage\n")
        for file_info in generated_files:
            filename = file_info.get('filename', 'unknown')
            language = file_info.get('language', '').lower()
            
            if language in ['python', 'py']:
                instructions.append(f"### Running {filename}\n")
                instructions.append("```bash")
                instructions.append(f"python {filename}")
                instructions.append("```\n")
            elif language in ['bash', 'sh', 'shell']:
                instructions.append(f"### Running {filename}\n")
                instructions.append("```bash")
                instructions.append(f"bash {filename}")
                instructions.append("```\n")
                # Make executable
                instructions.append("Or make it executable:\n")
                instructions.append("```bash")
                instructions.append(f"chmod +x {filename}")
                instructions.append(f"./{filename}")
                instructions.append("```\n")
        
        # Add notes
        instructions.append("## Notes\n")
        instructions.append("- Make sure all dependencies are installed before running")
        if requirements_txt or requirements_file_path:
            instructions.append("- Install dependencies using the command above")
        instructions.append("- Check file permissions for shell scripts")
        
        return "\n".join(instructions)


# Helper function to get file size for Telegram limits
def get_file_size(file_path: str) -> int:
    """Get file size in bytes"""
    try:
        return Path(file_path).stat().st_size
    except Exception:
        return 0


# Telegram file size limit: 50MB for documents
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

def is_file_size_valid(file_path: str, max_size: int = MAX_FILE_SIZE) -> bool:
    """Check if file size is within Telegram limits"""
    size = get_file_size(file_path)
    return size <= max_size
