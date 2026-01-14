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

# MEGA.nz support
try:
    from mega import Mega
    MEGA_AVAILABLE = True
except ImportError:
    MEGA_AVAILABLE = False
    logger.warning("mega.py not available. MEGA.nz downloads will be limited.")


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
            # Extract file key from MediaFire URL
            # MediaFire URLs: https://www.mediafire.com/file/[file_key]/[filename]/file
            import re
            match = re.search(r'/file/([^/]+)/', url)
            if not match:
                logger.error(f"Invalid MediaFire URL: {url}")
                return None
            
            file_key = match.group(1)
            
            # MediaFire direct download - use the download page
            # MediaFire redirects to a download page, then to the actual file
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
            # Get the download page
            download_page_url = f"https://www.mediafire.com/file/{file_key}/"
            response = session.get(download_page_url, allow_redirects=True, timeout=30)
            response.raise_for_status()
            
            # Try multiple methods to get download URL
            download_url = None
            
            # Method 1: Look for direct download link in page
            download_patterns = [
                r'href="(https://download[^"]+)"',
                r'kNOk3" href="([^"]+)"',
                r'downloadUrl["\']?\s*:\s*["\']([^"\']+)["\']',
                r'data-downloadurl=["\']([^"\']+)["\']',
            ]
            
            for pattern in download_patterns:
                match = re.search(pattern, response.text)
                if match:
                    download_url = match.group(1)
                    if not download_url.startswith('http'):
                        download_url = 'https://www.mediafire.com' + download_url
                    break
            
            # Method 2: Try MediaFire API (may require API key, but worth trying)
            if not download_url:
                try:
                    api_url = f"https://www.mediafire.com/api/1.4/file/get_info.php?quick_key={file_key}&response_format=json"
                    api_response = session.get(api_url, timeout=30)
                    if api_response.status_code == 200:
                        data = api_response.json()
                        if data.get('response', {}).get('file_infos'):
                            download_url = data['response']['file_infos'][0].get('download_url')
                except:
                    pass
            
            # Method 3: Construct direct download URL (MediaFire pattern)
            if not download_url:
                # Try direct download pattern
                download_url = f"https://download{file_key[:2]}.mediafire.com/{file_key}/file"
            
            if not download_url:
                logger.error("Could not determine download URL from MediaFire")
                return None
            
            # Download file
            logger.info(f"Downloading template from MediaFire: {download_url}")
            file_response = session.get(download_url, stream=True, timeout=300, allow_redirects=True)
            file_response.raise_for_status()
            
            # Determine filename
            if not template_name:
                # Try to get filename from Content-Disposition header
                content_disposition = file_response.headers.get('Content-Disposition', '')
                if 'filename=' in content_disposition:
                    template_name = content_disposition.split('filename=')[1].strip('"\'')
                else:
                    # Extract from URL
                    template_name = url.split('/')[-2] if '/' in url else f"template_{file_key}"
                    # Clean filename
                    template_name = "".join(c for c in template_name if c.isalnum() or c in (' ', '-', '_', '.')).strip()
            
            # Determine file type and save location
            file_ext = Path(template_name).suffix.lower()
            if file_ext == '.psd':
                save_path = self.psd_dir / template_name
            elif file_ext in ['.rar', '.zip']:
                save_path = self.templates_dir / template_name
            else:
                save_path = self.templates_dir / template_name
            
            # Download and save
            total_size = 0
            with open(save_path, 'wb') as f:
                for chunk in file_response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_size += len(chunk)
            
            logger.info(f"Template downloaded: {save_path} ({total_size / 1024 / 1024:.2f} MB)")
            
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
    
    def download_from_mega(self, url: str, template_name: str = None) -> Optional[str]:
        """
        Download file from MEGA.nz
        
        Args:
            url: MEGA.nz file or folder URL
            template_name: Name for the template (auto-extracted if None)
        
        Returns:
            Path to downloaded file or None if failed
        """
        if not MEGA_AVAILABLE:
            logger.error("mega.py not available for MEGA.nz downloads. Install with: pip install mega.py")
            return None
        
        try:
            # Initialize MEGA client (anonymous download)
            mega = Mega()
            
            # Extract file key from URL
            # MEGA URLs: https://mega.nz/file/[file_key]#[decryption_key]
            # Or: https://mega.nz/folder/[folder_key]#[decryption_key]
            import re
            
            # Check if it's a folder
            folder_match = re.search(r'/folder/([^#]+)#([^#]+)', url)
            file_match = re.search(r'/file/([^#]+)#([^#]+)', url)
            
            if folder_match:
                # Download entire folder
                folder_key = folder_match.group(1)
                logger.info(f"Downloading MEGA folder: {folder_key}")
                
                try:
                    # Get folder from URL
                    folder = mega.get_folder_from_url(url)
                    
                    # Download all files in folder
                    downloaded_files = []
                    files = folder.get_files()
                    
                    for file_node in files:
                        try:
                            # Download file
                            file_path = mega.download_url(url, dest_path=str(self.templates_dir))
                            if file_path and Path(file_path).exists():
                                downloaded_files.append(file_path)
                        except Exception as e:
                            logger.warning(f"Error downloading file from folder: {e}")
                            continue
                    
                    if downloaded_files:
                        logger.info(f"Downloaded {len(downloaded_files)} files from MEGA folder")
                        return downloaded_files[0]  # Return first file
                    else:
                        logger.error("No files downloaded from MEGA folder")
                        return None
                except Exception as e:
                    logger.error(f"Error accessing MEGA folder: {e}")
                    return None
                    
            elif file_match:
                # Download single file
                file_key = file_match.group(1)
                logger.info(f"Downloading MEGA file: {file_key}")
                
                try:
                    # Download file
                    if not template_name:
                        # Try to get filename from MEGA
                        try:
                            file_info = mega.get_public_file_info(url)
                            if isinstance(file_info, dict):
                                template_name = file_info.get('name', f"mega_file_{file_key[:8]}")
                            else:
                                template_name = f"mega_file_{file_key[:8]}"
                        except:
                            template_name = f"mega_file_{file_key[:8]}"
                    
                    # Determine save location
                    file_ext = Path(template_name).suffix.lower()
                    if file_ext == '.psd':
                        save_dir = self.psd_dir
                    elif file_ext in ['.rar', '.zip']:
                        save_dir = self.templates_dir
                    else:
                        save_dir = self.templates_dir
                    
                    # Download file
                    downloaded_path = mega.download_url(url, dest_path=str(save_dir))
                    
                    if downloaded_path and Path(downloaded_path).exists():
                        logger.info(f"MEGA file downloaded: {downloaded_path}")
                        return str(downloaded_path)
                    else:
                        # File might have different name, search for recently created files
                        import time
                        recent_time = time.time() - 60  # Last minute
                        for file in save_dir.iterdir():
                            if file.stat().st_mtime > recent_time:
                                logger.info(f"Found recently downloaded file: {file}")
                                return str(file)
                        
                        logger.error("MEGA file download completed but file not found")
                        return None
                except Exception as e:
                    logger.error(f"Error downloading MEGA file: {e}", exc_info=True)
                    return None
            else:
                logger.error(f"Invalid MEGA.nz URL format: {url}")
                return None
                
        except Exception as e:
            logger.error(f"Error downloading from MEGA.nz: {e}", exc_info=True)
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
