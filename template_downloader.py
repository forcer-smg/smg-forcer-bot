# -*- coding: utf-8 -*-
"""
Template Downloader - Download and manage template files from external sources
Supports MediaFire, direct URLs, and local file uploads
"""

import os
import logging
import requests
from typing import Dict, Optional
from pathlib import Path
import zipfile
import rarfile
import shutil

logger = logging.getLogger(__name__)

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    logger.warning("Pillow not available. PSD template processing will be limited.")


class TemplateDownloader:
    """Download and process template files"""
    
    def __init__(self, templates_dir: str = "templates"):
        self.templates_dir = Path(templates_dir)
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        
        # Subdirectories
        self.psd_dir = self.templates_dir / "psd"
        self.psd_dir.mkdir(exist_ok=True)
        
        logger.info(f"Template Downloader initialized: {self.templates_dir}")
    
    def download_from_mediafire(self, url: str, template_name: str = None) -> Optional[str]:
        """
        Download file from MediaFire
        
        Args:
            url: MediaFire download URL
            template_name: Name for the template (auto-extracted if None)
        
        Returns:
            Path to downloaded file or None if failed
        """
        try:
            # Extract file ID from MediaFire URL
            # MediaFire URLs: https://www.mediafire.com/file/[file_id]/[filename]/file
            import re
            match = re.search(r'/file/([^/]+)/', url)
            if not match:
                logger.error(f"Invalid MediaFire URL: {url}")
                return None
            
            file_id = match.group(1)
            
            # MediaFire direct download API
            # First, get the download page
            session = requests.Session()
            response = session.get(url, allow_redirects=True, timeout=30)
            response.raise_for_status()
            
            # Try to find direct download link
            # MediaFire uses JavaScript to generate download links, so we need to parse the page
            import re
            download_link_match = re.search(r'href="(https://download[^"]+)"', response.text)
            if download_link_match:
                download_url = download_link_match.group(1)
            else:
                # Alternative: try MediaFire API
                api_url = f"https://www.mediafire.com/api/1.4/file/get_info.php?quick_key={file_id}&response_format=json"
                api_response = session.get(api_url, timeout=30)
                if api_response.status_code == 200:
                    data = api_response.json()
                    if data.get('response', {}).get('file_infos'):
                        download_url = data['response']['file_infos'][0].get('download_url')
                    else:
                        logger.error("Could not get download URL from MediaFire API")
                        return None
                else:
                    logger.error(f"MediaFire API returned {api_response.status_code}")
                    return None
            
            # Download file
            logger.info(f"Downloading template from MediaFire: {download_url}")
            file_response = session.get(download_url, stream=True, timeout=300)
            file_response.raise_for_status()
            
            # Determine filename
            if not template_name:
                # Try to get filename from Content-Disposition header
                content_disposition = file_response.headers.get('Content-Disposition', '')
                if 'filename=' in content_disposition:
                    template_name = content_disposition.split('filename=')[1].strip('"\'')
                else:
                    # Extract from URL
                    template_name = url.split('/')[-1] or f"template_{file_id}"
            
            # Determine file type and save location
            file_ext = Path(template_name).suffix.lower()
            if file_ext == '.psd':
                save_path = self.psd_dir / template_name
            elif file_ext in ['.rar', '.zip']:
                save_path = self.templates_dir / template_name
            else:
                save_path = self.templates_dir / template_name
            
            # Download and save
            with open(save_path, 'wb') as f:
                for chunk in file_response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Template downloaded: {save_path}")
            
            # Extract if archive
            if file_ext in ['.rar', '.zip']:
                extracted_path = self._extract_archive(save_path)
                if extracted_path:
                    return extracted_path
            
            return str(save_path)
            
        except Exception as e:
            logger.error(f"Error downloading from MediaFire: {e}", exc_info=True)
            return None
    
    def _extract_archive(self, archive_path: Path) -> Optional[str]:
        """Extract RAR or ZIP archive"""
        try:
            extract_dir = archive_path.parent / archive_path.stem
            extract_dir.mkdir(exist_ok=True)
            
            if archive_path.suffix.lower() == '.rar':
                try:
                    import rarfile
                    with rarfile.RarFile(archive_path) as rf:
                        rf.extractall(extract_dir)
                except ImportError:
                    logger.error("rarfile not available. Install with: pip install rarfile")
                    return None
            elif archive_path.suffix.lower() == '.zip':
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    zf.extractall(extract_dir)
            
            # Find PSD files in extracted directory
            psd_files = list(extract_dir.rglob('*.psd'))
            if psd_files:
                # Move first PSD to psd directory
                psd_file = psd_files[0]
                target_path = self.psd_dir / psd_file.name
                shutil.move(str(psd_file), str(target_path))
                logger.info(f"Extracted PSD template: {target_path}")
                return str(target_path)
            
            logger.warning(f"No PSD files found in archive: {archive_path}")
            return str(extract_dir)
            
        except Exception as e:
            logger.error(f"Error extracting archive: {e}", exc_info=True)
            return None
    
    def save_template_file(self, file_path: str, template_name: str, template_type: str = "psd") -> Optional[str]:
        """
        Save a template file to the templates directory
        
        Args:
            file_path: Path to source file
            template_name: Name for the template
            template_type: Type of template (psd, pdf, etc.)
        
        Returns:
            Path to saved template file
        """
        try:
            source_path = Path(file_path)
            if not source_path.exists():
                logger.error(f"Source file not found: {file_path}")
                return None
            
            # Determine destination directory
            if template_type.lower() == 'psd':
                dest_dir = self.psd_dir
            else:
                dest_dir = self.templates_dir / template_type
            
            dest_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy file
            dest_path = dest_dir / template_name
            shutil.copy2(source_path, dest_path)
            
            logger.info(f"Template file saved: {dest_path}")
            return str(dest_path)
            
        except Exception as e:
            logger.error(f"Error saving template file: {e}", exc_info=True)
            return None
    
    def list_templates(self, template_type: str = None) -> Dict[str, list]:
        """List available template files"""
        templates = {}
        
        if template_type:
            template_type = template_type.lower()
            if template_type == 'psd':
                templates['psd'] = [str(f) for f in self.psd_dir.glob('*.psd')]
            else:
                type_dir = self.templates_dir / template_type
                if type_dir.exists():
                    templates[template_type] = [str(f) for f in type_dir.glob('*')]
        else:
            # List all types
            templates['psd'] = [str(f) for f in self.psd_dir.glob('*.psd')]
            for subdir in self.templates_dir.iterdir():
                if subdir.is_dir() and subdir.name != 'psd':
                    templates[subdir.name] = [str(f) for f in subdir.glob('*')]
        
        return templates


# Global instance
_template_downloader_instance = None

def get_template_downloader(templates_dir: str = "templates") -> TemplateDownloader:
    """Get or create global template downloader instance"""
    global _template_downloader_instance
    if _template_downloader_instance is None:
        _template_downloader_instance = TemplateDownloader(templates_dir)
    return _template_downloader_instance
