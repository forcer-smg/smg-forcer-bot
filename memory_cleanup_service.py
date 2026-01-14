# -*- coding: utf-8 -*-
"""
Memory Cleanup Service - Automatic 3-day cleanup with secure deletion
Background daemon that cleans up expired user data securely
"""

import os
import logging
import asyncio
import threading
from typing import Optional
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class MemoryCleanupService:
    """Background service for automatic memory cleanup"""
    
    def __init__(self, memory_manager, cleanup_interval: int = 3600):
        """
        Initialize Memory Cleanup Service
        memory_manager: SecureMemoryManager instance
        cleanup_interval: Cleanup interval in seconds (default: 1 hour)
        """
        self.memory_manager = memory_manager
        self.cleanup_interval = cleanup_interval
        self.running = False
        self.cleanup_thread = None
        self.stats = {
            'total_cleanups': 0,
            'total_deleted': 0,
            'last_cleanup': None,
            'errors': 0
        }
    
    def start(self):
        """Start cleanup service"""
        if self.running:
            logger.warning("Cleanup service already running")
            return
        
        self.running = True
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()
        logger.info(f"Memory cleanup service started (interval: {self.cleanup_interval}s)")
    
    def stop(self):
        """Stop cleanup service"""
        self.running = False
        if self.cleanup_thread:
            self.cleanup_thread.join(timeout=5)
        logger.info("Memory cleanup service stopped")
    
    def _cleanup_loop(self):
        """Main cleanup loop"""
        import time
        
        while self.running:
            try:
                # Run cleanup
                deleted = self.memory_manager.cleanup_expired()
                
                # Update stats
                self.stats['total_cleanups'] += 1
                self.stats['total_deleted'] += deleted
                self.stats['last_cleanup'] = datetime.now().isoformat()
                
                if deleted > 0:
                    logger.info(f"Cleanup completed: {deleted} expired user(s) deleted")
                else:
                    logger.debug("Cleanup completed: No expired data found")
            
            except Exception as e:
                self.stats['errors'] += 1
                logger.error(f"Error in cleanup loop: {e}", exc_info=True)
            
            # Wait for next cleanup
            time.sleep(self.cleanup_interval)
    
    def cleanup_now(self) -> int:
        """Trigger immediate cleanup"""
        try:
            deleted = self.memory_manager.cleanup_expired()
            self.stats['total_cleanups'] += 1
            self.stats['total_deleted'] += deleted
            self.stats['last_cleanup'] = datetime.now().isoformat()
            return deleted
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"Error in immediate cleanup: {e}")
            return 0
    
    def get_stats(self) -> dict:
        """Get cleanup service statistics"""
        return self.stats.copy()


# Global cleanup service instance
_cleanup_service_instance = None
_cleanup_service_lock = threading.Lock()

def get_cleanup_service(memory_manager, cleanup_interval: int = 3600) -> MemoryCleanupService:
    """Get or create global cleanup service instance"""
    global _cleanup_service_instance
    with _cleanup_service_lock:
        if _cleanup_service_instance is None:
            _cleanup_service_instance = MemoryCleanupService(memory_manager, cleanup_interval)
        return _cleanup_service_instance
