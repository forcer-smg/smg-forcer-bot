# -*- coding: utf-8 -*-
"""
Command Execution Integration - Integrates command execution into DesktopAIHandler
This module provides methods that can be added to DesktopAIHandler or used as a mixin
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class CommandExecutionMixin:
    """Mixin class to add command execution capabilities to DesktopAIHandler"""
    
    def __init__(self, *args, **kwargs):
        """Initialize command execution mixin"""
        # Import here to avoid circular dependencies
        from command_executor import get_command_executor
        from ai_response_parser import get_ai_response_parser
        from auto_retry_manager import get_auto_retry_manager
        from progress_streamer import create_progress_streamer
        from task_tracker import TaskTracker
        from continuous_executor import get_continuous_executor
        
        self.command_executor = get_command_executor(getattr(self, 'workspace_root', None))
        self.response_parser = get_ai_response_parser()
        self.retry_manager = get_auto_retry_manager()
        self.continuous_executor = get_continuous_executor()
        
        # Progress streamer will be initialized when needed
        self.progress_streamer = None
        self.task_tracker = None
        
        logger.info("Command Execution Mixin initialized")
    
    async def execute_ai_commands(self,
                                 ai_response: str,
                                 update=None,
                                 context=None,
                                 user_id: int = None,
                                 workspace_path: str = None) -> Dict[str, Any]:
        """
        Execute commands from AI response automatically
        
        Args:
            ai_response: AI response text containing code blocks
            update: Telegram Update object (for progress streaming)
            context: Telegram Context object
            user_id: User ID
            workspace_path: Workspace path for execution
        
        Returns:
            Dictionary with execution results
        """
        logger.info("Executing AI commands from response")
        
        # Parse AI response
        parsed = self.response_parser.parse_ai_response(ai_response)
        
        if not parsed['commands']:
            logger.debug("No commands found in AI response")
            return {
                'success': True,
                'commands_executed': 0,
                'results': [],
                'is_complete': parsed['is_complete']
            }
        
        # Initialize progress streamer if long-running task
        if parsed['is_long_running'] and update:
            from progress_streamer import create_progress_streamer
            self.progress_streamer = create_progress_streamer(update, context, update_interval=15)
            self.progress_streamer.set_task_info("Executing commands", estimated_duration=None)
        
        # Initialize task tracker
        from task_tracker import TaskTracker
        self.task_tracker = TaskTracker("Command Execution")
        
        # Execute commands
        results = []
        execution_results = []
        
        for i, command in enumerate(parsed['commands'], 1):
            logger.info(f"Executing command {i}/{len(parsed['commands'])}: {command}")
            
            # Update progress
            if self.progress_streamer:
                self.progress_streamer.update_progress(
                    f"Executing command {i}/{len(parsed['commands'])}",
                    progress_pct=int((i / len(parsed['commands'])) * 100),
                    details=f"Command: {command[:50]}..."
                )
                await self.progress_streamer.send_progress_update()
            
            # Track step
            step_num = self.task_tracker.add_step(f"Execute: {command}")
            self.task_tracker.mark_started(step_num)
            
            # Execute command with retry
            max_retries = 3
            executed = False
            
            for attempt in range(max_retries):
                result = self.command_executor.execute_command(
                    command,
                    cwd=workspace_path or getattr(self, 'workspace_root', None),
                    timeout=300,
                    verify=True
                )
                
                execution_results.append(result)
                
                # Check if command was verified (actually ran)
                if result.get('verified', False):
                    self.task_tracker.mark_complete(step_num, result)
                    results.append({
                        'command': command,
                        'success': result['success'],
                        'output': result.get('stdout', ''),
                        'error': result.get('stderr', ''),
                        'verified': True
                    })
                    executed = True
                    break
                else:
                    # Command didn't actually run - try alternative
                    if attempt < max_retries - 1:
                        error_msg = result.get('error', '') or result.get('stderr', '') or 'Verification failed'
                        alt_command = self.retry_manager.retry_with_alternative(command, error_msg, attempt + 1)
                        if alt_command and alt_command != command:
                            logger.info(f"Trying alternative command: {alt_command}")
                            command = alt_command  # Use alternative for next attempt
                        await asyncio.sleep(1)  # Brief delay before retry
            
            if not executed:
                error_msg = execution_results[-1].get('error', '') or 'Command execution failed'
                self.task_tracker.mark_failed(step_num, error_msg, will_retry=False)
                results.append({
                    'command': command,
                    'success': False,
                    'error': error_msg,
                    'verified': False
                })
        
        # Final progress update
        if self.progress_streamer:
            await self.progress_streamer.send_final_update(
                success=all(r.get('success', False) for r in results),
                summary=f"Executed {len(results)} commands"
            )
        
        return {
            'success': all(r.get('success', False) for r in results),
            'commands_executed': len(results),
            'results': results,
            'is_complete': parsed['is_complete'],
            'task_tracker': self.task_tracker
        }
    
    async def execute_with_continuous_loop(self,
                                          user_message: str,
                                          update=None,
                                          context=None,
                                          user_id: int = None,
                                          workspace_path: str = None,
                                          max_iterations: int = 10) -> Dict[str, Any]:
        """
        Execute AI commands in a continuous loop until task complete (like Cursor)
        
        Args:
            user_message: User's original message
            update: Telegram Update object
            context: Telegram Context object
            user_id: User ID
            workspace_path: Workspace path
            max_iterations: Maximum iterations
        
        Returns:
            Final execution results
        """
        logger.info(f"Starting continuous execution loop for: {user_message}")
        
        # Get AI brain
        brain = getattr(self, 'brain', None)
        if not brain:
            logger.error("No brain available in handler")
            return {'success': False, 'error': 'No brain available'}
        
        # Initialize progress streamer
        if update:
            from progress_streamer import create_progress_streamer
            self.progress_streamer = create_progress_streamer(update, context, update_interval=15)
            self.progress_streamer.set_task_info("Executing task", estimated_duration=None)
        
        # Initialize task tracker
        from task_tracker import TaskTracker
        self.task_tracker = TaskTracker("Continuous Task Execution")
        
        # Conversation context
        conversation_context = user_message
        iteration = 0
        all_results = []
        
        while iteration < max_iterations:
            iteration += 1
            logger.info(f"Continuous execution iteration {iteration}/{max_iterations}")
            
            # Update progress
            if self.progress_streamer:
                self.progress_streamer.update_progress(
                    f"Iteration {iteration}/{max_iterations}",
                    progress_pct=int((iteration / max_iterations) * 50),  # First 50% for iterations
                    details=f"Processing: {user_message[:50]}..."
                )
                await self.progress_streamer.send_progress_update()
            
            # Get AI response
            try:
                ai_response = ""
                for chunk in brain.chat(conversation_context):
                    ai_response += chunk
                
                logger.debug(f"AI response (iteration {iteration}): {ai_response[:200]}...")
                
            except Exception as e:
                logger.error(f"Error getting AI response: {e}", exc_info=True)
                break
            
            # Parse and execute commands
            execution_result = await self.execute_ai_commands(
                ai_response,
                update=update,
                context=context,
                user_id=user_id,
                workspace_path=workspace_path
            )
            
            all_results.append(execution_result)
            
            # Check if task is complete
            if execution_result.get('is_complete', False):
                logger.info(f"Task marked as complete after {iteration} iterations")
                break
            
            # If no commands were executed, check if AI says task is done
            if execution_result['commands_executed'] == 0:
                parsed = self.response_parser.parse_ai_response(ai_response)
                if parsed['is_complete']:
                    logger.info(f"Task complete (no more commands) after {iteration} iterations")
                    break
            
            # Build next context with results
            results_summary = "\n".join([
                f"Command: {r['command']}\nResult: {r.get('output', '')[:200]}\n"
                for r in execution_result['results']
            ])
            
            conversation_context = f"""Previous commands executed. Results:
{results_summary}

Continue with next steps. If task is complete, say "Task complete"."""
            
            # Brief delay before next iteration
            await asyncio.sleep(1)
        
        # Final update
        if self.progress_streamer:
            success = any(r.get('success', False) for r in all_results)
            summary = f"Completed {iteration} iterations. Executed {sum(r['commands_executed'] for r in all_results)} commands."
            await self.progress_streamer.send_final_update(success=success, summary=summary)
        
        return {
            'success': True,
            'iterations': iteration,
            'all_results': all_results,
            'task_tracker': self.task_tracker
        }
