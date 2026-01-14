# -*- coding: utf-8 -*-
"""
Task Planner - AI-based task planning with tool discovery
Creates structured plans before code generation (Cursor-style)
"""

import os
import json
import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class TaskPlanner:
    """AI-based task planning system that analyzes tasks and creates structured plans"""
    
    def __init__(self, brain, toolkit_manager=None):
        """
        Initialize TaskPlanner
        brain: HacxBrain instance for AI interactions
        toolkit_manager: ToolkitManager instance for tool discovery
        """
        self.brain = brain
        self.toolkit_manager = toolkit_manager
        self.plans_cache = {}  # Cache plans by task hash
    
    def analyze_task(self, task: str) -> Dict:
        """
        Analyze task and extract requirements
        Returns dict with: task_type, complexity, requirements, keywords, has_ambiguity, missing_info
        """
        task_lower = task.lower()
        
        # Detect task type
        task_type = "general"
        if any(kw in task_lower for kw in ['scan', 'recon', 'discover', 'enumerate']):
            task_type = "reconnaissance"
        elif any(kw in task_lower for kw in ['exploit', 'attack', 'breach', 'hack']):
            task_type = "exploitation"
        elif any(kw in task_lower for kw in ['brute', 'crack', 'password', 'hash']):
            task_type = "credential_access"
        elif any(kw in task_lower for kw in ['code', 'script', 'program', 'function']):
            task_type = "code_generation"
        elif any(kw in task_lower for kw in ['test', 'validate', 'check', 'verify']):
            task_type = "testing"
        
        # Estimate complexity
        complexity = "low"
        word_count = len(task.split())
        if word_count > 20:
            complexity = "high"
        elif word_count > 10:
            complexity = "medium"
        
        # Detect ambiguity indicators
        ambiguity_keywords = ['maybe', 'perhaps', 'could', 'might', 'possibly', 'some', 'any', 'whatever']
        has_ambiguity = any(kw in task_lower for kw in ambiguity_keywords) or word_count < 5
        
        # Detect missing critical information
        missing_info = []
        if task_type == "reconnaissance" and not bool(re.search(r'https?://|www\.', task)):
            missing_info.append("target_url")
        if task_type == "credential_access" and not any(kw in task_lower for kw in ['hash', 'password', 'file', 'list']):
            missing_info.append("credentials_source")
        if task_type == "code_generation" and not any(kw in task_lower for kw in ['function', 'class', 'script', 'tool']):
            missing_info.append("code_type")
        if 'scan' in task_lower and not bool(re.search(r'https?://|www\.', task)):
            missing_info.append("scan_target")
        
        # Extract keywords
        keywords = []
        common_keywords = ['python', 'script', 'tool', 'scan', 'exploit', 'brute', 'crack', 
                          'hash', 'password', 'api', 'web', 'network', 'file', 'database']
        for kw in common_keywords:
            if kw in task_lower:
                keywords.append(kw)
        
        return {
            'task_type': task_type,
            'complexity': complexity,
            'keywords': keywords,
            'word_count': word_count,
            'has_url': bool(re.search(r'https?://', task)),
            'has_file_reference': bool(re.search(r'\b(file|path|directory|folder)\b', task_lower)),
            'has_ambiguity': has_ambiguity,
            'missing_info': missing_info
        }
    
    def deep_task_analysis(self, task: str) -> Dict:
        """Comprehensive deep analysis of task with edge cases and risk assessment"""
        try:
            analysis_prompt = f"""
Perform DEEP, COMPREHENSIVE analysis of this task:
{task}

Analyze ALL of the following:
1. REQUIREMENTS - All explicit and implicit requirements. What must be accomplished?
2. COMPLEXITY - True complexity, not surface level. What makes this challenging?
3. EDGE CASES - All possible edge cases and failure modes. What could go wrong?
4. RISKS - Technical, security, operational risks. What are the dangers?
5. ALTERNATIVES - Multiple sophisticated approaches. What are different ways to solve this?
6. RESOURCES - Required resources, dependencies, constraints. What's needed?
7. OPTIMIZATION - How to do this most efficiently. What's the best approach?
8. INNOVATION - Unprecedented approaches. What hasn't been tried?
9. STEALTH - Detection avoidance requirements. How to avoid detection?
10. QUALITY - Production-grade requirements. What quality standards apply?

Return comprehensive analysis in structured format:
- Requirements: [list all requirements]
- Complexity: [detailed complexity analysis]
- Edge Cases: [all edge cases identified]
- Risks: [all risks with mitigation strategies]
- Alternatives: [multiple sophisticated approaches]
- Resources: [required resources and dependencies]
- Optimization: [efficiency considerations]
- Innovation: [unprecedented approaches]
- Stealth: [detection avoidance measures]
- Quality: [quality standards and requirements]
"""
            
            # Use brain to generate analysis
            analysis_text = ""
            for chunk in self.brain.chat(analysis_prompt):
                analysis_text += chunk
            
            # Parse analysis into structured format
            analysis = {
                'raw_analysis': analysis_text,
                'requirements': self._extract_section(analysis_text, 'requirements', 'requirement'),
                'complexity': self._extract_section(analysis_text, 'complexity', 'complex'),
                'edge_cases': self._extract_section(analysis_text, 'edge', 'failure'),
                'risks': self._extract_section(analysis_text, 'risk', 'danger'),
                'alternatives': self._extract_section(analysis_text, 'alternative', 'approach'),
                'resources': self._extract_section(analysis_text, 'resource', 'dependency'),
                'optimization': self._extract_section(analysis_text, 'optimization', 'efficiency'),
                'innovation': self._extract_section(analysis_text, 'innovation', 'unprecedented'),
                'stealth': self._extract_section(analysis_text, 'stealth', 'detection'),
                'quality': self._extract_section(analysis_text, 'quality', 'standard'),
            }
            
            logger.info("Deep task analysis completed")
            return analysis
        except Exception as e:
            logger.error(f"Error in deep task analysis: {e}", exc_info=True)
            return {
                'raw_analysis': f"Analysis error: {str(e)}",
                'requirements': 'Requirements analysis needed',
                'complexity': 'Complexity analysis needed',
                'edge_cases': 'Edge case analysis needed',
                'risks': 'Risk assessment needed',
                'alternatives': 'Alternative approaches needed',
                'resources': 'Resource analysis needed',
                'optimization': 'Optimization analysis needed',
                'innovation': 'Innovation analysis needed',
                'stealth': 'Stealth analysis needed',
                'quality': 'Quality analysis needed',
            }
    
    def _extract_section(self, text: str, *keywords) -> str:
        """Extract section from analysis text based on keywords"""
        text_lower = text.lower()
        for keyword in keywords:
            if keyword in text_lower:
                # Try to extract paragraph containing keyword
                lines = text.split('\n')
                for i, line in enumerate(lines):
                    if keyword in line.lower():
                        # Return this line and next few lines
                        return '\n'.join(lines[max(0, i-1):min(len(lines), i+5)])
        return ""
    
    def discover_relevant_tools(self, task: str, mcp_integration=None, hexstrike_integration=None, 
                                tool_selector=None, execution_monitor=None) -> List[Dict]:
        """
        Discover relevant tools for the task using ToolkitManager, HexStrike, and MCP
        Returns list of tool dicts
        """
        tools = []
        
        # Discover tools from ToolkitManager (RedTeam-Tools) - now includes HexStrike
        if self.toolkit_manager:
            try:
                toolkit_tools = self.toolkit_manager.find_best_tools(
                    task, limit=10, tool_selector=tool_selector, execution_monitor=execution_monitor
                )
                tools.extend(toolkit_tools)
                logger.info(f"Discovered {len(toolkit_tools)} tools from ToolkitManager (includes HexStrike)")
            except Exception as e:
                logger.error(f"Error discovering ToolkitManager tools: {e}")
        
        # Also get HexStrike tools directly if available
        if hexstrike_integration:
            try:
                hexstrike_tools = hexstrike_integration.get_tools_for_task(task, limit=10)
                for tool in hexstrike_tools:
                    tool_dict = tool.to_dict()
                    # Check if already exists
                    if not any(t.get('name') == tool_dict['name'] for t in tools):
                        tools.append(tool_dict)
                logger.info(f"Discovered {len(hexstrike_tools)} additional HexStrike tools")
            except Exception as e:
                logger.error(f"Error discovering HexStrike tools: {e}")
        
        # Discover tools from MCP integration
        if mcp_integration:
            try:
                mcp_tools = asyncio.run(mcp_integration.discover_all_tools())
                # Filter MCP tools relevant to task
                task_lower = task.lower()
                relevant_mcp_tools = []
                for tool in mcp_tools:
                    if (task_lower in tool.name.lower() or 
                        task_lower in tool.description.lower() or
                        any(keyword in tool.description.lower() for keyword in task_lower.split())):
                        relevant_mcp_tools.append({
                            'name': tool.name,
                            'description': tool.description,
                            'category': 'MCP',
                            'mcp_tool': True,
                            'parameters': tool.parameters
                        })
                tools.extend(relevant_mcp_tools)
                logger.info(f"Discovered {len(relevant_mcp_tools)} MCP tools")
            except Exception as e:
                logger.error(f"Error discovering MCP tools: {e}")
        
        if not tools:
            logger.warning("No tools discovered for task")
        
        return tools
    
    def create_plan(self, task: str, tools: List[Dict] = None, knowledge_base=None,
                   vulnerability_scanner=None, cve_intelligence=None, exploit_intelligence=None) -> Dict:
        """
        Create AI-generated structured plan for the task
        Returns structured plan dict
        """
        # Analyze task first
        task_analysis = self.analyze_task(task)
        
        # Check if task involves vulnerability scanning
        task_lower = task.lower()
        is_vuln_task = any(keyword in task_lower for keyword in ['scan', 'vulnerability', 'cve', 'exploit', 'test site'])
        
        # Extract target URL if present
        url_pattern = re.compile(r'https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
        url_matches = url_pattern.findall(task)
        target_url = url_matches[0] if url_matches else None
        
        # If vulnerability task, add scanning steps to plan
        vuln_context = ""
        if is_vuln_task and target_url and vulnerability_scanner:
            try:
                # Perform quick scan
                scan_result = vulnerability_scanner.scan_target(target_url, scan_type='quick')
                exploitable = scan_result.get('exploitable', [])
                vulnerabilities = scan_result.get('vulnerabilities', [])
                
                vuln_context = f"\n[VULNERABILITY SCAN RESULTS FOR {target_url}]:"
                vuln_context += f"\n- Vulnerabilities found: {len(vulnerabilities)}"
                vuln_context += f"\n- Exploitable: {len(exploitable)}"
                if exploitable:
                    vuln_context += "\n- Exploitable CVEs:"
                    for vuln in exploitable[:5]:
                        vuln_context += f"\n  • {vuln.get('cve_id')} - {vuln.get('severity')} ({vuln.get('exploit_count', 0)} exploits)"
            except Exception as e:
                logger.warning(f"Error in vulnerability scan for planning: {e}")
        
        # Discover tools if not provided
        if tools is None:
            tools = self.discover_relevant_tools(task)
        
        # Get knowledge base context
        knowledge_context = None
        if knowledge_base:
            try:
                knowledge_results = knowledge_base.search_knowledge(task)
                # Manually limit to 3 items
                if knowledge_results:
                    knowledge_results = knowledge_results[:3]
                    knowledge_context = knowledge_base.format_knowledge_for_prompt(knowledge_results)
            except Exception as e:
                logger.warning(f"Error getting knowledge context: {e}")
        
        # Combine contexts
        combined_context = ""
        if knowledge_context:
            combined_context += knowledge_context
        if vuln_context:
            combined_context += vuln_context
        
        # Create planning prompt
        planning_prompt = self._create_planning_prompt(task, task_analysis, tools, combined_context if combined_context else None)
        
        # Get AI response (non-streaming for planning)
        plan_text = ""
        try:
            for chunk in self.brain.chat(planning_prompt):
                plan_text += chunk
        except Exception as e:
            logger.error(f"Error getting plan from AI: {e}")
            return self._create_fallback_plan(task, task_analysis, tools)
        
        # Parse AI response into structured plan
        plan = self._parse_plan_response(plan_text, task, task_analysis, tools)
        
        return plan
    
    def _create_planning_prompt(self, task: str, analysis: Dict, tools: List[Dict], context: Optional[str] = None) -> str:
        """Create prompt for AI to generate plan"""
        
        tools_text = ""
        if tools:
            tools_text = "\n\n[AVAILABLE TOOLS]:\n"
            for i, tool in enumerate(tools[:10], 1):  # Limit to top 10
                tools_text += f"{i}. {tool.get('name', 'Unknown')} - {tool.get('description', 'No description')}\n"
                if tool.get('category'):
                    tools_text += f"   Category: {tool.get('category')}\n"
                if tool.get('path'):
                    tools_text += f"   Path: {tool.get('path')}\n"
        else:
            tools_text = "\n[AVAILABLE TOOLS]: No specific tools found, use standard commands and libraries.\n"
        
        # Include context if provided
        context_text = ""
        if context:
            context_text = f"\n\n[ADDITIONAL CONTEXT]:\n{context}\n"
        
        prompt = f"""You are a task planning AI. Analyze the user's task and create a detailed, step-by-step execution plan.

TASK: {task}

TASK ANALYSIS:
- Type: {analysis['task_type']}
- Complexity: {analysis['complexity']}
- Keywords: {', '.join(analysis['keywords']) if analysis['keywords'] else 'None'}
{context_text}{tools_text}

Create a structured plan with the following format:

PLAN:
1. [Step description]
   Tool: [tool name or 'standard command']
   Command: [exact command to run]
   Dependencies: [list any dependencies]
   Expected Output: [what to expect]

2. [Next step...]

Continue until all steps are covered.

IMPORTANT:
- Be specific with commands
- Include tool installation if needed
- Consider dependencies
- Plan for error handling
- Estimate time for each step

Respond ONLY with the plan in the format above, no additional text."""

        return prompt
    
    def _parse_plan_response(self, plan_text: str, task: str, analysis: Dict, tools: List[Dict]) -> Dict:
        """Parse AI response into structured plan format"""
        
        steps = []
        tools_needed = []
        
        # Extract steps from plan text
        step_pattern = r'(\d+)\.\s*(.+?)(?=\d+\.|$)'
        matches = re.finditer(step_pattern, plan_text, re.DOTALL | re.IGNORECASE)
        
        for match in matches:
            step_num = int(match.group(1))
            step_content = match.group(2).strip()
            
            # Extract components
            action = step_content.split('\n')[0].strip() if '\n' in step_content else step_content
            
            # Extract tool
            tool_match = re.search(r'Tool:\s*(.+)', step_content, re.IGNORECASE)
            tool = tool_match.group(1).strip() if tool_match else "standard command"
            
            # Extract command
            cmd_match = re.search(r'Command:\s*(.+)', step_content, re.IGNORECASE)
            command = cmd_match.group(1).strip() if cmd_match else ""
            
            # Extract dependencies
            dep_match = re.search(r'Dependencies:\s*(.+)', step_content, re.IGNORECASE)
            dependencies = [d.strip() for d in dep_match.group(1).split(',')] if dep_match else []
            
            # Extract expected output
            output_match = re.search(r'Expected Output:\s*(.+)', step_content, re.IGNORECASE)
            expected_output = output_match.group(1).strip() if output_match else ""
            
            if tool and tool != "standard command":
                if tool not in tools_needed:
                    tools_needed.append(tool)
            
            steps.append({
                'step_number': step_num,
                'action': action,
                'tool': tool,
                'command': command,
                'dependencies': dependencies,
                'expected_output': expected_output
            })
        
        # If no steps found, create a simple plan
        if not steps:
            steps = [{
                'step_number': 1,
                'action': 'Execute task',
                'tool': 'standard command',
                'command': '',
                'dependencies': [],
                'expected_output': 'Task completion'
            }]
        
        # Estimate time (rough estimate)
        estimated_time = f"{len(steps) * 2} minutes" if analysis['complexity'] == 'low' else \
                        f"{len(steps) * 5} minutes" if analysis['complexity'] == 'medium' else \
                        f"{len(steps) * 10} minutes"
        
        # Risk level
        risk_level = "low"
        if any(kw in task.lower() for kw in ['exploit', 'attack', 'hack', 'breach', 'crack']):
            risk_level = "high"
        elif any(kw in task.lower() for kw in ['scan', 'recon', 'brute']):
            risk_level = "medium"
        
        return {
            'task': task,
            'task_analysis': analysis,
            'steps': steps,
            'tools_needed': tools_needed,
            'available_tools': [t.get('name') for t in tools],
            'estimated_time': estimated_time,
            'risk_level': risk_level,
            'plan_text': plan_text
        }
    
    def _create_fallback_plan(self, task: str, analysis: Dict, tools: List[Dict]) -> Dict:
        """Create a simple fallback plan if AI planning fails"""
        return {
            'task': task,
            'task_analysis': analysis,
            'steps': [{
                'step_number': 1,
                'action': 'Execute task',
                'tool': 'standard command',
                'command': '',
                'dependencies': [],
                'expected_output': 'Task completion'
            }],
            'tools_needed': [],
            'available_tools': [t.get('name') for t in tools] if tools else [],
            'estimated_time': '5 minutes',
            'risk_level': 'low',
            'plan_text': 'Fallback plan - AI planning unavailable'
        }
    
    def validate_plan(self, plan: Dict) -> Tuple[bool, List[str]]:
        """
        Validate plan feasibility
        Returns (is_valid, list_of_issues)
        """
        issues = []
        
        if not plan.get('steps'):
            issues.append("Plan has no steps")
            return False, issues
        
        # Check if tools are available
        if plan.get('tools_needed'):
            available_tools = plan.get('available_tools', [])
            for tool in plan['tools_needed']:
                if tool not in available_tools and tool != "standard command":
                    issues.append(f"Tool '{tool}' may not be available")
        
        # Check if steps have commands
        for step in plan['steps']:
            if not step.get('command') and step.get('tool') != "standard command":
                issues.append(f"Step {step['step_number']} has no command")
        
        # Check dependencies
        for step in plan['steps']:
            deps = step.get('dependencies', [])
            for dep in deps:
                # Check if dependency is mentioned in earlier steps
                found = False
                for prev_step in plan['steps']:
                    if prev_step['step_number'] < step['step_number']:
                        if dep.lower() in prev_step.get('action', '').lower() or \
                           dep.lower() in prev_step.get('tool', '').lower():
                            found = True
                            break
                if not found and dep:
                    issues.append(f"Step {step['step_number']} dependency '{dep}' may not be resolved")
        
        is_valid = len(issues) == 0
        return is_valid, issues
    
    def format_plan_for_display(self, plan: Dict) -> str:
        """Format plan as readable text"""
        lines = []
        lines.append("=" * 60)
        lines.append("EXECUTION PLAN")
        lines.append("=" * 60)
        lines.append(f"Task: {plan['task']}")
        lines.append(f"Complexity: {plan['task_analysis']['complexity']}")
        lines.append(f"Estimated Time: {plan['estimated_time']}")
        lines.append(f"Risk Level: {plan['risk_level']}")
        lines.append("")
        lines.append("Steps:")
        lines.append("-" * 60)
        
        for step in plan['steps']:
            lines.append(f"\n{step['step_number']}. {step['action']}")
            if step.get('tool'):
                lines.append(f"   Tool: {step['tool']}")
            if step.get('command'):
                lines.append(f"   Command: {step['command']}")
            if step.get('dependencies'):
                lines.append(f"   Dependencies: {', '.join(step['dependencies'])}")
            if step.get('expected_output'):
                lines.append(f"   Expected: {step['expected_output']}")
        
        if plan.get('tools_needed'):
            lines.append("\n" + "-" * 60)
            lines.append("Tools Needed:")
            for tool in plan['tools_needed']:
                lines.append(f"  - {tool}")
        
        return "\n".join(lines)
    
    def get_plan_summary(self, plan: Dict) -> str:
        """Get short summary of plan"""
        num_steps = len(plan.get('steps', []))
        tools = plan.get('tools_needed', [])
        tools_str = f" using {len(tools)} tool(s)" if tools else ""
        return f"Plan with {num_steps} step(s){tools_str} - {plan.get('estimated_time', 'unknown time')}"


# Global planner instance
_planner_instance = None

def get_task_planner(brain, toolkit_manager=None) -> TaskPlanner:
    """Get or create global task planner instance"""
    global _planner_instance
    if _planner_instance is None:
        _planner_instance = TaskPlanner(brain, toolkit_manager)
    return _planner_instance
