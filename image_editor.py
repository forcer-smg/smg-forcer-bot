# -*- coding: utf-8 -*-
"""
Advanced Image Editor - Text overlay, filters, manipulation using Pillow
Extends vision_processor.py with advanced editing capabilities
"""

import os
import logging
import time
from typing import Dict, Optional, Tuple, Union, List
from pathlib import Path
import io

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    logger.warning("Pillow not available. Image editing will be limited.")


class ImageEditor:
    """Advanced image editing with Pillow"""
    
    def __init__(self, output_dir: str = "edited_images"):
        if not PILLOW_AVAILABLE:
            raise ImportError("Pillow is required for image editing. Install with: pip install Pillow")
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("Image Editor initialized")
    
    def add_text_overlay(self,
                        image_path: Union[str, Path, Image.Image],
                        text: str,
                        position: Tuple[int, int] = None,
                        font_size: int = 40,
                        font_color: Tuple[int, int, int] = (255, 255, 255),
                        font_path: str = None,
                        background_color: Optional[Tuple[int, int, int]] = None,
                        output_path: str = None) -> Optional[str]:
        """
        Add text overlay to image
        
        Args:
            image_path: Path to image or PIL Image object
            text: Text to add
            position: (x, y) position (None = center)
            font_size: Font size in pixels
            font_color: RGB color tuple
            font_path: Path to custom font file
            background_color: Optional background color for text
            output_path: Output file path (auto-generated if None)
        
        Returns:
            Path to edited image or None if failed
        """
        try:
            # Load image
            if isinstance(image_path, Image.Image):
                img = image_path.copy()
            else:
                img = Image.open(image_path)
            
            # Convert to RGB if needed
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Create drawing context
            draw = ImageDraw.Draw(img)
            
            # Load font
            try:
                if font_path and os.path.exists(font_path):
                    font = ImageFont.truetype(font_path, font_size)
                else:
                    # Try to use default font
                    try:
                        font = ImageFont.truetype("arial.ttf", font_size)
                    except:
                        try:
                            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
                        except:
                            font = ImageFont.load_default()
            except:
                font = ImageFont.load_default()
            
            # Get text dimensions
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            # Calculate position
            if position is None:
                # Center
                x = (img.width - text_width) // 2
                y = (img.height - text_height) // 2
            else:
                x, y = position
            
            # Draw background if specified
            if background_color:
                padding = 10
                draw.rectangle(
                    [x - padding, y - padding, x + text_width + padding, y + text_height + padding],
                    fill=background_color
                )
            
            # Draw text
            draw.text((x, y), text, font=font, fill=font_color)
            
            # Save image
            if output_path is None:
                timestamp = int(time.time())
                output_path = self.output_dir / f"text_overlay_{timestamp}.png"
            else:
                output_path = Path(output_path)
            
            img.save(output_path)
            logger.info(f"Text overlay added: {output_path}")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Error adding text overlay: {e}", exc_info=True)
            return None
    
    def apply_filter(self,
                    image_path: Union[str, Path, Image.Image],
                    filter_type: str,
                    intensity: float = 1.0,
                    output_path: str = None) -> Optional[str]:
        """
        Apply filter to image
        
        Args:
            image_path: Path to image or PIL Image object
            filter_type: 'blur', 'sharpen', 'emboss', 'edge_enhance', 'smooth'
            intensity: Filter intensity (0.0 to 2.0)
            output_path: Output file path
        
        Returns:
            Path to edited image or None if failed
        """
        try:
            # Load image
            if isinstance(image_path, Image.Image):
                img = image_path.copy()
            else:
                img = Image.open(image_path)
            
            # Apply filter
            if filter_type == 'blur':
                img = img.filter(ImageFilter.GaussianBlur(radius=intensity * 2))
            elif filter_type == 'sharpen':
                img = img.filter(ImageFilter.SHARPEN)
                if intensity > 1.0:
                    for _ in range(int(intensity) - 1):
                        img = img.filter(ImageFilter.SHARPEN)
            elif filter_type == 'emboss':
                img = img.filter(ImageFilter.EMBOSS)
            elif filter_type == 'edge_enhance':
                img = img.filter(ImageFilter.EDGE_ENHANCE)
            elif filter_type == 'smooth':
                img = img.filter(ImageFilter.SMOOTH)
            else:
                logger.warning(f"Unknown filter type: {filter_type}")
                return None
            
            # Save image
            if output_path is None:
                timestamp = int(time.time())
                output_path = self.output_dir / f"filtered_{filter_type}_{timestamp}.png"
            else:
                output_path = Path(output_path)
            
            img.save(output_path)
            logger.info(f"Filter applied: {output_path}")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Error applying filter: {e}", exc_info=True)
            return None
    
    def adjust_brightness(self,
                         image_path: Union[str, Path, Image.Image],
                         factor: float,
                         output_path: str = None) -> Optional[str]:
        """
        Adjust image brightness
        
        Args:
            image_path: Path to image or PIL Image object
            factor: Brightness factor (0.0 = black, 1.0 = original, 2.0 = very bright)
            output_path: Output file path
        
        Returns:
            Path to edited image or None if failed
        """
        try:
            if isinstance(image_path, Image.Image):
                img = image_path.copy()
            else:
                img = Image.open(image_path)
            
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(factor)
            
            if output_path is None:
                timestamp = int(time.time())
                output_path = self.output_dir / f"brightness_{timestamp}.png"
            else:
                output_path = Path(output_path)
            
            img.save(output_path)
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Error adjusting brightness: {e}", exc_info=True)
            return None
    
    def adjust_contrast(self,
                      image_path: Union[str, Path, Image.Image],
                      factor: float,
                      output_path: str = None) -> Optional[str]:
        """Adjust image contrast"""
        try:
            if isinstance(image_path, Image.Image):
                img = image_path.copy()
            else:
                img = Image.open(image_path)
            
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(factor)
            
            if output_path is None:
                timestamp = int(time.time())
                output_path = self.output_dir / f"contrast_{timestamp}.png"
            else:
                output_path = Path(output_path)
            
            img.save(output_path)
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Error adjusting contrast: {e}", exc_info=True)
            return None
    
    def crop(self,
            image_path: Union[str, Path, Image.Image],
            box: Tuple[int, int, int, int],
            output_path: str = None) -> Optional[str]:
        """
        Crop image
        
        Args:
            image_path: Path to image or PIL Image object
            box: (left, top, right, bottom) crop box
            output_path: Output file path
        
        Returns:
            Path to cropped image or None if failed
        """
        try:
            if isinstance(image_path, Image.Image):
                img = image_path.copy()
            else:
                img = Image.open(image_path)
            
            img = img.crop(box)
            
            if output_path is None:
                timestamp = int(time.time())
                output_path = self.output_dir / f"cropped_{timestamp}.png"
            else:
                output_path = Path(output_path)
            
            img.save(output_path)
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Error cropping image: {e}", exc_info=True)
            return None
    
    def rotate(self,
              image_path: Union[str, Path, Image.Image],
              angle: float,
              expand: bool = True,
              output_path: str = None) -> Optional[str]:
        """
        Rotate image
        
        Args:
            image_path: Path to image or PIL Image object
            angle: Rotation angle in degrees (counter-clockwise)
            expand: Expand image to fit rotated content
            output_path: Output file path
        
        Returns:
            Path to rotated image or None if failed
        """
        try:
            if isinstance(image_path, Image.Image):
                img = image_path.copy()
            else:
                img = Image.open(image_path)
            
            img = img.rotate(angle, expand=expand, fillcolor='white')
            
            if output_path is None:
                timestamp = int(time.time())
                output_path = self.output_dir / f"rotated_{timestamp}.png"
            else:
                output_path = Path(output_path)
            
            img.save(output_path)
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Error rotating image: {e}", exc_info=True)
            return None
    
    def resize(self,
              image_path: Union[str, Path, Image.Image],
              size: Tuple[int, int],
              maintain_aspect: bool = True,
              output_path: str = None) -> Optional[str]:
        """
        Resize image
        
        Args:
            image_path: Path to image or PIL Image object
            size: (width, height) target size
            maintain_aspect: Maintain aspect ratio
            output_path: Output file path
        
        Returns:
            Path to resized image or None if failed
        """
        try:
            if isinstance(image_path, Image.Image):
                img = image_path.copy()
            else:
                img = Image.open(image_path)
            
            if maintain_aspect:
                img.thumbnail(size, Image.Resampling.LANCZOS)
            else:
                img = img.resize(size, Image.Resampling.LANCZOS)
            
            if output_path is None:
                timestamp = int(time.time())
                output_path = self.output_dir / f"resized_{timestamp}.png"
            else:
                output_path = Path(output_path)
            
            img.save(output_path)
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Error resizing image: {e}", exc_info=True)
            return None
    
    def combine_images(self,
                      image_paths: List[Union[str, Path, Image.Image]],
                      direction: str = "horizontal",
                      spacing: int = 10,
                      output_path: str = None) -> Optional[str]:
        """
        Combine multiple images
        
        Args:
            image_paths: List of image paths or PIL Image objects
            direction: 'horizontal' or 'vertical'
            spacing: Spacing between images in pixels
            output_path: Output file path
        
        Returns:
            Path to combined image or None if failed
        """
        try:
            # Load all images
            images = []
            for img_path in image_paths:
                if isinstance(img_path, Image.Image):
                    images.append(img_path.copy())
                else:
                    images.append(Image.open(img_path))
            
            if not images:
                return None
            
            # Calculate dimensions
            if direction == "horizontal":
                total_width = sum(img.width for img in images) + spacing * (len(images) - 1)
                max_height = max(img.height for img in images)
                new_img = Image.new('RGB', (total_width, max_height), color='white')
                
                x_offset = 0
                for img in images:
                    # Center vertically
                    y_offset = (max_height - img.height) // 2
                    new_img.paste(img, (x_offset, y_offset))
                    x_offset += img.width + spacing
            else:  # vertical
                max_width = max(img.width for img in images)
                total_height = sum(img.height for img in images) + spacing * (len(images) - 1)
                new_img = Image.new('RGB', (max_width, total_height), color='white')
                
                y_offset = 0
                for img in images:
                    # Center horizontally
                    x_offset = (max_width - img.width) // 2
                    new_img.paste(img, (x_offset, y_offset))
                    y_offset += img.height + spacing
            
            if output_path is None:
                timestamp = int(time.time())
                output_path = self.output_dir / f"combined_{timestamp}.png"
            else:
                output_path = Path(output_path)
            
            new_img.save(output_path)
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Error combining images: {e}", exc_info=True)
            return None
    
    def add_watermark(self,
                     image_path: Union[str, Path, Image.Image],
                     watermark_text: str,
                     opacity: float = 0.5,
                     output_path: str = None) -> Optional[str]:
        """
        Add watermark to image
        
        Args:
            image_path: Path to image or PIL Image object
            watermark_text: Watermark text
            opacity: Opacity (0.0 to 1.0)
            output_path: Output file path
        
        Returns:
            Path to watermarked image or None if failed
        """
        try:
            if isinstance(image_path, Image.Image):
                img = image_path.copy()
            else:
                img = Image.open(image_path)
            
            # Create watermark layer
            watermark = Image.new('RGBA', img.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(watermark)
            
            # Use default font
            font = ImageFont.load_default()
            
            # Get text size
            bbox = draw.textbbox((0, 0), watermark_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            # Position (bottom right)
            x = img.width - text_width - 20
            y = img.height - text_height - 20
            
            # Draw text with opacity
            alpha = int(255 * opacity)
            draw.text((x, y), watermark_text, font=font, fill=(255, 255, 255, alpha))
            
            # Composite watermark onto image
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            img = Image.alpha_composite(img, watermark)
            
            if output_path is None:
                timestamp = int(time.time())
                output_path = self.output_dir / f"watermarked_{timestamp}.png"
            else:
                output_path = Path(output_path)
            
            img.save(output_path)
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Error adding watermark: {e}", exc_info=True)
            return None


# Global instance
_image_editor_instance = None

def get_image_editor(output_dir: str = "edited_images") -> ImageEditor:
    """Get or create global image editor instance"""
    global _image_editor_instance
    if _image_editor_instance is None:
        _image_editor_instance = ImageEditor(output_dir)
    return _image_editor_instance
