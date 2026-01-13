#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Start both Telegram bot and Dashboard API services
For Railway deployment
"""

import subprocess
import threading
import os
import sys
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def install_tools_if_needed():
    """Install security tools if not available (Railway runtime installation)"""
    import subprocess
    import shutil
    
    # Check if we're on Railway
    if os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('RAILWAY_PUBLIC_DOMAIN'):
        logger.info("Railway environment detected - checking tools...")
        
        # Run post-deployment setup first
        post_deploy_script = os.path.join(os.getcwd(), 'post_deploy_setup.sh')
        if os.path.exists(post_deploy_script):
            try:
                logger.info("Running post-deployment setup...")
                result = subprocess.run(['bash', post_deploy_script], 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=120)
                if result.returncode == 0:
                    logger.info("Post-deployment setup completed")
                    if result.stdout:
                        logger.info(result.stdout[-500:])  # Last 500 chars
                else:
                    logger.warning(f"Post-deployment setup had issues: {result.stderr[:200]}")
            except Exception as e:
                logger.warning(f"Could not run post-deployment setup: {e}")
        
        # Check if install script exists and run it
        install_script = os.path.join(os.getcwd(), 'install_tools.sh')
        if os.path.exists(install_script):
            try:
                logger.info("Running tool installation script...")
                result = subprocess.run(['bash', install_script], 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=300)  # 5 minute timeout
                if result.returncode == 0:
                    logger.info("Tool installation completed successfully")
                    logger.info(result.stdout)
                else:
                    logger.warning(f"Tool installation had issues: {result.stderr}")
                
                # Always reinstall Click 8.0.1 after tool installation to prevent conflicts
                logger.info("Reinstalling Click 8.0.1 to ensure Flask compatibility...")
                try:
                    import subprocess as sp
                    click_result = sp.run(['pip', 'install', '--no-cache-dir', '--force-reinstall', 'click==8.0.1'],
                                        capture_output=True, text=True, timeout=60)
                    if click_result.returncode == 0:
                        logger.info("Click 8.0.1 reinstalled successfully")
                    else:
                        logger.warning(f"Could not reinstall Click: {click_result.stderr}")
                except Exception as e:
                    logger.warning(f"Error reinstalling Click: {e}")
            except Exception as e:
                logger.warning(f"Could not run installation script: {e}")
        else:
            logger.info("Installation script not found, skipping runtime installation")

def run_bot():
    """Run Telegram bot"""
    logger.info("Starting Telegram bot...")
    try:
        # Import and run bot directly (not as subprocess to avoid exit issues)
        import telegram_bot
        telegram_bot.main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Don't exit - let the main loop restart it

def run_dashboard():
    """Run Dashboard API"""
    logger.info("Starting Dashboard API...")
    try:
        # Verify and fix Click and Flask versions before importing
        try:
            import subprocess as sp
            import sys
            import importlib
            
            # Check Click version
            try:
                import click
                click_version = click.__version__
                logger.info(f"Current Click version: {click_version}")
            except:
                click_version = None
                logger.warning("Click not found, will install")
            
            # Check Flask version
            try:
                import flask
                flask_version = flask.__version__
                logger.info(f"Current Flask version: {flask_version}")
            except:
                flask_version = None
                logger.warning("Flask not found, will install")
            
            # Force reinstall both to ensure correct versions
            logger.info("Ensuring correct Click and Flask versions...")
            result = sp.run(['pip', 'install', '--no-cache-dir', '--force-reinstall', 
                           'click==8.0.1', 'flask==2.2.5'],
                          capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                logger.info("Click 8.0.1 and Flask 2.2.5 reinstalled successfully")
            else:
                logger.error(f"Failed to reinstall: {result.stderr}")
            
            # Clear module cache and reload
            for module in ['click', 'flask', 'flask.cli', 'flask.app']:
                if module in sys.modules:
                    del sys.modules[module]
            
            # Verify versions after reinstall
            import click
            import flask
            logger.info(f"Verified Click version: {click.__version__}")
            logger.info(f"Verified Flask version: {flask.__version__}")
            
            if not click.__version__.startswith('8.'):
                logger.error(f"Click version {click.__version__} is incorrect!")
            if not flask.__version__.startswith('2.2.'):
                logger.error(f"Flask version {flask.__version__} is incorrect!")
                
        except Exception as e:
            logger.error(f"Error verifying/fixing versions: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Continue anyway - might work
        
        # Import and run dashboard directly (not as subprocess)
        import dashboard
        dashboard.app.run(host='0.0.0.0', port=int(os.getenv('PORT', '8080')), debug=False)
    except KeyboardInterrupt:
        logger.info("Dashboard stopped by user")
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Don't exit - let the main loop restart it

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("Starting SMG-Forcer Services")
    logger.info("=" * 60)
    
    # Install tools if needed (Railway runtime installation)
    install_tools_if_needed()
    
    # Start monitoring service (auto-fix issues)
    try:
        from monitor_and_fix import run_monitor
        monitor = run_monitor()
        logger.info("✅ Monitoring service started")
    except Exception as e:
        logger.warning(f"Could not start monitoring service: {e}")
        monitor = None
    
    # Start bot in background thread
    bot_thread = threading.Thread(target=run_bot, daemon=True, name="TelegramBot")
    bot_thread.start()
    
    # Small delay to let bot initialize
    time.sleep(2)
    
    # Start dashboard in background thread
    dashboard_thread = threading.Thread(target=run_dashboard, daemon=True, name="DashboardAPI")
    dashboard_thread.start()
    
    logger.info("Both services started!")
    logger.info("Bot: Running in background")
    logger.info("Dashboard: Running in background")
    if monitor:
        logger.info("Monitor: Running in background (auto-fix enabled)")
    logger.info("Press Ctrl+C to stop")
    
    try:
        # Keep main thread alive
        while True:
            time.sleep(5)  # Check every 5 seconds instead of 1
            # Check if threads are still alive
            if not bot_thread.is_alive():
                logger.warning("Bot thread died, waiting 10 seconds before restarting...")
                time.sleep(10)  # Wait to avoid rapid restarts and conflicts
                logger.info("Restarting bot thread...")
                bot_thread = threading.Thread(target=run_bot, daemon=True, name="TelegramBot")
                bot_thread.start()
            
            if not dashboard_thread.is_alive():
                logger.warning("Dashboard thread died, restarting...")
                # Try to fix Click/Flask before restarting
                if monitor:
                    logger.info("Attempting auto-fix before restarting Dashboard...")
                    monitor.check_click_flask_versions()
                dashboard_thread = threading.Thread(target=run_dashboard, daemon=True, name="DashboardAPI")
                dashboard_thread.start()
    except KeyboardInterrupt:
        logger.info("Shutting down services...")
        sys.exit(0)

