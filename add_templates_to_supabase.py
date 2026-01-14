# -*- coding: utf-8 -*-
"""
Add Pre-configured Templates to Supabase Database
Adds templates from MEGA.nz, MediaFire, and other sources
"""

import os
import sys
import logging
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()

# Import database and template manager
try:
    from database_hybrid import Database
    from template_manager import get_template_manager
    from template_downloader import get_template_downloader
except ImportError as e:
    logger.error(f"Import error: {e}")
    sys.exit(1)


def add_templates_to_database():
    """Add pre-configured templates to Supabase database"""
    
    try:
        # Initialize database and managers
        db = Database()
        template_mgr = get_template_manager(db)
        downloader = get_template_downloader()
        
        # Template URLs to add
        templates = [
            {
                'name': 'texas_dl_psd',
                'url': 'https://www.mediafire.com/file/njzbeit60kmwxkb/texas+dl+psd.rar/file',
                'type': 'psd',
                'category': 'id_document',
                'description': 'Texas Driver License PSD Template',
                'source': 'mediafire'
            },
            {
                'name': 'mega_template_1',
                'url': 'https://mega.nz/file/uWBmUZgA#iUzerkrfdROQQ53XQq0-Mc9ItCvrNYndz1be9kvo4xM',
                'type': 'psd',
                'category': 'document',
                'description': 'MEGA Template 1',
                'source': 'mega'
            },
            {
                'name': 'mega_template_2',
                'url': 'https://mega.nz/file/uaBjWIKa#UZa-_JwuaXxy3zq1zzS4lgZXULJT8AqOBtsKaT1vE-4',
                'type': 'psd',
                'category': 'document',
                'description': 'MEGA Template 2',
                'source': 'mega'
            },
            {
                'name': 'mega_template_3',
                'url': 'https://mega.nz/file/3O43SZ6D#7XuMUtMwpEsi98TdEWSvMR2qLK5V1J1sPBqWaseLNj8',
                'type': 'psd',
                'category': 'document',
                'description': 'MEGA Template 3',
                'source': 'mega'
            },
            {
                'name': 'mega_template_folder',
                'url': 'https://mega.nz/folder/zyQlWLJC#4oYgrOgGPt6b1i3KsbKJ8Q',
                'type': 'psd',
                'category': 'document',
                'description': 'MEGA Template Folder',
                'source': 'mega'
            },
        ]
        
        logger.info(f"Adding {len(templates)} templates to database...")
        
        added_count = 0
        skipped_count = 0
        
        for template_info in templates:
            try:
                name = template_info['name']
                url = template_info['url']
                template_type = template_info['type']
                category = template_info.get('category', 'document')
                description = template_info.get('description', '')
                source = template_info.get('source', 'unknown')
                
                # Check if template already exists
                existing = template_mgr.get_template(name=name, user_id=None)
                if existing:
                    logger.info(f"Template '{name}' already exists, skipping...")
                    skipped_count += 1
                    continue
                
                # Download template
                logger.info(f"Downloading template '{name}' from {source}...")
                file_path = None
                
                if source == 'mega':
                    file_path = downloader.download_from_mega(url, template_name=name)
                elif source == 'mediafire':
                    file_path = downloader.download_from_mediafire(url, template_name=name)
                
                if not file_path:
                    logger.warning(f"Failed to download template '{name}', storing URL only")
                    file_path = None
                
                # Save to database as global template
                template_data = {
                    'source_url': url,
                    'source': source,
                    'auto_download': True  # Can be downloaded on demand
                }
                
                if file_path:
                    template_data['file_path'] = file_path
                
                template_id = template_mgr.save_template(
                    user_id=None,  # Global template
                    name=name,
                    template_type=template_type,
                    template_data=template_data,
                    category=category,
                    description=description,
                    is_global=True,
                    source_url=url,
                    file_path=file_path
                )
                
                if template_id:
                    logger.info(f"✅ Template '{name}' added (ID: {template_id})")
                    added_count += 1
                else:
                    logger.error(f"❌ Failed to save template '{name}' to database")
                    
            except Exception as e:
                logger.error(f"Error processing template '{template_info.get('name', 'unknown')}': {e}", exc_info=True)
        
        logger.info(f"\n{'='*50}")
        logger.info(f"Template addition complete!")
        logger.info(f"✅ Added: {added_count}")
        logger.info(f"⏭️  Skipped (already exists): {skipped_count}")
        logger.info(f"❌ Failed: {len(templates) - added_count - skipped_count}")
        logger.info(f"{'='*50}")
        
    except Exception as e:
        logger.error(f"Error adding templates: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    add_templates_to_database()
