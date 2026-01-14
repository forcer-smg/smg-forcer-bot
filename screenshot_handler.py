# -*- coding: utf-8 -*-
"""
Screenshot Handler - Takes screenshots and sends to Telegram
"""

import os
import logging
from pathlib import Path
from typing import Optional
import tempfile

logger = logging.getLogger(__name__)

try:
    from PIL import ImageGrab
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    logger.warning("Pillow not available for screenshots")

try:
    import mss
    import mss.tools
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False
    logger.warning("mss not available for screenshots")

# Browser automation for headless screenshots
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("selenium not available for browser screenshots")

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("playwright not available for browser screenshots")


class ScreenshotHandler:
    """Handles screenshot capture and management"""
    
    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = Path(workspace_root) if workspace_root else Path(tempfile.gettempdir())
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.browser = None  # Store browser instance if using browser automation
    
    def take_screenshot(self, filename: Optional[str] = None, browser_instance=None) -> Optional[str]:
        """
        Take a screenshot and save it
        If browser_instance is provided, takes screenshot from browser (works in headless mode)
        Otherwise tries screen capture (requires display)
        Returns path to saved screenshot file
        """
        if not filename:
            import time
            filename = f"screenshot_{int(time.time())}.png"
        
        screenshot_path = self.workspace_root / filename
        
        # If browser instance provided, take screenshot from browser (works headless)
        if browser_instance:
            try:
                if hasattr(browser_instance, 'save_screenshot'):  # Selenium
                    browser_instance.save_screenshot(str(screenshot_path))
                    logger.info(f"Browser screenshot saved: {screenshot_path}")
                    return str(screenshot_path)
                elif hasattr(browser_instance, 'screenshot'):  # Playwright
                    browser_instance.screenshot(path=str(screenshot_path))
                    logger.info(f"Browser screenshot saved: {screenshot_path}")
                    return str(screenshot_path)
            except Exception as e:
                logger.error(f"Failed to take browser screenshot: {e}")
                # Fall through to regular screenshot methods
        
        # Regular screen capture (requires display/GUI)
        try:
            # Try using mss first (more reliable, cross-platform)
            if MSS_AVAILABLE:
                with mss.mss() as sct:
                    # Capture entire screen
                    monitor = sct.monitors[1]  # Monitor 1 is the entire screen
                    screenshot = sct.grab(monitor)
                    
                    # Save to file
                    mss.tools.to_png(screenshot.rgb, screenshot.size, output=str(screenshot_path))
                    logger.info(f"Screenshot saved: {screenshot_path}")
                    return str(screenshot_path)
            
            # Fallback to PIL ImageGrab (Windows/Mac)
            elif PILLOW_AVAILABLE:
                screenshot = ImageGrab.grab()
                screenshot.save(screenshot_path, 'PNG')
                logger.info(f"Screenshot saved: {screenshot_path}")
                return str(screenshot_path)
            
            else:
                logger.warning("No screenshot library available. For headless servers, use browser automation.")
                return None
        
        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")
            # On headless servers, this is expected - suggest browser automation
            if "display" in str(e).lower() or "no display" in str(e).lower():
                logger.info("Note: Screen capture requires a display. Use browser automation for headless servers.")
            return None
    
    def take_browser_screenshot(self, url: Optional[str] = None, browser_instance=None) -> Optional[str]:
        """
        Take screenshot using browser automation (works in headless mode)
        If browser_instance provided, uses it; otherwise creates temporary browser
        """
        import time
        filename = f"browser_screenshot_{int(time.time())}.png"
        screenshot_path = self.workspace_root / filename
        
        # If browser instance provided, use it
        if browser_instance:
            return self.take_screenshot(filename=filename, browser_instance=browser_instance)
        
        # Try to create browser for screenshot
        try:
            if SELENIUM_AVAILABLE:
                # Use Selenium with headless Chrome
                chrome_options = ChromeOptions()
                chrome_options.add_argument('--headless')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--disable-gpu')
                chrome_options.add_argument('--window-size=1920,1080')
                
                try:
                    driver = webdriver.Chrome(options=chrome_options)
                    if url:
                        driver.get(url)
                    driver.save_screenshot(str(screenshot_path))
                    driver.quit()
                    logger.info(f"Browser screenshot saved: {screenshot_path}")
                    return str(screenshot_path)
                except Exception as e:
                    logger.warning(f"Selenium screenshot failed: {e}")
            
            if PLAYWRIGHT_AVAILABLE:
                # Use Playwright
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    if url:
                        page.goto(url)
                    page.screenshot(path=str(screenshot_path))
                    browser.close()
                    logger.info(f"Playwright screenshot saved: {screenshot_path}")
                    return str(screenshot_path)
        except Exception as e:
            logger.error(f"Browser screenshot failed: {e}")
        
        return None
    
    def take_screenshot_area(self, x: int, y: int, width: int, height: int, 
                            filename: Optional[str] = None) -> Optional[str]:
        """
        Take screenshot of specific area
        Returns path to saved screenshot file
        """
        if not filename:
            import time
            filename = f"screenshot_area_{int(time.time())}.png"
        
        screenshot_path = self.workspace_root / filename
        
        try:
            if MSS_AVAILABLE:
                with mss.mss() as sct:
                    # Capture specific area
                    monitor = {"top": y, "left": x, "width": width, "height": height}
                    screenshot = sct.grab(monitor)
                    
                    # Save to file
                    mss.tools.to_png(screenshot.rgb, screenshot.size, output=str(screenshot_path))
                    logger.info(f"Area screenshot saved: {screenshot_path}")
                    return str(screenshot_path)
            
            elif PILLOW_AVAILABLE:
                screenshot = ImageGrab.grab(bbox=(x, y, x + width, y + height))
                screenshot.save(screenshot_path, 'PNG')
                logger.info(f"Area screenshot saved: {screenshot_path}")
                return str(screenshot_path)
            
            else:
                logger.error("No screenshot library available")
                return None
        
        except Exception as e:
            logger.error(f"Failed to take area screenshot: {e}")
            return None
    
    def cleanup_screenshot(self, file_path: str):
        """Delete screenshot file"""
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
                logger.info(f"Cleaned up screenshot: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup screenshot {file_path}: {e}")


# Global handler instance
_handler_instance = None

def get_screenshot_handler(workspace_root: Optional[str] = None) -> ScreenshotHandler:
    """Get or create global screenshot handler instance"""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = ScreenshotHandler(workspace_root)
    return _handler_instance
