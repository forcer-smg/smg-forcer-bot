# -*- coding: utf-8 -*-
"""
Telegram Bot Module - Shared classes and instances
Contains TelegramBot, GitHubReleaseChecker, and SettingsSync classes
Used by both telegram_bot.py (main bot) and dashboard.py
"""

import os
import json
import requests
from datetime import datetime
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)

class TelegramBot:
    """Telegram Bot integration for desktop app"""
    
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or os.environ.get('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.environ.get('TELEGRAM_CHAT_ID')
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None
        self.enabled = bool(self.bot_token and self.chat_id)
        
    def send_message(self, text: str, parse_mode: str = 'Markdown') -> bool:
        """Send message to Telegram chat"""
        if not self.enabled:
            logger.warning("Telegram bot not configured")
            return False
            
        try:
            url = f"{self.api_url}/sendMessage"
            data = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': parse_mode
            }
            response = requests.post(url, json=data, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    def send_notification(self, title: str, message: str, priority: str = 'info') -> bool:
        """Send formatted notification"""
        emoji = {
            'info': 'ℹ️',
            'success': '✅',
            'warning': '⚠️',
            'error': '❌',
            'update': '🆕'
        }.get(priority, 'ℹ️')
        
        text = f"{emoji} **{title}**\n\n{message}"
        return self.send_message(text)
    
    def notify_update(self, version: str, download_url: str, changelog: str = "") -> bool:
        """Notify about new desktop app update"""
        message = f"""🆕 **Auto_Punch IDE Update Available!**

📦 **Version:** {version}
📥 **Download:** [Click here]({download_url})

{changelog if changelog else 'Bug fixes and improvements'}

Update your desktop app to get the latest features!"""
        return self.send_message(message)
    
    def notify_status(self, status: str, details: str = "") -> bool:
        """Send status update"""
        message = f"""🖥️ **Desktop App Status**

**Status:** {status}
{details if details else ''}"""
        return self.send_message(message)
    
    def notify_dashboard_event(self, event_type: str, title: str, details: str = "", data: Dict = None) -> bool:
        """Send dashboard event notification"""
        emoji_map = {
            'terminal': '💻',
            'toolkit': '🔧',
            'extension': '📦',
            'git': '🔀',
            'settings': '⚙️',
            'dashboard_fix': '🛠️',
            'error': '❌',
            'success': '✅',
            'info': 'ℹ️'
        }
        
        emoji = emoji_map.get(event_type, 'ℹ️')
        message = f"""{emoji} **Dashboard: {title}**

{details}"""
        
        if data:
            if 'command' in data:
                message += f"\n\n**Command:** `{data['command']}`"
            if 'tool' in data:
                message += f"\n\n**Tool:** {data['tool']}"
            if 'result' in data:
                result = str(data['result'])[:200]
                message += f"\n\n**Result:** {result}"
            if 'extension' in data:
                message += f"\n\n**Extension:** {data['extension']}"
        
        return self.send_message(message)
    
    def notify_terminal_command(self, command: str, output: str = "", success: bool = True) -> bool:
        """Notify about terminal command execution"""
        status = "✅ Success" if success else "❌ Failed"
        message = f"""💻 **Terminal Command Executed**

**Command:** `{command}`
**Status:** {status}"""
        
        if output:
            output_preview = output[:300] + "..." if len(output) > 300 else output
            message += f"\n\n**Output:**\n```\n{output_preview}\n```"
        
        return self.send_message(message)
    
    def notify_toolkit_execution(self, tool_name: str, result: str = "", success: bool = True) -> bool:
        """Notify about toolkit tool execution"""
        status = "✅ Success" if success else "❌ Failed"
        message = f"""🔧 **Toolkit Tool Executed**

**Tool:** {tool_name}
**Status:** {status}"""
        
        if result:
            result_preview = result[:300] + "..." if len(result) > 300 else result
            message += f"\n\n**Result:**\n```\n{result_preview}\n```"
        
        return self.send_message(message)
    
    def notify_extension_install(self, extension_id: str, success: bool = True) -> bool:
        """Notify about extension installation"""
        status = "✅ Installed" if success else "❌ Failed"
        message = f"""📦 **Extension Installation**

**Extension:** {extension_id}
**Status:** {status}"""
        
        return self.send_message(message)
    
    def notify_git_operation(self, operation: str, result: str = "", success: bool = True) -> bool:
        """Notify about Git operation"""
        status = "✅ Success" if success else "❌ Failed"
        message = f"""🔀 **Git Operation**

**Operation:** {operation}
**Status:** {status}"""
        
        if result:
            result_preview = result[:200] + "..." if len(result) > 200 else result
            message += f"\n\n**Result:**\n{result_preview}"
        
        return self.send_message(message)
    
    def notify_dashboard_fix(self, issue: str, fixes: List[Dict] = None, success: bool = True) -> bool:
        """Notify about dashboard fix"""
        status = "✅ Fixed" if success else "❌ Failed"
        message = f"""🛠️ **Dashboard Fix**

**Issue:** {issue}
**Status:** {status}"""
        
        if fixes:
            message += f"\n\n**Fixes Applied:** {len(fixes)}"
            for i, fix in enumerate(fixes[:3], 1):
                fix_desc = fix.get('description', fix.get('file', 'Unknown'))
                message += f"\n{i}. {fix_desc}"
        
        return self.send_message(message)


class GitHubReleaseChecker:
    """Check for GitHub releases and notify users"""
    
    def __init__(self, repo: str = "SMG-Dawn/Auto-Punch-IDE-Desktop"):
        self.repo = repo
        self.api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    
    def get_latest_release(self) -> Optional[Dict]:
        """Get latest release from GitHub"""
        try:
            response = requests.get(self.api_url, timeout=10)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Failed to get GitHub release: {e}")
            return None
    
    def get_release_assets(self, release: Dict) -> Dict:
        """Extract download URLs from release"""
        assets = {
            'exe_url': None,
            'msi_url': None,
            'version': release.get('tag_name', ''),
            'changelog': release.get('body', ''),
            'published_at': release.get('published_at', '')
        }
        
        for asset in release.get('assets', []):
            name = asset.get('name', '').lower()
            url = asset.get('browser_download_url', '')
            
            if name.endswith('.exe'):
                assets['exe_url'] = url
            elif name.endswith('.msi'):
                assets['msi_url'] = url
        
        return assets


class SettingsSync:
    """Sync settings between web and desktop via Supabase"""
    
    def __init__(self, supabase_url: Optional[str] = None, supabase_key: Optional[str] = None):
        self.supabase_url = supabase_url or os.environ.get('SUPABASE_URL')
        self.supabase_key = supabase_key or os.environ.get('SUPABASE_KEY')
        self.enabled = bool(self.supabase_url and self.supabase_key)
        
        if self.enabled:
            try:
                from supabase import create_client, Client
                self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
            except ImportError:
                logger.warning("Supabase client not installed. Install with: pip install supabase")
                self.enabled = False
            except Exception as e:
                logger.error(f"Failed to initialize Supabase: {e}")
                self.enabled = False
    
    def save_settings(self, user_id: int, settings: Dict) -> bool:
        """Save user settings to Supabase"""
        if not self.enabled:
            return False
            
        try:
            data = {
                'user_id': user_id,
                'settings': json.dumps(settings),
                'updated_at': datetime.now().isoformat()
            }
            self.supabase.table('user_settings').upsert(data).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            return False
    
    def get_settings(self, user_id: int) -> Dict:
        """Get user settings from Supabase"""
        if not self.enabled:
            return {}
            
        try:
            result = self.supabase.table('user_settings').select('*').eq('user_id', user_id).execute()
            if result.data:
                settings_str = result.data[0].get('settings', '{}')
                return json.loads(settings_str) if isinstance(settings_str, str) else settings_str
            return {}
        except Exception as e:
            logger.error(f"Failed to get settings: {e}")
            return {}
    
    def register_desktop(self, user_id: int, device_id: str, app_version: str) -> bool:
        """Register desktop app installation"""
        if not self.enabled:
            return False
            
        try:
            data = {
                'user_id': user_id,
                'device_id': device_id,
                'app_version': app_version,
                'registered_at': datetime.now().isoformat()
            }
            self.supabase.table('desktop_registrations').upsert(data).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to register desktop: {e}")
            return False


# Global instances - can be imported by both telegram_bot.py and dashboard.py
telegram_bot = TelegramBot()
github_release = GitHubReleaseChecker()
settings_sync = SettingsSync()

