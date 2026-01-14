# -*- coding: utf-8 -*-
"""
Plan Generator - Generate markdown plans for tasks (Cursor-style)
Creates structured plans before executing complex tasks
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class PlanGenerator:
    """Generate markdown plans for tasks"""
    
    def __init__(self, workspace_path: str = None):
        """
        Initialize plan generator
        
        Args:
            workspace_path: Base workspace path for saving plans
        """
        self.workspace_path = Path(workspace_path) if workspace_path else None
        logger.info("Plan Generator initialized")
    
    def generate_plan(self, 
                     task_description: str,
                     steps: List[str] = None,
                     expected_results: str = None,
                     requires_templates: bool = False,
                     template_type: str = None) -> str:
        """
        Generate markdown plan for a task
        
        Args:
            task_description: Description of the task
            steps: List of step descriptions (optional, will be generated if not provided)
            expected_results: Expected deliverables (optional)
            requires_templates: Whether task requires templates from database
            template_type: Type of template needed (e.g., 'id', 'document')
        
        Returns:
            Markdown plan string
        """
        plan_lines = [
            f"# Task: {task_description}",
            "",
            f"**Created:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            ""
        ]
        
        # Add template check step if needed
        if requires_templates:
            plan_lines.extend([
                "## Template Check",
                "",
                "**CRITICAL:** Check database for templates FIRST before creating new ones:",
                "",
                "```python",
                "from template_manager import get_template_manager",
                "tm = get_template_manager()",
            ])
            
            if template_type:
                plan_lines.append(f"templates = tm.list_templates(template_type='{template_type}')")
            else:
                plan_lines.append("templates = tm.list_templates()")
            
            plan_lines.extend([
                "# Search for matching template",
                "template = tm.get_template(name='template_name')",
                "```",
                "",
                "- [ ] Check database for existing templates",
                "- [ ] Use template from database if found",
                "- [ ] Only create new template if none exists",
                ""
            ])
        
        plan_lines.extend([
            "## Plan",
            ""
        ])
        
        if steps:
            for i, step in enumerate(steps, 1):
                plan_lines.append(f"{i}. {step}")
        else:
            plan_lines.append("1. Analyze task requirements")
            plan_lines.append("2. Execute steps")
            plan_lines.append("3. Test results")
            plan_lines.append("4. Deliver output")
        
        plan_lines.extend([
            "",
            "## Execution",
            "",
            "Status will be updated as steps complete:",
            ""
        ])
        
        # Add placeholder execution status
        if steps:
            for i in range(1, len(steps) + 1):
                plan_lines.append(f"- Step {i}: ⏳ Pending")
        else:
            plan_lines.append("- Step 1: ⏳ Pending")
        
        plan_lines.extend([
            "",
            "## Testing",
            "",
            "Each step will be tested before proceeding:",
            "",
            "- [ ] Verify files exist and are readable",
            "- [ ] Test script execution (if applicable)",
            "- [ ] Verify service startup (if applicable)",
            "- [ ] Validate API responses (if applicable)",
            ""
        ])
        
        if expected_results:
            plan_lines.extend([
                "## Expected Results",
                "",
                expected_results,
                ""
            ])
        
        plan_lines.extend([
            "## Results",
            "",
            "Results will be documented here as task completes.",
            ""
        ])
        
        return "\n".join(plan_lines)
    
    def save_plan(self, plan: str, task_name: str, user_id: int = None) -> Optional[Path]:
        """
        Save plan to file
        
        Args:
            plan: Plan markdown string
            task_name: Name of the task (for filename)
            user_id: User ID (for user-specific workspace)
        
        Returns:
            Path to saved plan file, or None if failed
        """
        if not self.workspace_path:
            logger.warning("No workspace path set, cannot save plan")
            return None
        
        try:
            # Sanitize task name for filename
            safe_name = "".join(c for c in task_name if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_name = safe_name.replace(' ', '_').lower()[:50]
            
            # Create plans directory
            if user_id:
                plans_dir = self.workspace_path / f"user_{user_id}" / "plans"
            else:
                plans_dir = self.workspace_path / "plans"
            
            plans_dir.mkdir(parents=True, exist_ok=True)
            
            # Save plan
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            plan_file = plans_dir / f"{safe_name}_{timestamp}.md"
            
            plan_file.write_text(plan, encoding='utf-8')
            logger.info(f"Plan saved: {plan_file}")
            
            return plan_file
            
        except Exception as e:
            logger.error(f"Error saving plan: {e}", exc_info=True)
            return None
    
    def update_plan(self, plan_file: Path, step_number: int, status: str, result: str = None) -> bool:
        """
        Update plan with step execution status
        
        Args:
            plan_file: Path to plan file
            step_number: Step number to update
            status: Status ('complete', 'failed', 'retrying')
            result: Optional result message
        
        Returns:
            True if updated successfully
        """
        try:
            if not plan_file.exists():
                logger.warning(f"Plan file not found: {plan_file}")
                return False
            
            content = plan_file.read_text(encoding='utf-8')
            lines = content.split('\n')
            
            # Find execution section and update step
            in_execution = False
            updated = False
            
            for i, line in enumerate(lines):
                if line.strip() == "## Execution":
                    in_execution = True
                    continue
                
                if in_execution and line.strip().startswith("##"):
                    break
                
                if in_execution and line.strip().startswith(f"- Step {step_number}:"):
                    status_icon = {
                        'complete': '✅',
                        'failed': '❌',
                        'retrying': '🔄',
                        'pending': '⏳'
                    }.get(status.lower(), '⏳')
                    
                    result_text = f" - {result}" if result else ""
                    lines[i] = f"- Step {step_number}: {status_icon} {status.capitalize()}{result_text}"
                    updated = True
                    break
            
            if updated:
                plan_file.write_text('\n'.join(lines), encoding='utf-8')
                logger.info(f"Plan updated: Step {step_number} -> {status}")
                return True
            else:
                logger.warning(f"Could not find step {step_number} in plan")
                return False
                
        except Exception as e:
            logger.error(f"Error updating plan: {e}", exc_info=True)
            return False
    
    def add_result(self, plan_file: Path, result_text: str) -> bool:
        """
        Add result to plan file
        
        Args:
            plan_file: Path to plan file
            result_text: Result text to add
        
        Returns:
            True if added successfully
        """
        try:
            if not plan_file.exists():
                logger.warning(f"Plan file not found: {plan_file}")
                return False
            
            content = plan_file.read_text(encoding='utf-8')
            
            # Find Results section and append
            if "## Results" in content:
                # Append to existing results
                content = content.replace(
                    "## Results",
                    f"## Results\n\n{result_text}\n"
                )
            else:
                # Add Results section
                content += f"\n\n## Results\n\n{result_text}\n"
            
            plan_file.write_text(content, encoding='utf-8')
            logger.info("Result added to plan")
            return True
            
        except Exception as e:
            logger.error(f"Error adding result: {e}", exc_info=True)
            return False


# Global instance
_plan_generator_instance = None

def get_plan_generator(workspace_path: str = None) -> PlanGenerator:
    """Get or create global plan generator instance"""
    global _plan_generator_instance
    if _plan_generator_instance is None:
        _plan_generator_instance = PlanGenerator(workspace_path)
    return _plan_generator_instance
