# -*- coding: utf-8 -*-
"""
Multi-Model Manager - Routes requests to appropriate AI models
DeepSeek for text/code, Vision models for images
"""

import os
import logging
from typing import Dict, Optional, List, Any, Union
from enum import Enum

logger = logging.getLogger(__name__)


class ModelType(Enum):
    """Types of models available"""
    TEXT = "text"  # DeepSeek for text/code
    VISION = "vision"  # Vision models for images
    MULTIMODAL = "multimodal"  # Models that handle both


class TaskType(Enum):
    """Types of tasks"""
    TEXT_QUERY = "text_query"
    CODE_GENERATION = "code_generation"
    IMAGE_ANALYSIS = "image_analysis"
    IMAGE_CAPTION = "image_caption"
    SCREENSHOT_READ = "screenshot_read"
    IMAGE_CONVERSION = "image_conversion"
    MULTIMODAL = "multimodal"


class MultiModelManager:
    """Manages routing between different AI models"""
    
    def __init__(self, deepseek_keys: List[str], vision_models_config: Optional[Dict] = None):
        self.deepseek_keys = deepseek_keys
        self.vision_models_config = vision_models_config or {}
        self.primary_model = "deepseek"  # DeepSeek is always primary for text/code
        
        # Model availability flags
        self.deepseek_available = bool(deepseek_keys)
        self.huggingface_available = False
        self.openrouter_available = False
        
        # Initialize vision models if configured
        self._initialize_vision_models()
    
    def _initialize_vision_models(self):
        """Initialize vision model connections"""
        # Check Hugging Face
        hf_key = os.getenv('HUGGINGFACE_API_KEY')
        if hf_key:
            try:
                # Will be initialized lazily when needed
                self.huggingface_available = True
                logger.info("Hugging Face API key found")
            except Exception as e:
                logger.warning(f"Hugging Face initialization failed: {e}")
        
        # Check OpenRouter
        openrouter_key = os.getenv('OPENROUTER_API_KEY')
        if openrouter_key:
            try:
                # Will be initialized lazily when needed
                self.openrouter_available = True
                logger.info("OpenRouter API key found")
            except Exception as e:
                logger.warning(f"OpenRouter initialization failed: {e}")
    
    def detect_task_type(self, message: str, has_image: bool = False) -> TaskType:
        """
        Detect what type of task this is
        Returns appropriate TaskType
        """
        if has_image:
            message_lower = message.lower()
            
            if any(keyword in message_lower for keyword in ['screenshot', 'screen', 'capture']):
                return TaskType.SCREENSHOT_READ
            elif any(keyword in message_lower for keyword in ['caption', 'describe', 'what is']):
                return TaskType.IMAGE_CAPTION
            elif any(keyword in message_lower for keyword in ['convert', 'transform', 'resize']):
                return TaskType.IMAGE_CONVERSION
            else:
                return TaskType.IMAGE_ANALYSIS
        
        message_lower = message.lower()
        
        # Check for code-related keywords
        code_keywords = ['code', 'function', 'script', 'program', 'implement', 'create a', 'write']
        if any(keyword in message_lower for keyword in code_keywords):
            return TaskType.CODE_GENERATION
        
        return TaskType.TEXT_QUERY
    
    def select_model(self, task_type: TaskType, has_image: bool = False) -> Dict[str, Any]:
        """
        Select appropriate model for the task
        Returns model config dict with: type, provider, model_name, api_key
        """
        # For text/code tasks, always use DeepSeek
        if task_type in [TaskType.TEXT_QUERY, TaskType.CODE_GENERATION]:
            if not self.deepseek_available:
                raise ValueError("DeepSeek API keys not available")
            
            return {
                'type': ModelType.TEXT,
                'provider': 'deepseek',
                'model_name': 'deepseek-chat',
                'api_keys': self.deepseek_keys,
                'primary': True
            }
        
        # For vision tasks, try fallback chain
        if task_type in [TaskType.IMAGE_ANALYSIS, TaskType.IMAGE_CAPTION, 
                         TaskType.SCREENSHOT_READ, TaskType.IMAGE_CONVERSION]:
            
            # Try OpenRouter first (if available)
            if self.openrouter_available:
                return {
                    'type': ModelType.VISION,
                    'provider': 'openrouter',
                    'model_name': 'openai/gpt-4-vision-preview',  # Or other vision model
                    'api_key': os.getenv('OPENROUTER_API_KEY'),
                    'primary': False,
                    'fallback': 'huggingface'
                }
            
            # Fallback to Hugging Face
            if self.huggingface_available:
                return {
                    'type': ModelType.VISION,
                    'provider': 'huggingface',
                    'model_name': 'Salesforce/blip-image-captioning-base',  # Default vision model
                    'api_key': os.getenv('HUGGINGFACE_API_KEY'),
                    'primary': False,
                    'fallback': None
                }
            
            # If no vision models available, return error
            raise ValueError("No vision models available. Please configure Hugging Face or OpenRouter API keys.")
        
        # Default: use DeepSeek
        return {
            'type': ModelType.TEXT,
            'provider': 'deepseek',
            'model_name': 'deepseek-chat',
            'api_keys': self.deepseek_keys,
            'primary': True
        }
    
    def get_model_for_request(self, message: str, has_image: bool = False) -> Dict[str, Any]:
        """
        Main method to get appropriate model for a request
        Combines task detection and model selection
        """
        task_type = self.detect_task_type(message, has_image)
        model_config = self.select_model(task_type, has_image)
        
        logger.info(f"Selected model: {model_config['provider']} for task: {task_type.value}")
        
        return model_config
    
    def should_use_vision_model(self, message: str, has_image: bool = False) -> bool:
        """Quick check if vision model should be used"""
        if has_image:
            return True
        
        # Check message for image-related requests
        image_keywords = ['image', 'picture', 'photo', 'screenshot', 'screenshot', 
                         'read image', 'analyze image', 'what is in this']
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in image_keywords)
    
    def get_fallback_model(self, current_provider: str) -> Optional[Dict[str, Any]]:
        """Get fallback model if primary fails"""
        if current_provider == 'openrouter':
            if self.huggingface_available:
                return {
                    'type': ModelType.VISION,
                    'provider': 'huggingface',
                    'model_name': 'Salesforce/blip-image-captioning-base',
                    'api_key': os.getenv('HUGGINGFACE_API_KEY'),
                    'primary': False
                }
        
        elif current_provider == 'huggingface':
            if self.openrouter_available:
                return {
                    'type': ModelType.VISION,
                    'provider': 'openrouter',
                    'model_name': 'openai/gpt-4-vision-preview',
                    'api_key': os.getenv('OPENROUTER_API_KEY'),
                    'primary': False
                }
        
        # For DeepSeek, try next key in rotation
        if current_provider == 'deepseek' and len(self.deepseek_keys) > 1:
            # Rotation is handled in HacxGPT, just return same config
            return None
        
        return None
    
    def is_model_available(self, provider: str) -> bool:
        """Check if a specific model provider is available"""
        if provider == 'deepseek':
            return self.deepseek_available
        elif provider == 'huggingface':
            return self.huggingface_available
        elif provider == 'openrouter':
            return self.openrouter_available
        return False


# Global manager instance
_manager_instance = None

def get_model_manager(deepseek_keys: List[str], vision_config: Optional[Dict] = None) -> MultiModelManager:
    """Get or create global model manager instance"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = MultiModelManager(deepseek_keys, vision_config)
    return _manager_instance
