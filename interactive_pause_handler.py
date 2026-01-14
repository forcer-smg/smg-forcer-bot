# -*- coding: utf-8 -*-
"""
Interactive Pause Handler - Handle interactive pauses and user responses during code generation
"""

import logging
import asyncio
import time
from typing import Dict, List, Optional, Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


class InteractivePauseHandler:
    """Handle interactive pauses during code generation"""
    
    def __init__(self):
        """Initialize Interactive Pause Handler"""
        self.pending_responses: Dict[str, Dict] = {}  # Store pending user responses
    
    def create_interactive_keyboard(self, question_type: str, context: Dict) -> InlineKeyboardMarkup:
        """Create inline keyboard for user interaction based on question type"""
        
        if question_type == "run_test_after_generation":
            keyboard = [[
                InlineKeyboardButton("✅ Yes, run test when done", callback_data="pause_yes_run_test"),
                InlineKeyboardButton("❌ No, just generate code", callback_data="pause_no_run_test")
            ]]
        
        elif question_type == "has_combolist":
            keyboard = [[
                InlineKeyboardButton("✅ I have a combolist", callback_data="pause_yes_combolist"),
                InlineKeyboardButton("🔧 Generate combolist for me", callback_data="pause_generate_combolist"),
                InlineKeyboardButton("⏭️ Skip testing, just code", callback_data="pause_skip_testing")
            ]]
        
        elif question_type == "has_resources":
            keyboard = [[
                InlineKeyboardButton("✅ I have resources", callback_data="pause_yes_resources"),
                InlineKeyboardButton("🔧 Generate resources for me", callback_data="pause_generate_resources"),
                InlineKeyboardButton("⏭️ Continue without resources", callback_data="pause_skip_resources")
            ]]
        
        elif question_type == "test_with_resources":
            keyboard = [[
                InlineKeyboardButton("✅ Yes, I have file", callback_data="pause_yes_test_resources"),
                InlineKeyboardButton("🔧 Generate sample file", callback_data="pause_generate_test_resources"),
                InlineKeyboardButton("⏭️ Skip testing", callback_data="pause_skip_testing")
            ]]
        
        elif question_type == "personal_methods":
            keyboard = [[
                InlineKeyboardButton("📚 I have personal methods/resources", callback_data="pause_yes_personal"),
                InlineKeyboardButton("🔄 Retry with different approach", callback_data="pause_retry"),
                InlineKeyboardButton("✅ Accept current results", callback_data="pause_accept")
            ]]
        
        elif question_type == "continue_long_task":
            keyboard = [[
                InlineKeyboardButton("✅ Continue", callback_data="pause_continue_task"),
                InlineKeyboardButton("❌ Stop", callback_data="pause_stop_task")
            ]]
        
        else:
            # Default yes/no keyboard
            keyboard = [[
                InlineKeyboardButton("✅ Yes", callback_data=f"pause_yes_{question_type}"),
                InlineKeyboardButton("❌ No", callback_data=f"pause_no_{question_type}")
            ]]
        
        return InlineKeyboardMarkup(keyboard)
    
    async def pause_and_ask_user(self, question: str, question_type: str, 
                                update, context, options: List[str] = None,
                                timeout: int = 300) -> Optional[str]:
        """Pause execution and wait for user response via keyboard/poll
        
        Args:
            question: Question text to ask user
            question_type: Type of question (determines keyboard layout)
            update: Telegram update object
            context: Bot context
            options: Optional list of options (if None, uses default for question_type)
            timeout: Timeout in seconds (default 5 minutes)
        
        Returns:
            User's choice (callback_data value) or None if timeout
        """
        user_id = update.effective_user.id if hasattr(update, 'effective_user') else 0
        pause_id = f"{user_id}_{question_type}_{int(time.time())}"
        
        # Create keyboard
        keyboard = self.create_interactive_keyboard(question_type, context)
        
        # Send question with keyboard
        try:
            message = await update.message.reply_text(
                question,
                parse_mode='Markdown',
                reply_markup=keyboard
            )
            
            # Store pending response
            self.pending_responses[pause_id] = {
                'user_id': user_id,
                'question_type': question_type,
                'message_id': message.message_id,
                'response': None,
                'timestamp': time.time()
            }
            
            # Store in context for callback handler
            if hasattr(context, 'user_data'):
                context.user_data[f'pending_pause_{pause_id}'] = {
                    'pause_id': pause_id,
                    'question_type': question_type,
                    'timeout': timeout
                }
            
            # Wait for response (poll context for response - shared state)
            start_time = time.time()
            while time.time() - start_time < timeout:
                # Check instance storage
                if pause_id in self.pending_responses:
                    response = self.pending_responses[pause_id].get('response')
                    if response is not None:
                        # Clean up
                        del self.pending_responses[pause_id]
                        if hasattr(context, 'user_data'):
                            context.user_data.pop(f'pending_pause_{pause_id}', None)
                            context.user_data.get('pending_pause_responses', {}).pop(pause_id, None)
                        return response
                
                # Check context storage (for callback handler)
                if hasattr(context, 'user_data'):
                    pending_responses = context.user_data.get('pending_pause_responses', {})
                    if pause_id in pending_responses:
                        response = pending_responses[pause_id]
                        # Clean up
                        del pending_responses[pause_id]
                        if pause_id in self.pending_responses:
                            del self.pending_responses[pause_id]
                        context.user_data.pop(f'pending_pause_{pause_id}', None)
                        return response
                
                await asyncio.sleep(1)  # Check every second
            
            # Timeout
            logger.warning(f"Pause timeout for {question_type} after {timeout}s")
            if pause_id in self.pending_responses:
                del self.pending_responses[pause_id]
            return None
            
        except Exception as e:
            logger.error(f"Error in pause_and_ask_user: {e}")
            return None
    
    def detect_pause_points(self, task_type: str, current_step: str) -> List[str]:
        """Detect natural pause points in task execution
        
        Args:
            task_type: Type of task (brute_force, script_generation, etc.)
            current_step: Current step in execution
        
        Returns:
            List of pause point types that should be triggered
        """
        pause_points = []
        
        if task_type == "brute_force" or "brute" in current_step.lower():
            if "generating" in current_step.lower() or "code" in current_step.lower():
                pause_points.append("run_test_after_generation")
            if "executing" in current_step.lower() or "testing" in current_step.lower():
                pause_points.append("has_combolist")
        
        elif task_type == "script_generation" or "script" in current_step.lower():
            if "generating" in current_step.lower():
                pause_points.append("run_test_after_generation")
            if "executing" in current_step.lower():
                pause_points.append("has_resources")
        
        elif task_type == "code_generation":
            if "generated" in current_step.lower() or "created" in current_step.lower():
                pause_points.append("run_test_after_generation")
        
        return pause_points
    
    def handle_user_response(self, pause_id: str, response: str) -> bool:
        """Handle user response to pause question
        
        Args:
            pause_id: Pause ID from pause_and_ask_user
            response: User's response (callback_data value)
        
        Returns:
            True if response was handled, False if pause_id not found
        """
        if pause_id in self.pending_responses:
            self.pending_responses[pause_id]['response'] = response
            return True
        return False
