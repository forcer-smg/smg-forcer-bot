# -*- coding: utf-8 -*-
"""
Image Generator - Generate images from text prompts using Pollinations.AI
Completely free, no API key required
"""

import os
import logging
import requests
from typing import Dict, Optional, List
from pathlib import Path
from urllib.parse import quote
import time

logger = logging.getLogger(__name__)


class ImageGenerator:
    """Generate images from text prompts using Pollinations.AI"""
    
    def __init__(self, output_dir: str = "generated_images"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Pollinations.AI API (completely free, no API key)
        self.base_url = "https://image.pollinations.ai/prompt"
        
        # Available models
        self.models = {
            'stable-diffusion': 'stable-diffusion',
            'flux': 'flux',
            'flux-schnell': 'flux-schnell',
            'realistic': 'realistic',
            'anime': 'anime',
            'default': None  # Default model
        }
        
        logger.info("Image Generator initialized (Pollinations.AI - Free)")
    
    def generate_image(self,
                      prompt: str,
                      model: str = "default",
                      width: int = 1024,
                      height: int = 1024,
                      seed: Optional[int] = None,
                      nologo: bool = True,
                      enhance: bool = False,
                      filename: str = None) -> Optional[str]:
        """
        Generate image from text prompt
        
        Args:
            prompt: Text description of the image
            model: Model to use (stable-diffusion, flux, flux-schnell, realistic, anime, default)
            width: Image width (default: 1024)
            height: Image height (default: 1024)
            seed: Random seed for reproducibility (optional)
            nologo: Remove logo watermark (default: True)
            enhance: Enhance prompt automatically (default: False)
            filename: Output filename (auto-generated if None)
        
        Returns:
            Path to generated image file or None if failed
        """
        try:
            # Build prompt with parameters
            full_prompt = prompt
            
            # Add model parameter if specified
            if model and model != "default" and model in self.models:
                full_prompt = f"{full_prompt}, model:{model}"
            
            # Build URL with parameters
            params = {
                'prompt': full_prompt,
                'width': width,
                'height': height,
            }
            
            if seed is not None:
                params['seed'] = seed
            
            if nologo:
                params['nologo'] = 'true'
            
            if enhance:
                params['enhance'] = 'true'
            
            # Build query string
            query_parts = []
            for key, value in params.items():
                query_parts.append(f"{key}={quote(str(value))}")
            
            url = f"{self.base_url}?{'&'.join(query_parts)}"
            
            logger.info(f"Generating image with prompt: {prompt[:100]}...")
            
            # Download image
            response = requests.get(url, stream=True, timeout=120)
            response.raise_for_status()
            
            # Generate filename if not provided
            if not filename:
                timestamp = int(time.time())
                safe_prompt = "".join(c for c in prompt[:50] if c.isalnum() or c in (' ', '-', '_')).strip()
                safe_prompt = safe_prompt.replace(' ', '_')
                filename = f"generated_{safe_prompt}_{timestamp}.png"
            
            if not filename.endswith(('.png', '.jpg', '.jpeg')):
                filename += '.png'
            
            filepath = self.output_dir / filename
            
            # Save image
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Image generated: {filepath}")
            return str(filepath)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error generating image (network): {e}")
            return None
        except Exception as e:
            logger.error(f"Error generating image: {e}", exc_info=True)
            return None
    
    def generate_multiple(self,
                         prompts: List[str],
                         model: str = "default",
                         width: int = 1024,
                         height: int = 1024) -> List[Optional[str]]:
        """
        Generate multiple images from prompts
        
        Args:
            prompts: List of text prompts
            model: Model to use
            width: Image width
            height: Image height
        
        Returns:
            List of file paths (None for failed generations)
        """
        results = []
        for i, prompt in enumerate(prompts):
            logger.info(f"Generating image {i+1}/{len(prompts)}")
            result = self.generate_image(
                prompt=prompt,
                model=model,
                width=width,
                height=height,
                filename=f"batch_{i+1}_{int(time.time())}.png"
            )
            results.append(result)
            # Small delay to avoid rate limiting
            time.sleep(1)
        
        return results
    
    def enhance_prompt(self, prompt: str) -> str:
        """
        Enhance prompt for better results
        
        Args:
            prompt: Original prompt
        
        Returns:
            Enhanced prompt
        """
        # Add quality keywords
        enhancements = [
            "high quality",
            "detailed",
            "professional",
            "4k",
            "sharp focus"
        ]
        
        enhanced = prompt
        prompt_lower = prompt.lower()
        
        # Add enhancements if not already present
        for enhancement in enhancements:
            if enhancement not in prompt_lower:
                enhanced += f", {enhancement}"
        
        return enhanced
    
    def get_available_models(self) -> List[str]:
        """Get list of available models"""
        return list(self.models.keys())
    
    def validate_prompt(self, prompt: str) -> Dict[str, Any]:
        """
        Validate prompt and provide suggestions
        
        Args:
            prompt: Text prompt
        
        Returns:
            Dict with validation results and suggestions
        """
        result = {
            'valid': True,
            'warnings': [],
            'suggestions': []
        }
        
        if not prompt or len(prompt.strip()) == 0:
            result['valid'] = False
            result['warnings'].append("Prompt is empty")
            return result
        
        if len(prompt) < 5:
            result['warnings'].append("Prompt is very short, may produce poor results")
        
        if len(prompt) > 500:
            result['warnings'].append("Prompt is very long, may be truncated")
        
        # Check for common issues
        if prompt.lower().count('and') > 5:
            result['suggestions'].append("Consider splitting into multiple prompts for complex scenes")
        
        # Suggest enhancements
        prompt_lower = prompt.lower()
        if 'quality' not in prompt_lower and 'detailed' not in prompt_lower:
            result['suggestions'].append("Consider adding quality descriptors for better results")
        
        return result


# Global instance
_image_generator_instance = None

def get_image_generator(output_dir: str = "generated_images") -> ImageGenerator:
    """Get or create global image generator instance"""
    global _image_generator_instance
    if _image_generator_instance is None:
        _image_generator_instance = ImageGenerator(output_dir)
    return _image_generator_instance
