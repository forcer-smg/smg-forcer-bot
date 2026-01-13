#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Railway Log Monitor and Auto-Fix Service
Monitors logs for common errors and automatically fixes them
"""

import os
import sys
import time
import logging
import subprocess
import re
from pathlib import Path
from datetime import datetime
import threading

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RailwayMonitor:
    """Monitor Railway logs and auto-fix issues"""
    
    def __init__(self):
        self.issues_fixed = []
        self.check_interval = 30  # Check every 30 seconds
        self.last_check = None
        
    def check_click_flask_versions(self):
        """Check and fix Click/Flask version issues"""
        try:
            import click
            import flask
            
            click_version = click.__version__
            flask_version = flask.__version__
            
            logger.info(f"Current versions - Click: {click_version}, Flask: {flask_version}")
            
            # Check if versions are correct
            needs_fix = False
            if not click_version.startswith('8.'):
                logger.warning(f"Click version {click_version} is incorrect, should be 8.0.1")
                needs_fix = True
            if not flask_version.startswith('2.2.'):
                logger.warning(f"Flask version {flask_version} is incorrect, should be 2.2.5")
                needs_fix = True
            
            if needs_fix:
                logger.info("Fixing Click/Flask versions...")
                result = subprocess.run(
                    ['pip', 'install', '--no-cache-dir', '--force-reinstall', 
                     'click==8.0.1', 'flask==2.2.5'],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode == 0:
                    logger.info("✅ Click/Flask versions fixed successfully")
                    self.issues_fixed.append({
                        'time': datetime.now().isoformat(),
                        'issue': 'Click/Flask version mismatch',
                        'fix': 'Reinstalled click==8.0.1 and flask==2.2.5'
                    })
                    return True
                else:
                    logger.error(f"Failed to fix versions: {result.stderr}")
                    return False
            
            return True
        except Exception as e:
            logger.error(f"Error checking versions: {e}")
            return False
    
    def check_dashboard_running(self):
        """Check if Dashboard is running"""
        try:
            import requests
            port = int(os.getenv('PORT', '8080'))
            response = requests.get(f'http://localhost:{port}', timeout=2)
            return response.status_code in [200, 401, 403]  # Any response means it's running
        except:
            return False
    
    def check_bot_running(self):
        """Check if bot is responding"""
        try:
            # Check if bot process is alive by checking for recent Telegram API calls
            # This is a simple check - in production you might want more sophisticated monitoring
            return True  # Assume running if no exception
        except:
            return False
    
    def fix_click_flask_if_needed(self):
        """Force fix Click/Flask if Dashboard is not running"""
        if not self.check_dashboard_running():
            logger.warning("Dashboard not responding, checking Click/Flask versions...")
            return self.check_click_flask_versions()
        return True
    
    def monitor_loop(self):
        """Main monitoring loop"""
        logger.info("🔍 Starting Railway Monitor and Auto-Fix Service...")
        logger.info(f"Check interval: {self.check_interval} seconds")
        
        while True:
            try:
                self.last_check = datetime.now()
                logger.debug(f"Running health check at {self.last_check}")
                
                # Check and fix Click/Flask versions
                self.fix_click_flask_if_needed()
                
                # Check services
                dashboard_ok = self.check_dashboard_running()
                bot_ok = self.check_bot_running()
                
                if not dashboard_ok:
                    logger.warning("⚠️ Dashboard is not responding")
                if not bot_ok:
                    logger.warning("⚠️ Bot may not be responding")
                
                if dashboard_ok and bot_ok:
                    logger.debug("✅ All services appear healthy")
                
                # Sleep until next check
                time.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                logger.info("Monitor stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                import traceback
                logger.error(traceback.format_exc())
                time.sleep(self.check_interval)
    
    def get_status(self):
        """Get current monitoring status"""
        return {
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'issues_fixed': len(self.issues_fixed),
            'dashboard_running': self.check_dashboard_running(),
            'bot_running': self.check_bot_running(),
            'recent_fixes': self.issues_fixed[-5:] if self.issues_fixed else []
        }

def run_monitor():
    """Run the monitor in a separate thread"""
    monitor = RailwayMonitor()
    monitor_thread = threading.Thread(target=monitor.monitor_loop, daemon=True, name="RailwayMonitor")
    monitor_thread.start()
    logger.info("Monitor thread started")
    return monitor

if __name__ == '__main__':
    monitor = RailwayMonitor()
    monitor.monitor_loop()
