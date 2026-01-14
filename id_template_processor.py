# -*- coding: utf-8 -*-
"""
ID Template Processor - Process ID templates and add photos
Handles Texas ID and other ID templates with image overlay
"""

import os
import logging
import time
from typing import Dict, Optional, Tuple
from pathlib import Path
import json

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    logger.warning("Pillow not available. ID processing will be limited.")

try:
    from psd_tools import PSDImage
    from psd_tools.api.layers import PixelLayer, GroupLayer, TypeLayer
    PSD_TOOLS_AVAILABLE = True
except ImportError:
    PSD_TOOLS_AVAILABLE = False
    logger.warning("psd-tools not available. PSD processing will be limited.")

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.warning("NumPy not available. Some advanced features may be limited.")


class IDTemplateProcessor:
    """Process ID templates and add photos"""
    
    def __init__(self, templates_dir: str = "templates"):
        self.templates_dir = Path(templates_dir)
        self.output_dir = Path("generated_documents")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"ID Template Processor initialized: {self.templates_dir}")
    
    def process_texas_id_with_photo(self, 
                                   photo_path: str,
                                   template_name: str = "texas_dl_psd",
                                   user_data: Dict = None) -> Optional[str]:
        """
        Process Texas ID template and add photo
        
        Args:
            photo_path: Path to user photo
            template_name: Name of template to use
            user_data: Dictionary with user data (name, DOB, address, etc.)
        
        Returns:
            Path to generated ID image or None if failed
        """
        if not PILLOW_AVAILABLE:
            logger.error("Pillow not available for ID processing")
            return None
        
        try:
            # Load template - checks database first, then local files
            template_path = self._find_template(template_name)
            if not template_path:
                logger.warning(f"Template not found: {template_name}, trying alternative names")
                # Try alternative template names
                for alt_name in ['texas_dl', 'texas_id', 'texas_driver_license', 'texas_dl_psd']:
                    template_path = self._find_template(alt_name)
                    if template_path:
                        logger.info(f"Found template with alternative name: {alt_name}")
                        break
                
                if not template_path:
                    logger.error(f"No Texas template found in database or local files")
                    return None
            
            # Load photo
            if not Path(photo_path).exists():
                logger.error(f"Photo not found: {photo_path}")
                return None
            
            user_photo = Image.open(photo_path)
            
            # Process template
            if template_path.suffix.lower() == '.psd':
                id_image = self._process_psd_template(template_path, user_photo, user_data)
            else:
                id_image = self._process_image_template(template_path, user_photo, user_data)
            
            if not id_image:
                return None
            
            # Save generated ID
            output_filename = f"texas_id_{Path(photo_path).stem}_{int(time.time())}.png"
            output_path = self.output_dir / output_filename
            id_image.save(str(output_path), 'PNG', quality=95)
            
            logger.info(f"Texas ID generated: {output_path} (size: {output_path.stat().st_size} bytes)")
            
            # Verify file was actually created
            if not output_path.exists() or output_path.stat().st_size == 0:
                logger.error(f"Generated ID file is empty or doesn't exist: {output_path}")
                return None
            
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Error processing Texas ID: {e}", exc_info=True)
            return None
    
    def _find_template(self, template_name: str) -> Optional[Path]:
        """Find template file - checks database first, then local files"""
        # FIRST: Check database for template
        try:
            from template_manager import get_template_manager
            from database_hybrid import Database
            
            db = Database()
            tm = get_template_manager(db)
            
            # Search for template in database
            template = None
            
            # Try exact name match first
            template = tm.get_template(name=template_name)
            
            # If not found, search for Texas/ID templates
            if not template:
                all_templates = tm.list_templates()
                for t in all_templates:
                    if isinstance(t, dict):
                        name = t.get('name', '').lower()
                        if 'texas' in name or 'tx' in name or 'id' in name or 'driver' in name:
                            template = t
                            break
            
            # If template found in database, use its file_path
            if template and isinstance(template, dict):
                file_path = template.get('file_path')
                if file_path and Path(file_path).exists():
                    logger.info(f"Found template in database: {file_path}")
                    return Path(file_path)
                # Also check template_data for file_path
                template_data = template.get('template_data', {})
                if isinstance(template_data, dict):
                    file_path = template_data.get('file_path')
                    if file_path and Path(file_path).exists():
                        logger.info(f"Found template file_path in template_data: {file_path}")
                        return Path(file_path)
        except Exception as e:
            logger.warning(f"Could not check database for template: {e}")
        
        # FALLBACK: Check local files
        # Check processed templates first
        processed_dir = self.templates_dir / "processed"
        metadata_path = processed_dir / f"{template_name}_metadata.json"
        
        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
                file_path = metadata.get('file_path')
                if file_path and Path(file_path).exists():
                    return Path(file_path)
        
        # Check PSD directory
        psd_dir = self.templates_dir / "psd"
        psd_path = psd_dir / f"{template_name}.psd"
        if psd_path.exists():
            return psd_path
        
        # Check templates directory
        template_path = self.templates_dir / f"{template_name}.psd"
        if template_path.exists():
            return template_path
        
        # Try with different extensions
        for ext in ['.psd', '.png', '.jpg', '.jpeg']:
            template_path = self.templates_dir / f"{template_name}{ext}"
            if template_path.exists():
                return template_path
        
        return None
    
    def _process_psd_template(self, 
                            psd_path: Path, 
                            user_photo: Image.Image,
                            user_data: Dict = None) -> Optional[Image.Image]:
        """
        Process PSD template with advanced layer manipulation
        - Reads individual layers
        - Finds photo layer position from metadata
        - Edits text layers directly
        - Maintains layer effects and blending
        """
        try:
            if not PSD_TOOLS_AVAILABLE:
                logger.error("psd-tools not available for PSD processing")
                return None
            
            # Load PSD
            psd = PSDImage.open(str(psd_path))
            
            # Extract layer information for better positioning
            layer_info = self._extract_layer_positions(psd)
            
            # Start with base composite (background layers)
            composite = psd.composite()
            
            # Convert to PIL Image if needed
            if not isinstance(composite, Image.Image):
                if NUMPY_AVAILABLE:
                    # Convert numpy array to PIL Image
                    if composite.dtype != np.uint8:
                        composite = (composite * 255).astype(np.uint8)
                    if len(composite.shape) == 3:
                        composite = Image.fromarray(composite, 'RGB')
                    else:
                        composite = Image.fromarray(composite, 'L')
                else:
                    composite = Image.fromarray(composite)
            
            # Ensure RGBA mode for transparency
            if composite.mode != 'RGBA':
                composite = composite.convert('RGBA')
            
            # Process photo to match ID specifications
            processed_photo = self._process_id_photo(user_photo, target_size=(300, 300))
            
            # Find photo layer position from PSD metadata
            photo_position = self._find_photo_position_advanced(psd, layer_info, composite.size)
            
            # Paste photo with proper blending
            if photo_position:
                x, y, width, height = photo_position
                # Resize photo to match layer size if specified
                if width and height:
                    processed_photo = processed_photo.resize((width, height), Image.Resampling.LANCZOS)
                
                # Create mask for smooth edges
                mask = self._create_photo_mask(processed_photo)
                
                # Paste with alpha blending
                composite.paste(processed_photo, (x, y), mask)
            
            # Edit text layers directly if user_data provided
            if user_data:
                composite = self._edit_text_layers_advanced(composite, psd, layer_info, user_data)
            
            return composite
            
        except Exception as e:
            logger.error(f"Error processing PSD template: {e}", exc_info=True)
            return None
    
    def _extract_layer_positions(self, psd: PSDImage) -> Dict:
        """Extract layer positions and metadata from PSD"""
        layer_info = {
            'photo_layers': [],
            'text_layers': [],
            'all_layers': []
        }
        
        def traverse_layers(layer, parent_offset=(0, 0)):
            """Recursively traverse layers"""
            if hasattr(layer, 'bbox'):
                bbox = layer.bbox
                x, y = bbox.x1 + parent_offset[0], bbox.y1 + parent_offset[1]
                width = bbox.x2 - bbox.x1
                height = bbox.y2 - bbox.y1
                
                layer_data = {
                    'name': layer.name.lower() if hasattr(layer, 'name') else '',
                    'type': type(layer).__name__,
                    'x': x,
                    'y': y,
                    'width': width,
                    'height': height,
                    'bbox': (x, y, width, height)
                }
                
                layer_info['all_layers'].append(layer_data)
                
                # Identify photo layers (common names)
                photo_keywords = ['photo', 'picture', 'image', 'portrait', 'face', 'headshot']
                if any(keyword in layer_data['name'] for keyword in photo_keywords):
                    layer_info['photo_layers'].append(layer_data)
                
                # Identify text layers
                if isinstance(layer, TypeLayer):
                    layer_info['text_layers'].append(layer_data)
        
        # Traverse all layers
        for layer in psd:
            traverse_layers(layer)
        
        return layer_info
    
    def _find_photo_position_advanced(self, psd: PSDImage, layer_info: Dict, template_size: Tuple[int, int]) -> Optional[Tuple[int, int, int, int]]:
        """Find photo layer position from PSD metadata"""
        # Try to find photo layer from metadata
        if layer_info['photo_layers']:
            photo_layer = layer_info['photo_layers'][0]  # Use first photo layer
            return (photo_layer['x'], photo_layer['y'], photo_layer['width'], photo_layer['height'])
        
        # Fallback: search for layers with photo-like names
        for layer in psd:
            if hasattr(layer, 'name'):
                name_lower = layer.name.lower()
                if any(keyword in name_lower for keyword in ['photo', 'picture', 'image', 'portrait']):
                    if hasattr(layer, 'bbox'):
                        bbox = layer.bbox
                        return (bbox.x1, bbox.y1, bbox.x2 - bbox.x1, bbox.y2 - bbox.y1)
        
        # Default position (typical ID photo location: top-right)
        return (template_size[0] - 350, 50, 300, 300)
    
    def _create_photo_mask(self, photo: Image.Image) -> Image.Image:
        """Create smooth mask for photo edges"""
        if photo.mode != 'RGBA':
            photo = photo.convert('RGBA')
        
        # Create mask with feathered edges
        mask = Image.new('L', photo.size, 255)
        
        # Apply slight blur for smooth edges
        try:
            mask = mask.filter(ImageFilter.GaussianBlur(radius=1))
        except:
            pass
        
        return mask
    
    def _edit_text_layers_advanced(self, 
                                  composite: Image.Image,
                                  psd: PSDImage,
                                  layer_info: Dict,
                                  user_data: Dict) -> Image.Image:
        """Edit text layers with proper positioning and fonts"""
        draw = ImageDraw.Draw(composite)
        
        # Map user data to text fields
        text_mapping = {
            'name': user_data.get('name', ''),
            'dob': user_data.get('dob', ''),
            'address': user_data.get('address', ''),
            'city': user_data.get('city', ''),
            'state': user_data.get('state', ''),
            'zip': user_data.get('zip', ''),
            'license_number': user_data.get('license_number', ''),
            'expiry': user_data.get('expiry', ''),
            'height': user_data.get('height', ''),
            'weight': user_data.get('weight', ''),
            'eyes': user_data.get('eyes', ''),
            'hair': user_data.get('hair', '')
        }
        
        # Edit text layers from PSD
        for text_layer_info in layer_info['text_layers']:
            layer_name = text_layer_info['name']
            
            # Find matching text field
            text_value = None
            for key, value in text_mapping.items():
                if key in layer_name or layer_name in key:
                    text_value = str(value)
                    break
            
            if text_value:
                # Get font (try to match PSD font size)
                font_size = min(text_layer_info['height'], 24)
                try:
                    font = ImageFont.truetype("arial.ttf", font_size)
                except:
                    font = ImageFont.load_default()
                
                # Draw text at layer position
                x = text_layer_info['x']
                y = text_layer_info['y']
                
                # Use white text (typical for IDs)
                draw.text((x, y), text_value, fill=(255, 255, 255), font=font)
        
        return composite
    
    def _process_image_template(self,
                               template_path: Path,
                               user_photo: Image.Image,
                               user_data: Dict = None) -> Optional[Image.Image]:
        """Process image template and add photo"""
        try:
            # Load template
            template = Image.open(str(template_path))
            
            # Process photo
            processed_photo = self._process_id_photo(user_photo, target_size=(300, 300))
            
            # Default photo position (top-right area)
            photo_x = template.width - 350
            photo_y = 50
            
            # Paste photo
            template.paste(processed_photo, (photo_x, photo_y), processed_photo if processed_photo.mode == 'RGBA' else None)
            
            # Add text data if provided
            if user_data:
                template = self._add_text_data(template, user_data)
            
            return template
            
        except Exception as e:
            logger.error(f"Error processing image template: {e}", exc_info=True)
            return None
    
    def _process_id_photo(self, photo: Image.Image, target_size: Tuple[int, int] = (300, 300)) -> Image.Image:
        """Process photo to match ID specifications"""
        try:
            # Convert to RGB if needed
            if photo.mode != 'RGB':
                photo = photo.convert('RGB')
            
            # Resize maintaining aspect ratio
            photo.thumbnail(target_size, Image.Resampling.LANCZOS)
            
            # Create new image with exact size (white background)
            processed = Image.new('RGB', target_size, (255, 255, 255))
            
            # Center photo
            x_offset = (target_size[0] - photo.width) // 2
            y_offset = (target_size[1] - photo.height) // 2
            processed.paste(photo, (x_offset, y_offset))
            
            # Enhance contrast slightly
            enhancer = ImageEnhance.Contrast(processed)
            processed = enhancer.enhance(1.1)
            
            # Slight sharpening
            processed = processed.filter(ImageFilter.SHARPEN)
            
            return processed
            
        except Exception as e:
            logger.error(f"Error processing ID photo: {e}")
            return photo
    
    def _find_photo_position(self, psd: PSDImage, template_size: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """Find photo layer position in PSD"""
        try:
            # Try to find photo layer by name
            for layer in psd:
                if hasattr(layer, 'name'):
                    layer_name = layer.name.lower()
                    if 'photo' in layer_name or 'picture' in layer_name or 'image' in layer_name:
                        if hasattr(layer, 'bbox'):
                            bbox = layer.bbox
                            return (bbox.x1, bbox.y1)
            
            # Default position (typical ID photo location)
            # Top-right area for most IDs
            return (template_size[0] - 350, 50)
            
        except Exception as e:
            logger.warning(f"Could not find photo position: {e}")
            return None
    
    def _add_text_data(self, image: Image.Image, user_data: Dict, psd: PSDImage = None) -> Image.Image:
        """Add text data to ID image"""
        try:
            draw = ImageDraw.Draw(image)
            
            # Try to load font
            try:
                font_large = ImageFont.truetype("arial.ttf", 24)
                font_small = ImageFont.truetype("arial.ttf", 18)
            except:
                try:
                    font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
                    font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
                except:
                    font_large = ImageFont.load_default()
                    font_small = ImageFont.load_default()
            
            # Default text positions (adjust based on template)
            text_positions = {
                'name': (50, 200),
                'dob': (50, 240),
                'address': (50, 280),
                'license_number': (50, 320),
            }
            
            # Add text fields
            y_offset = 200
            for key, value in user_data.items():
                if key.lower() in ['name', 'full_name']:
                    draw.text((50, y_offset), str(value), fill=(0, 0, 0), font=font_large)
                    y_offset += 40
                elif key.lower() in ['dob', 'date_of_birth', 'birth_date']:
                    draw.text((50, y_offset), f"DOB: {value}", fill=(0, 0, 0), font=font_small)
                    y_offset += 30
                elif key.lower() in ['address']:
                    draw.text((50, y_offset), str(value), fill=(0, 0, 0), font=font_small)
                    y_offset += 30
                elif key.lower() in ['license', 'license_number', 'dl_number']:
                    draw.text((50, y_offset), f"DL: {value}", fill=(0, 0, 0), font=font_small)
                    y_offset += 30
            
            return image
            
        except Exception as e:
            logger.error(f"Error adding text data: {e}")
            return image


# Global instance
_id_processor_instance = None

def get_id_processor(templates_dir: str = "templates") -> IDTemplateProcessor:
    """Get or create global ID processor instance"""
    global _id_processor_instance
    if _id_processor_instance is None:
        _id_processor_instance = IDTemplateProcessor(templates_dir)
    return _id_processor_instance
