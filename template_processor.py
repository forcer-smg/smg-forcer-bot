# -*- coding: utf-8 -*-
"""
Template Processor - Extract and prepare templates for AI document generation
Handles PSD files, extracts layers, and makes templates AI-friendly
"""

import os
import logging
import json
from typing import Dict, List, Optional, Any
from pathlib import Path
import shutil

logger = logging.getLogger(__name__)

try:
    from psd_tools import PSDImage
    PSD_TOOLS_AVAILABLE = True
except ImportError:
    PSD_TOOLS_AVAILABLE = False
    logger.warning("psd-tools not available. PSD processing will be limited.")

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    logger.warning("Pillow not available. Image processing will be limited.")


class TemplateProcessor:
    """Process templates for AI document generation"""
    
    def __init__(self, templates_dir: str = "templates"):
        self.templates_dir = Path(templates_dir)
        self.processed_dir = self.templates_dir / "processed"
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        
        self.psd_dir = self.templates_dir / "psd"
        self.psd_dir.mkdir(exist_ok=True)
        
        logger.info(f"Template Processor initialized: {self.templates_dir}")
    
    def extract_psd_layers(self, psd_path: str) -> Optional[Dict]:
        """
        Extract layer information from PSD file
        
        Args:
            psd_path: Path to PSD file
        
        Returns:
            Dictionary with layer information and preview images
        """
        if not PSD_TOOLS_AVAILABLE:
            logger.error("psd-tools not available for PSD processing")
            return None
        
        try:
            psd_file = Path(psd_path)
            if not psd_file.exists():
                logger.error(f"PSD file not found: {psd_path}")
                return None
            
            # Load PSD
            psd = PSDImage.open(psd_path)
            
            # Extract layer information
            layers_info = []
            self._extract_layers_recursive(psd, layers_info, "")
            
            # Generate preview image (composite)
            preview_path = self.processed_dir / f"{psd_file.stem}_preview.png"
            if PILLOW_AVAILABLE:
                composite = psd.composite()
                composite.save(str(preview_path))
            
            # Extract text layers
            text_layers = []
            for layer_info in layers_info:
                if layer_info.get('type') == 'text':
                    text_layers.append(layer_info)
            
            # Create template metadata
            template_data = {
                'name': psd_file.stem,
                'file_path': str(psd_path),
                'preview_path': str(preview_path) if preview_path.exists() else None,
                'width': psd.width,
                'height': psd.height,
                'layers': layers_info,
                'text_layers': text_layers,
                'layer_count': len(layers_info),
                'text_layer_count': len(text_layers)
            }
            
            # Save metadata
            metadata_path = self.processed_dir / f"{psd_file.stem}_metadata.json"
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(template_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Extracted {len(layers_info)} layers from PSD: {psd_path}")
            return template_data
            
        except Exception as e:
            logger.error(f"Error extracting PSD layers: {e}", exc_info=True)
            return None
    
    def _extract_layers_recursive(self, layer, layers_info: List, prefix: str = ""):
        """Recursively extract layer information"""
        try:
            layer_name = prefix + (layer.name if hasattr(layer, 'name') else 'Layer')
            
            layer_info = {
                'name': layer_name,
                'visible': layer.visible if hasattr(layer, 'visible') else True,
                'opacity': layer.opacity if hasattr(layer, 'opacity') else 255,
                'type': 'group' if hasattr(layer, 'layers') else 'layer'
            }
            
            # Check if it's a text layer
            if hasattr(layer, 'text') and layer.text:
                layer_info['type'] = 'text'
                layer_info['text'] = layer.text
                layer_info['font'] = getattr(layer, 'font', None)
                layer_info['size'] = getattr(layer, 'size', None)
            
            # Get layer bounds
            if hasattr(layer, 'bbox'):
                bbox = layer.bbox
                layer_info['bounds'] = {
                    'x': bbox.x1,
                    'y': bbox.y1,
                    'width': bbox.width,
                    'height': bbox.height
                }
            
            layers_info.append(layer_info)
            
            # Process child layers (for groups)
            if hasattr(layer, 'layers'):
                for child in layer.layers:
                    self._extract_layers_recursive(child, layers_info, f"{layer_name}/")
                    
        except Exception as e:
            logger.warning(f"Error extracting layer: {e}")
    
    def process_template(self, template_path: str, template_name: str = None) -> Optional[Dict]:
        """
        Process a template file (PSD, PDF, etc.) and make it AI-ready
        
        Args:
            template_path: Path to template file
            template_name: Name for the template
        
        Returns:
            Processed template metadata
        """
        template_file = Path(template_path)
        if not template_file.exists():
            logger.error(f"Template file not found: {template_path}")
            return None
        
        if not template_name:
            template_name = template_file.stem
        
        file_ext = template_file.suffix.lower()
        
        if file_ext == '.psd':
            return self.extract_psd_layers(template_path)
        elif file_ext in ['.pdf', '.docx', '.xlsx']:
            # For other formats, create basic metadata
            return {
                'name': template_name,
                'file_path': str(template_path),
                'type': file_ext[1:],  # Remove dot
                'processed': True
            }
        else:
            logger.warning(f"Unsupported template format: {file_ext}")
            return None
    
    def get_template_info(self, template_name: str) -> Optional[Dict]:
        """
        Get processed template information
        
        Args:
            template_name: Name of the template
        
        Returns:
            Template metadata dictionary
        """
        # Check processed templates
        metadata_path = self.processed_dir / f"{template_name}_metadata.json"
        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # Check if PSD exists
        psd_path = self.psd_dir / f"{template_name}.psd"
        if psd_path.exists():
            return self.process_template(str(psd_path), template_name)
        
        return None
    
    def list_processed_templates(self) -> List[Dict]:
        """List all processed templates"""
        templates = []
        
        # Check processed metadata files
        for metadata_file in self.processed_dir.glob("*_metadata.json"):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    template_data = json.load(f)
                    templates.append(template_data)
            except Exception as e:
                logger.warning(f"Error reading metadata: {metadata_file}: {e}")
        
        return templates
    
    def prepare_template_for_ai(self, template_name: str) -> Optional[str]:
        """
        Prepare template information in a format easy for AI to understand
        
        Args:
            template_name: Name of the template
        
        Returns:
            Formatted string describing the template for AI
        """
        template_info = self.get_template_info(template_name)
        if not template_info:
            return None
        
        # Format for AI consumption
        ai_description = f"Template: {template_info.get('name', template_name)}\n"
        ai_description += f"Type: {template_info.get('type', 'unknown')}\n"
        
        if 'width' in template_info and 'height' in template_info:
            ai_description += f"Dimensions: {template_info['width']}x{template_info['height']} pixels\n"
        
        if 'layers' in template_info:
            ai_description += f"Total Layers: {template_info.get('layer_count', 0)}\n"
            
            # List text layers (editable fields)
            text_layers = template_info.get('text_layers', [])
            if text_layers:
                ai_description += f"\nEditable Text Fields ({len(text_layers)}):\n"
                for i, text_layer in enumerate(text_layers, 1):
                    layer_name = text_layer.get('name', 'Unknown')
                    current_text = text_layer.get('text', '')
                    bounds = text_layer.get('bounds', {})
                    
                    ai_description += f"  {i}. {layer_name}\n"
                    if current_text:
                        ai_description += f"     Current text: \"{current_text}\"\n"
                    if bounds:
                        ai_description += f"     Position: ({bounds.get('x', 0)}, {bounds.get('y', 0)}), Size: {bounds.get('width', 0)}x{bounds.get('height', 0)}\n"
        
        if 'file_path' in template_info:
            ai_description += f"\nFile Path: {template_info['file_path']}\n"
        
        return ai_description


# Global instance
_template_processor_instance = None

def get_template_processor(templates_dir: str = "templates") -> TemplateProcessor:
    """Get or create global template processor instance"""
    global _template_processor_instance
    if _template_processor_instance is None:
        _template_processor_instance = TemplateProcessor(templates_dir)
    return _template_processor_instance
