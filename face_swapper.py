# -*- coding: utf-8 -*-
"""
Face Swapper - Swap faces between images with contextual instructions support
Uses free APIs (AI Photocraft) and integrates with AI for context understanding
"""

import os
import logging
import requests
from typing import Dict, Optional, Tuple, Union, List
from pathlib import Path
import time
import base64

logger = logging.getLogger(__name__)


class FaceSwapper:
    """Swap faces between images with contextual instructions"""
    
    def __init__(self, output_dir: str = "face_swapped_images"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # AI Photocraft API (completely free, no API key)
        self.api_url = "https://api.aiphotocraft.com/face-swap"
        
        # Alternative APIs (fallback)
        self.lightx_url = "https://api.lightxeditor.com/face-swap"
        self.changeface_url = "https://api.changeface.io/api/face-swap"
        
        logger.info("Face Swapper initialized (AI Photocraft - Free)")
    
    def swap_faces(self,
                  source_image_path: Union[str, Path],
                  target_image_path: Union[str, Path],
                  context_instruction: str = None,
                  output_path: str = None,
                  use_ai_context: bool = True) -> Optional[str]:
        """
        Swap faces between two images
        
        Args:
            source_image_path: Path to source image (face to swap from)
            target_image_path: Path to target image (face to swap to)
            context_instruction: Optional contextual instruction (e.g., "holding a card", "in this pose")
            output_path: Output file path (auto-generated if None)
            use_ai_context: Use AI to process contextual instructions (requires AI integration)
        
        Returns:
            Path to swapped image or None if failed
        """
        try:
            # If contextual instruction provided, process it
            if context_instruction and use_ai_context:
                # Process context with AI (this would integrate with HacxGPT)
                processed_target = self._process_contextual_instruction(
                    target_image_path,
                    context_instruction
                )
                if processed_target:
                    target_image_path = processed_target
            
            # Perform face swap
            result = self._perform_face_swap(source_image_path, target_image_path)
            
            if not result:
                return None
            
            # Save result
            if output_path is None:
                timestamp = int(time.time())
                output_path = self.output_dir / f"face_swap_{timestamp}.png"
            else:
                output_path = Path(output_path)
            
            # Save image
            with open(output_path, 'wb') as f:
                f.write(result)
            
            logger.info(f"Face swap completed: {output_path}")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Error swapping faces: {e}", exc_info=True)
            return None
    
    def _perform_face_swap(self,
                          source_image_path: Union[str, Path],
                          target_image_path: Union[str, Path]) -> Optional[bytes]:
        """
        Perform face swap using AI Photocraft API
        
        Args:
            source_image_path: Source image path
            target_image_path: Target image path
        
        Returns:
            Image bytes or None if failed
        """
        try:
            # Read images
            with open(source_image_path, 'rb') as f:
                source_image = f.read()
            
            with open(target_image_path, 'rb') as f:
                target_image = f.read()
            
            # Try AI Photocraft first (free, no API key)
            try:
                files = {
                    'source_image': ('source.jpg', source_image, 'image/jpeg'),
                    'target_image': ('target.jpg', target_image, 'image/jpeg')
                }
                
                response = requests.post(
                    self.api_url,
                    files=files,
                    timeout=60
                )
                
                if response.status_code == 200:
                    return response.content
                else:
                    logger.warning(f"AI Photocraft API returned {response.status_code}: {response.text}")
            except Exception as e:
                logger.warning(f"AI Photocraft API failed: {e}")
            
            # Fallback: Try alternative APIs if available
            # (These may require API keys)
            
            return None
            
        except Exception as e:
            logger.error(f"Error performing face swap: {e}", exc_info=True)
            return None
    
    def _process_contextual_instruction(self,
                                          target_image_path: Union[str, Path],
                                          context_instruction: str) -> Optional[str]:
        """
        Process contextual instruction to modify target image
        
        This integrates with image generation/editing to prepare the target image
        based on contextual requirements (e.g., "holding a card", "in this pose")
        
        Args:
            target_image_path: Original target image
            context_instruction: Contextual instruction
        
        Returns:
            Path to processed target image or None
        """
        try:
            # Import image generator and editor
            from image_generator import get_image_generator
            from image_editor import get_image_editor
            
            # Parse instruction
            instruction_lower = context_instruction.lower()
            
            # Check if we need to generate a new image or edit existing
            if any(keyword in instruction_lower for keyword in ['holding', 'with', 'card', 'object']):
                # Need to add object to image
                # For now, return original (can be enhanced with object detection/insertion)
                logger.info(f"Contextual instruction detected: {context_instruction}")
                # TODO: Integrate with object insertion/editing
                return None
            
            elif any(keyword in instruction_lower for keyword in ['pose', 'position', 'angle']):
                # May need to adjust pose (complex, would require pose estimation)
                logger.info(f"Pose instruction detected: {context_instruction}")
                return None
            
            # For now, return None (use original image)
            # This can be enhanced with actual image generation/editing integration
            return None
            
        except Exception as e:
            logger.warning(f"Error processing contextual instruction: {e}")
            return None
    
    def swap_faces_batch(self,
                        source_image_path: Union[str, Path],
                        target_image_paths: List[Union[str, Path]],
                        output_dir: str = None) -> List[Optional[str]]:
        """
        Swap face from one source to multiple targets
        
        Args:
            source_image_path: Source image path
            target_image_paths: List of target image paths
            output_dir: Output directory (auto-created if None)
        
        Returns:
            List of output file paths (None for failed swaps)
        """
        results = []
        output_dir = Path(output_dir) if output_dir else self.output_dir
        
        for i, target_path in enumerate(target_image_paths):
            logger.info(f"Swapping face {i+1}/{len(target_image_paths)}")
            output_path = output_dir / f"batch_swap_{i+1}_{int(time.time())}.png"
            result = self.swap_faces(
                source_image_path,
                target_path,
                output_path=str(output_path)
            )
            results.append(result)
            time.sleep(1)  # Rate limiting
        
        return results
    
    def detect_faces(self, image_path: Union[str, Path]) -> Dict:
        """
        Detect faces in image (for validation)
        
        Args:
            image_path: Image path
        
        Returns:
            Dict with face detection results
        """
        # This is a placeholder - actual face detection would require
        # a face detection library or API
        return {
            'faces_detected': 1,  # Placeholder
            'message': 'Face detection not implemented - using default'
        }


# Global instance
_face_swapper_instance = None

def get_face_swapper(output_dir: str = "face_swapped_images") -> FaceSwapper:
    """Get or create global face swapper instance"""
    global _face_swapper_instance
    if _face_swapper_instance is None:
        _face_swapper_instance = FaceSwapper(output_dir)
    return _face_swapper_instance
