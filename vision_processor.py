# -*- coding: utf-8 -*-
"""
Vision Processor - Handles image processing using Hugging Face and OpenRouter
Provides image captioning, analysis, and conversion capabilities
"""

import os
import io
import base64
import logging
from typing import Dict, Optional, Union, List
from pathlib import Path
import requests

logger = logging.getLogger(__name__)

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    logger.warning("Pillow not available. Image processing will be limited.")


class VisionProcessor:
    """Processes images using multiple vision model providers"""
    
    def __init__(self, huggingface_key: Optional[str] = None, openrouter_key: Optional[str] = None):
        self.huggingface_key = huggingface_key or os.getenv('HUGGINGFACE_API_KEY')
        self.openrouter_key = openrouter_key or os.getenv('OPENROUTER_API_KEY')
        self.hf_available = bool(self.huggingface_key)
        self.or_available = bool(self.openrouter_key)
        
        # Hugging Face models
        self.hf_models = {
            'caption': 'Salesforce/blip-image-captioning-base',
            'vqa': 'dandelin/vilt-b32-finetuned-vqa',
            'clip': 'openai/clip-vit-base-patch32'
        }
    
    def process_image_huggingface(self, image_data: Union[bytes, str, Path], 
                                   task: str = 'caption') -> Dict:
        """
        Process image using Hugging Face Inference API
        task: 'caption', 'vqa', or 'clip'
        """
        if not self.hf_available:
            raise ValueError("Hugging Face API key not configured")
        
        # Prepare image
        image_bytes = self._prepare_image(image_data)
        if not image_bytes:
            raise ValueError("Failed to prepare image data")
        
        # Select model
        model = self.hf_models.get(task, self.hf_models['caption'])
        
        # Hugging Face Inference API endpoint
        api_url = f"https://api-inference.huggingface.co/models/{model}"
        
        headers = {
            "Authorization": f"Bearer {self.huggingface_key}",
            "Content-Type": "application/octet-stream"
        }
        
        try:
            response = requests.post(api_url, headers=headers, data=image_bytes, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            # Format response based on task
            if task == 'caption':
                if isinstance(result, list) and len(result) > 0:
                    caption = result[0].get('generated_text', 'No caption generated')
                elif isinstance(result, dict):
                    caption = result.get('generated_text', str(result))
                else:
                    caption = str(result)
                
                return {
                    'success': True,
                    'provider': 'huggingface',
                    'task': task,
                    'result': caption,
                    'raw': result
                }
            else:
                return {
                    'success': True,
                    'provider': 'huggingface',
                    'task': task,
                    'result': result,
                    'raw': result
                }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Hugging Face API error: {e}")
            return {
                'success': False,
                'provider': 'huggingface',
                'error': str(e)
            }
    
    def process_image_openrouter(self, image_data: Union[bytes, str, Path], 
                                 prompt: str = "What is in this image?") -> Dict:
        """
        Process image using OpenRouter API with vision models
        """
        if not self.or_available:
            raise ValueError("OpenRouter API key not configured")
        
        # Prepare image
        image_bytes = self._prepare_image(image_data)
        if not image_bytes:
            raise ValueError("Failed to prepare image data")
        
        # Convert to base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # OpenRouter API endpoint
        api_url = "https://openrouter.ai/api/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/forcer-smg/smg-forcer-bot",
            "X-Title": "SMG-Forcer-Bot"
        }
        
        # Try different vision models (fallback chain)
        vision_models = [
            "openai/gpt-4-vision-preview",
            "google/gemini-pro-vision",
            "anthropic/claude-3-opus",
            "anthropic/claude-3-sonnet"
        ]
        
        for model in vision_models:
            try:
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": prompt
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_base64}"
                                    }
                                }
                            ]
                        }
                    ],
                    "max_tokens": 1000
                }
                
                response = requests.post(api_url, headers=headers, json=payload, timeout=60)
                
                if response.status_code == 200:
                    result = response.json()
                    content = result['choices'][0]['message']['content']
                    
                    return {
                        'success': True,
                        'provider': 'openrouter',
                        'model': model,
                        'result': content,
                        'raw': result
                    }
                elif response.status_code == 404:
                    # Model not available, try next
                    continue
                else:
                    response.raise_for_status()
            
            except requests.exceptions.RequestException as e:
                logger.warning(f"OpenRouter model {model} failed: {e}")
                continue
        
        # All models failed
        return {
            'success': False,
            'provider': 'openrouter',
            'error': 'All vision models failed'
        }
    
    def process_image(self, image_data: Union[bytes, str, Path], 
                     task: str = 'caption',
                     prompt: Optional[str] = None,
                     prefer_provider: str = 'openrouter') -> Dict:
        """
        Process image using best available provider
        prefer_provider: 'openrouter' or 'huggingface'
        """
        # Try preferred provider first
        if prefer_provider == 'openrouter' and self.or_available:
            try:
                result = self.process_image_openrouter(
                    image_data, 
                    prompt or "Describe this image in detail."
                )
                if result.get('success'):
                    return result
            except Exception as e:
                logger.warning(f"OpenRouter failed: {e}")
        
        # Fallback to Hugging Face
        if self.hf_available:
            try:
                result = self.process_image_huggingface(image_data, task)
                if result.get('success'):
                    return result
            except Exception as e:
                logger.warning(f"Hugging Face failed: {e}")
        
        # Both failed
        return {
            'success': False,
            'error': 'No vision models available or all failed'
        }
    
    def _prepare_image(self, image_data: Union[bytes, str, Path]) -> Optional[bytes]:
        """Prepare image data for API requests"""
        try:
            # If it's already bytes
            if isinstance(image_data, bytes):
                return image_data
            
            # If it's a file path
            if isinstance(image_data, (str, Path)):
                path = Path(image_data)
                if path.exists():
                    return path.read_bytes()
                # Maybe it's a URL?
                if str(image_data).startswith(('http://', 'https://')):
                    response = requests.get(str(image_data), timeout=10)
                    response.raise_for_status()
                    return response.content
            
            # If it's a PIL Image
            if PILLOW_AVAILABLE and hasattr(image_data, 'save'):
                img_io = io.BytesIO()
                image_data.save(img_io, format='JPEG')
                return img_io.getvalue()
            
            return None
        
        except Exception as e:
            logger.error(f"Failed to prepare image: {e}")
            return None
    
    def convert_image(self, image_data: Union[bytes, str, Path], 
                     format: str = 'png',
                     resize: Optional[tuple] = None) -> Optional[bytes]:
        """
        Convert image format and optionally resize
        Returns converted image as bytes
        """
        if not PILLOW_AVAILABLE:
            logger.warning("Pillow not available for image conversion")
            return None
        
        try:
            # Load image
            if isinstance(image_data, bytes):
                img = Image.open(io.BytesIO(image_data))
            elif isinstance(image_data, (str, Path)):
                img = Image.open(image_data)
            else:
                img = image_data
            
            # Resize if requested
            if resize:
                img = img.resize(resize, Image.Resampling.LANCZOS)
            
            # Convert format
            output = io.BytesIO()
            img.save(output, format=format.upper())
            return output.getvalue()
        
        except Exception as e:
            logger.error(f"Image conversion failed: {e}")
            return None
    
    def analyze_screenshot(self, image_data: Union[bytes, str, Path]) -> Dict:
        """Analyze screenshot and extract text/information"""
        prompt = """Analyze this screenshot in detail. Describe:
1. What application or website is shown
2. Any visible text content
3. UI elements and their states
4. Any errors or warnings
5. Overall context and purpose"""
        
        return self.process_image(image_data, prompt=prompt)


# Global processor instance
_processor_instance = None

def get_vision_processor(hf_key: Optional[str] = None, or_key: Optional[str] = None) -> VisionProcessor:
    """Get or create global vision processor instance"""
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = VisionProcessor(hf_key, or_key)
    return _processor_instance
