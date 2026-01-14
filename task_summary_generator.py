# -*- coding: utf-8 -*-
"""
Task Summary Generator - Generate usage instructions and summaries for completed tasks
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class TaskSummaryGenerator:
    """Generate task completion summaries with usage instructions"""
    
    def __init__(self):
        self.logger = logger
    
    def generate_summary(self,
                        task_description: str,
                        results: Dict[str, Any],
                        files: List[Dict[str, str]],
                        duration: float,
                        status: str = "complete") -> str:
        """
        Generate task completion summary
        
        Args:
            task_description: Description of the task
            results: Results dictionary
            files: List of file dicts with 'name', 'desc', 'usage' keys
            duration: Task duration in seconds
            status: Task status ('complete', 'failed', 'partial')
        
        Returns:
            Formatted markdown summary
        """
        status_emoji = {
            'complete': '✅',
            'failed': '❌',
            'partial': '⚠️'
        }.get(status.lower(), '✅')
        
        duration_str = self._format_duration(duration)
        
        summary = f"# Task Completion Summary\n\n"
        summary += f"## Task\n{task_description}\n\n"
        summary += f"## Status\n{status_emoji} {status.capitalize()}\n\n"
        summary += f"## Duration\n{duration_str}\n\n"
        
        # Results summary
        if results:
            summary += f"## Results Summary\n"
            summary += self._format_results(results)
            summary += "\n"
        
        # Generated files
        if files:
            summary += f"## Generated Files\n\n"
            for i, file_info in enumerate(files, 1):
                name = file_info.get('name', f'file_{i}')
                desc = file_info.get('desc', 'Generated file')
                usage = file_info.get('usage', 'See file for details')
                file_type = file_info.get('type', 'unknown')
                
                summary += f"### {i}. `{name}`\n"
                summary += f"**Type:** {file_type}\n"
                summary += f"**Description:** {desc}\n"
                summary += f"**Usage:**\n```\n{usage}\n```\n\n"
        
        # Next steps
        next_steps = self._generate_next_steps(task_description, results, files)
        if next_steps:
            summary += f"## Next Steps\n\n"
            for step in next_steps:
                summary += f"- {step}\n"
            summary += "\n"
        
        return summary
    
    def _format_results(self, results: Dict[str, Any]) -> str:
        """Format results dictionary into readable text"""
        formatted = ""
        
        # Handle common result structures
        if isinstance(results, dict):
            # Count results
            if 'count' in results:
                formatted += f"**Total Items:** {results['count']}\n"
            
            # Vulnerabilities found
            if 'vulnerabilities' in results:
                vulns = results['vulnerabilities']
                if isinstance(vulns, list):
                    formatted += f"**Vulnerabilities Found:** {len(vulns)}\n"
                elif isinstance(vulns, int):
                    formatted += f"**Vulnerabilities Found:** {vulns}\n"
            
            # Ports found
            if 'ports' in results:
                ports = results['ports']
                if isinstance(ports, list):
                    formatted += f"**Open Ports:** {len(ports)}\n"
                elif isinstance(ports, int):
                    formatted += f"**Open Ports:** {ports}\n"
            
            # Errors
            if 'errors' in results:
                errors = results['errors']
                if errors:
                    formatted += f"**Errors:** {len(errors) if isinstance(errors, list) else 1}\n"
            
            # Summary text
            if 'summary' in results:
                formatted += f"\n{results['summary']}\n"
            elif 'message' in results:
                formatted += f"\n{results['message']}\n"
        
        return formatted if formatted else "Task completed successfully."
    
    def _generate_next_steps(self,
                            task_description: str,
                            results: Dict[str, Any],
                            files: List[Dict[str, str]]) -> List[str]:
        """Generate actionable next steps based on task and results"""
        steps = []
        
        # Analyze task type
        task_lower = task_description.lower()
        
        # Scanning tasks
        if 'scan' in task_lower or 'vulnerability' in task_lower:
            if results and results.get('vulnerabilities'):
                steps.append("Review identified vulnerabilities")
                steps.append("Prioritize critical vulnerabilities for exploitation")
                steps.append("Run exploit_search for found vulnerabilities")
            else:
                steps.append("No vulnerabilities found - target may be secure")
        
        # Code generation tasks
        if 'code' in task_lower or 'script' in task_lower or 'generate' in task_lower:
            if files:
                steps.append("Review generated code/script")
                steps.append("Test the code in a safe environment")
                steps.append("Customize as needed for your use case")
        
        # Credential checking tasks
        if 'credential' in task_lower or 'check' in task_lower or 'account' in task_lower:
            if results and results.get('valid_accounts'):
                steps.append("Review valid accounts found")
                steps.append("Use credentials responsibly and ethically")
            else:
                steps.append("No valid accounts found")
        
        # File generation tasks
        if files:
            for file_info in files:
                file_type = file_info.get('type', '').lower()
                if file_type == 'python':
                    steps.append(f"Run: `python {file_info.get('name', 'script.py')}`")
                elif file_type == 'bash' or file_type == 'sh':
                    steps.append(f"Run: `bash {file_info.get('name', 'script.sh')}`")
        
        # Default steps if none generated
        if not steps:
            steps.append("Review the generated files")
            steps.append("Test in a safe environment")
            steps.append("Customize as needed")
        
        return steps
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format"""
        if seconds < 60:
            return f"{int(seconds)} seconds"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes} minutes {secs} seconds"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours} hours {minutes} minutes"
    
    def generate_file_usage_guide(self, file_path: str, file_type: str = None) -> Dict[str, str]:
        """
        Generate usage instructions for a specific file
        
        Args:
            file_path: Path to the file
            file_type: Type of file (auto-detected if None)
        
        Returns:
            Dict with 'desc' and 'usage' keys
        """
        path = Path(file_path)
        name = path.name
        
        # Auto-detect file type
        if not file_type:
            ext = path.suffix.lower()
            type_map = {
                '.py': 'python',
                '.sh': 'bash',
                '.js': 'javascript',
                '.php': 'php',
                '.txt': 'text',
                '.json': 'json',
                '.csv': 'csv',
                '.pdf': 'pdf',
                '.docx': 'word',
                '.xlsx': 'excel'
            }
            file_type = type_map.get(ext, 'unknown')
        
        # Generate description
        desc_map = {
            'python': 'Python script',
            'bash': 'Bash shell script',
            'javascript': 'JavaScript file',
            'php': 'PHP script',
            'text': 'Text file',
            'json': 'JSON data file',
            'csv': 'CSV data file',
            'pdf': 'PDF document',
            'word': 'Word document',
            'excel': 'Excel spreadsheet'
        }
        desc = desc_map.get(file_type, 'Generated file')
        
        # Generate usage instructions
        usage_map = {
            'python': f'python {name}',
            'bash': f'bash {name}  # or: chmod +x {name} && ./{name}',
            'javascript': f'node {name}',
            'php': f'php {name}',
            'text': f'cat {name}  # or open with any text editor',
            'json': f'cat {name} | python -m json.tool  # or open with any JSON viewer',
            'csv': f'Open {name} with Excel, Google Sheets, or any CSV viewer',
            'pdf': f'Open {name} with any PDF reader',
            'word': f'Open {name} with Microsoft Word or LibreOffice',
            'excel': f'Open {name} with Microsoft Excel or LibreOffice Calc'
        }
        usage = usage_map.get(file_type, f'Open {name} with appropriate application')
        
        return {
            'name': name,
            'desc': desc,
            'usage': usage,
            'type': file_type
        }


# Global instance
_task_summary_generator_instance = None

def get_task_summary_generator() -> TaskSummaryGenerator:
    """Get or create global task summary generator instance"""
    global _task_summary_generator_instance
    if _task_summary_generator_instance is None:
        _task_summary_generator_instance = TaskSummaryGenerator()
    return _task_summary_generator_instance
