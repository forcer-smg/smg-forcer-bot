# -*- coding: utf-8 -*-
"""
Browser Controller - Automated browser interaction
Supports Selenium and Playwright for web automation, testing, and scraping
"""

import os
import time
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
import asyncio

logger = logging.getLogger(__name__)

# Try to import browser automation libraries
SELENIUM_AVAILABLE = False
PLAYWRIGHT_AVAILABLE = False

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium not available")

try:
    from playwright.async_api import async_playwright, Browser, Page, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not available")

try:
    from stealth_manager import get_stealth_manager, StealthManager
    STEALTH_MANAGER_AVAILABLE = True
except ImportError:
    STEALTH_MANAGER_AVAILABLE = False
    logger.warning("stealth_manager not available")


class BrowserController:
    """Browser automation controller supporting Selenium and Playwright"""
    
    def __init__(self, workspace_root: Optional[str] = None, headless: bool = True):
        """
        Initialize browser controller
        workspace_root: Directory for browser data and screenshots
        headless: Run browser in headless mode
        """
        self.workspace_root = Path(workspace_root) if workspace_root else Path(os.getcwd())
        self.headless = headless
        self.selenium_driver = None
        self.playwright_browser = None
        self.playwright_context = None
        self.playwright_page = None
        self.current_url = None
        self.screenshot_dir = self.workspace_root / "browser_screenshots"
        self.screenshot_dir.mkdir(exist_ok=True)
        
        # Prefer Playwright if available (better for headless)
        self.use_playwright = PLAYWRIGHT_AVAILABLE
        self.use_selenium = SELENIUM_AVAILABLE and not PLAYWRIGHT_AVAILABLE
        
        # Initialize stealth manager
        self.stealth_manager = None
        if STEALTH_MANAGER_AVAILABLE:
            try:
                self.stealth_manager = get_stealth_manager(str(self.workspace_root))
                logger.info("Stealth manager initialized for browser controller")
            except Exception as e:
                logger.warning(f"Could not initialize stealth manager: {e}")
    
    async def start_browser(self, browser_type: str = "chrome") -> bool:
        """Start browser instance"""
        try:
            if self.use_playwright:
                return await self._start_playwright(browser_type)
            elif self.use_selenium:
                return self._start_selenium(browser_type)
            else:
                logger.error("No browser automation library available")
                return False
        except Exception as e:
            logger.error(f"Error starting browser: {e}")
            return False
    
    async def _start_playwright(self, browser_type: str) -> bool:
        """Start Playwright browser"""
        try:
            playwright = await async_playwright().start()
            browser_name = browser_type.lower()
            
            if browser_name == "chrome" or browser_name == "chromium":
                self.playwright_browser = await playwright.chromium.launch(headless=self.headless)
            elif browser_name == "firefox":
                self.playwright_browser = await playwright.firefox.launch(headless=self.headless)
            elif browser_name == "webkit" or browser_name == "safari":
                self.playwright_browser = await playwright.webkit.launch(headless=self.headless)
            else:
                self.playwright_browser = await playwright.chromium.launch(headless=self.headless)
            
            # Use stealth manager for headers and fingerprint if available
            context_options = {
                'viewport': {'width': 1920, 'height': 1080}
            }
            
            if self.stealth_manager:
                stealth_config = self.stealth_manager.get_session_config()
                fingerprint = stealth_config.get('fingerprint', {})
                
                # Apply fingerprint to context
                if 'screen_resolution' in fingerprint:
                    width, height = map(int, fingerprint['screen_resolution'].split('x'))
                    context_options['viewport'] = {'width': width, 'height': height}
                
                # Set user agent and other headers
                headers = stealth_config.get('headers', {})
                if 'User-Agent' in headers:
                    context_options['user_agent'] = headers['User-Agent']
            
            self.playwright_context = await self.playwright_browser.new_context(**context_options)
            self.playwright_page = await self.playwright_context.new_page()
            
            # Set extra headers if stealth manager available
            if self.stealth_manager:
                headers = self.stealth_manager.get_human_like_headers()
                await self.playwright_page.set_extra_http_headers(headers)
            
            logger.info(f"Playwright {browser_type} browser started (headless={self.headless})")
            return True
        except Exception as e:
            logger.error(f"Error starting Playwright browser: {e}")
            return False
    
    def _start_selenium(self, browser_type: str) -> bool:
        """Start Selenium browser"""
        try:
            browser_name = browser_type.lower()
            
            if browser_name == "chrome" or browser_name == "chromium":
                options = ChromeOptions()
                if self.headless:
                    options.add_argument('--headless')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--disable-gpu')
                options.add_argument('--window-size=1920,1080')
                self.selenium_driver = webdriver.Chrome(options=options)
            elif browser_name == "firefox":
                options = FirefoxOptions()
                if self.headless:
                    options.add_argument('--headless')
                self.selenium_driver = webdriver.Firefox(options=options)
            else:
                # Default to Chrome
                options = ChromeOptions()
                if self.headless:
                    options.add_argument('--headless')
                self.selenium_driver = webdriver.Chrome(options=options)
            
            self.selenium_driver.set_window_size(1920, 1080)
            logger.info(f"Selenium {browser_type} browser started (headless={self.headless})")
            return True
        except Exception as e:
            logger.error(f"Error starting Selenium browser: {e}")
            return False
    
    async def navigate(self, url: str) -> bool:
        """Navigate to URL with stealth delays"""
        try:
            # Add human-like delay before navigation if stealth manager available
            if self.stealth_manager:
                delay = self.stealth_manager.get_stealth_delay('navigation')
                await asyncio.sleep(delay)
            
            if self.use_playwright and self.playwright_page:
                await self.playwright_page.goto(url, wait_until='networkidle', timeout=30000)
                self.current_url = url
                
                # Add delay after navigation
                if self.stealth_manager:
                    await asyncio.sleep(self.stealth_manager.get_stealth_delay('request'))
                
                return True
            elif self.use_selenium and self.selenium_driver:
                self.selenium_driver.get(url)
                self.current_url = url
                
                # Add delay after navigation
                if self.stealth_manager:
                    time.sleep(self.stealth_manager.get_stealth_delay('request'))
                
                return True
            else:
                logger.error("Browser not started")
                return False
        except Exception as e:
            logger.error(f"Error navigating to {url}: {e}")
            return False
    
    async def click(self, selector: str, wait_timeout: int = 10) -> bool:
        """Click an element by selector"""
        try:
            if self.use_playwright and self.playwright_page:
                await self.playwright_page.click(selector, timeout=wait_timeout * 1000)
                return True
            elif self.use_selenium and self.selenium_driver:
                element = WebDriverWait(self.selenium_driver, wait_timeout).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                element.click()
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"Error clicking element {selector}: {e}")
            return False
    
    async def fill_input(self, selector: str, text: str) -> bool:
        """Fill an input field"""
        try:
            if self.use_playwright and self.playwright_page:
                await self.playwright_page.fill(selector, text)
                return True
            elif self.use_selenium and self.selenium_driver:
                element = WebDriverWait(self.selenium_driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                element.clear()
                element.send_keys(text)
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"Error filling input {selector}: {e}")
            return False
    
    async def submit_form(self, selector: Optional[str] = None) -> bool:
        """Submit a form"""
        try:
            if self.use_playwright and self.playwright_page:
                if selector:
                    await self.playwright_page.locator(selector).press('Enter')
                else:
                    await self.playwright_page.keyboard.press('Enter')
                return True
            elif self.use_selenium and self.selenium_driver:
                if selector:
                    form = self.selenium_driver.find_element(By.CSS_SELECTOR, selector)
                    form.submit()
                else:
                    from selenium.webdriver.common.keys import Keys
                    self.selenium_driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.RETURN)
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"Error submitting form: {e}")
            return False
    
    async def get_text(self, selector: str) -> Optional[str]:
        """Get text content of an element"""
        try:
            if self.use_playwright and self.playwright_page:
                return await self.playwright_page.locator(selector).text_content()
            elif self.use_selenium and self.selenium_driver:
                element = self.selenium_driver.find_element(By.CSS_SELECTOR, selector)
                return element.text
            else:
                return None
        except Exception as e:
            logger.error(f"Error getting text from {selector}: {e}")
            return None
    
    async def get_page_source(self) -> Optional[str]:
        """Get page HTML source"""
        try:
            if self.use_playwright and self.playwright_page:
                return await self.playwright_page.content()
            elif self.use_selenium and self.selenium_driver:
                return self.selenium_driver.page_source
            else:
                return None
        except Exception as e:
            logger.error(f"Error getting page source: {e}")
            return None
    
    async def execute_script(self, script: str) -> Optional[Any]:
        """Execute JavaScript"""
        try:
            if self.use_playwright and self.playwright_page:
                return await self.playwright_page.evaluate(script)
            elif self.use_selenium and self.selenium_driver:
                return self.selenium_driver.execute_script(script)
            else:
                return None
        except Exception as e:
            logger.error(f"Error executing script: {e}")
            return None
    
    async def wait_for_element(self, selector: str, timeout: int = 10) -> bool:
        """Wait for element to appear"""
        try:
            if self.use_playwright and self.playwright_page:
                await self.playwright_page.wait_for_selector(selector, timeout=timeout * 1000)
                return True
            elif self.use_selenium and self.selenium_driver:
                WebDriverWait(self.selenium_driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                return True
            else:
                return False
        except TimeoutException:
            logger.warning(f"Timeout waiting for element {selector}")
            return False
        except Exception as e:
            logger.error(f"Error waiting for element: {e}")
            return False
    
    async def take_screenshot(self, filename: Optional[str] = None) -> Optional[str]:
        """Take screenshot of current page"""
        try:
            if not filename:
                timestamp = int(time.time())
                filename = f"screenshot_{timestamp}.png"
            
            screenshot_path = self.screenshot_dir / filename
            
            if self.use_playwright and self.playwright_page:
                await self.playwright_page.screenshot(path=str(screenshot_path), full_page=True)
            elif self.use_selenium and self.selenium_driver:
                self.selenium_driver.save_screenshot(str(screenshot_path))
            else:
                return None
            
            logger.info(f"Screenshot saved: {screenshot_path}")
            return str(screenshot_path)
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
            return None
    
    async def extract_data(self, selectors: Dict[str, str]) -> Dict[str, Any]:
        """Extract data from page using selectors"""
        data = {}
        
        for key, selector in selectors.items():
            try:
                text = await self.get_text(selector)
                data[key] = text
            except Exception as e:
                logger.warning(f"Error extracting {key}: {e}")
                data[key] = None
        
        return data
    
    async def close(self):
        """Close browser"""
        try:
            if self.use_playwright:
                if self.playwright_page:
                    await self.playwright_page.close()
                if self.playwright_context:
                    await self.playwright_context.close()
                if self.playwright_browser:
                    await self.playwright_browser.close()
            elif self.use_selenium and self.selenium_driver:
                self.selenium_driver.quit()
                self.selenium_driver = None
            
            logger.info("Browser closed")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")
    
    def is_browser_available(self) -> bool:
        """Check if browser automation is available"""
        return self.use_playwright or self.use_selenium


# Global browser controller instance
_browser_instance = None

def get_browser_controller(workspace_root: Optional[str] = None, headless: bool = True) -> BrowserController:
    """Get or create global browser controller instance"""
    global _browser_instance
    if _browser_instance is None:
        _browser_instance = BrowserController(workspace_root, headless)
    return _browser_instance
